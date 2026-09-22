"""
Front door motion detector using an HC-SR04 ultrasonic sensor.

Wiring:
    VCC  -> 5V
    GND  -> GND
    TRIG -> GPIO14 (physical pin 8)
    ECHO -> GPIO15 (physical pin 10) - through the voltage divider
    LED  -> GPIO18 (physical pin 12), through a resistor to GND

Note: ECHO outputs 5V but the Pi's GPIO pins are only 3.3V tolerant.
Make sure you're using a voltage divider (or a logic level shifter) on
the ECHO line, or you risk damaging the GPIO pin.

Sends a push notification (via ntfy.sh) when something is detected
within DISTANCE_THRESHOLD_CM, with a cooldown so it doesn't spam you.
"""

import RPi.GPIO as GPIO
import time
import requests
import urllib.parse
from datetime import datetime

# ---------- Config ----------
TRIG_PIN = 14
ECHO_PIN = 15
LED_PIN = 18   # optional visual indicator - lights up when motion is detected

DISTANCE_THRESHOLD_CM = 100     # trigger alert if something is closer than this
COOLDOWN_SECONDS = 5 * 60       # 5 minute cooldown between notifications
CHECK_INTERVAL_SECONDS = 0.5    # how often to poll the sensor

# --- WhatsApp via CallMeBot (free) ---
# Setup (one-time):
#   1. Save +34 621 331 709 to your phone contacts (double check the current
#      number at https://www.callmebot.com/blog/free-api-whatsapp-messages/
#      since it can change).
#   2. From WhatsApp, message that contact: "I allow callmebot to send me messages"
#   3. Within ~2 min you'll get a reply with your API key. Put it below.
WHATSAPP_PHONE = "+61XXXXXXXXX"   # your number, international format, no spaces
WHATSAPP_API_KEY = "your_api_key_here"

SEND_TEST_ON_STARTUP = True  # sends one test WhatsApp message immediately when the script starts,
                              # so you can confirm your credentials work without waiting for motion.
                              # Set to False once you've confirmed it's working.
# -----------------------------

GPIO.setmode(GPIO.BCM)
GPIO.setup(TRIG_PIN, GPIO.OUT)
GPIO.setup(ECHO_PIN, GPIO.IN)
GPIO.setup(LED_PIN, GPIO.OUT)
GPIO.output(TRIG_PIN, False)
GPIO.output(LED_PIN, False)

last_notified = None  # timestamp of the last notification sent


def get_distance_cm():
    """Fires the ultrasonic pulse and returns the measured distance in cm."""
    GPIO.output(TRIG_PIN, True)
    time.sleep(0.00001)  # 10 microsecond pulse
    GPIO.output(TRIG_PIN, False)

    timeout_start = time.time()

    # wait for echo to go high (with timeout so we never hang forever)
    while GPIO.input(ECHO_PIN) == 0:
        pulse_start = time.time()
        if pulse_start - timeout_start > 0.05:
            return None

    while GPIO.input(ECHO_PIN) == 1:
        pulse_end = time.time()
        if pulse_end - timeout_start > 0.05:
            return None

    pulse_duration = pulse_end - pulse_start
    distance = (pulse_duration * 34300) / 2  # speed of sound = 34300 cm/s
    return round(distance, 1)


def send_notification(distance):
    """Sends a WhatsApp message via the CallMeBot API."""
    message = f"🚨 Motion detected at front door ({distance} cm away)"
    encoded_message = urllib.parse.quote(message)
    url = (
        "https://api.callmebot.com/whatsapp.php"
        f"?phone={WHATSAPP_PHONE}&text={encoded_message}&apikey={WHATSAPP_API_KEY}"
    )

    print(f"[{datetime.now()}] Sending WhatsApp notification...")
    try:
        response = requests.get(url, timeout=10)
        print(f"[{datetime.now()}] CallMeBot response (status {response.status_code}): {response.text}")
        if response.status_code == 200 and "Message queued" in response.text:
            print(f"[{datetime.now()}] WhatsApp notification confirmed sent (distance={distance}cm)")
        else:
            print(f"[{datetime.now()}] WhatsApp send may have FAILED - check the response text above. "
                  f"Common causes: wrong phone number format, expired/wrong API key, "
                  f"or you never sent the activation message to the CallMeBot contact.")
    except requests.exceptions.RequestException as e:
        print(f"[{datetime.now()}] Failed to send WhatsApp notification: {e}")


def cooldown_active():
    """Returns True if we're still within the cooldown window."""
    if last_notified is None:
        return False
    return (time.time() - last_notified) < COOLDOWN_SECONDS


def main():
    global last_notified
    print("Starting front door motion detector... (Ctrl+C to stop)")

    if SEND_TEST_ON_STARTUP:
        print(f"[{datetime.now()}] Sending a test WhatsApp message to verify credentials...")
        send_notification("TEST - 0")

    try:
        while True:
            distance = get_distance_cm()

            if distance is None:
                print(f"[{datetime.now()}] No echo received (sensor timeout) "
                      f"- check wiring/power")
            else:
                print(f"[{datetime.now()}] Distance: {distance} cm")

            if distance is not None and distance < DISTANCE_THRESHOLD_CM:
                print(f"[{datetime.now()}] *** MOTION DETECTED *** ({distance} cm, "
                      f"threshold is {DISTANCE_THRESHOLD_CM} cm)")
                GPIO.output(LED_PIN, True)
                if not cooldown_active():
                    send_notification(distance)
                    last_notified = time.time()
                else:
                    remaining = COOLDOWN_SECONDS - (time.time() - last_notified)
                    print(f"[{datetime.now()}] Skipping notification - still in cooldown "
                          f"({int(remaining)}s remaining)")
            else:
                GPIO.output(LED_PIN, False)

            time.sleep(CHECK_INTERVAL_SECONDS)

    except KeyboardInterrupt:
        print("\nStopping detector...")

    finally:
        GPIO.output(LED_PIN, False)
        GPIO.cleanup()


if __name__ == "__main__":
    main()