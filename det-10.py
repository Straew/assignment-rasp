"""
Front door motion detector using an HC-SR04 ultrasonic sensor.

Wiring:
    VCC  -> 5V
    GND  -> GND
    TRIG -> GPIO5  (physical pin 29)
    ECHO -> GPIO6  (physical pin 31)

Note: ECHO outputs 5V but the Pi's GPIO pins are only 3.3V tolerant.
Make sure you're using a voltage divider (or a logic level shifter) on
the ECHO line, or you risk damaging the GPIO pin.

Sends a push notification (via ntfy.sh) when something is detected
within DISTANCE_THRESHOLD_CM, with a cooldown so it doesn't spam you.
"""

import RPi.GPIO as GPIO
import time
import requests
from datetime import datetime

# ---------- Config ----------
TRIG_PIN = 5
ECHO_PIN = 6

DISTANCE_THRESHOLD_CM = 100     # trigger alert if something is closer than this
COOLDOWN_SECONDS = 5 * 60       # 5 minute cooldown between notifications
CHECK_INTERVAL_SECONDS = 0.5    # how often to poll the sensor

NTFY_TOPIC = "your-unique-topic-name"   # change this to something unique/private
NTFY_URL = f"https://ntfy.sh/{NTFY_TOPIC}"
# -----------------------------

GPIO.setmode(GPIO.BCM)
GPIO.setup(TRIG_PIN, GPIO.OUT)
GPIO.setup(ECHO_PIN, GPIO.IN)
GPIO.output(TRIG_PIN, False)

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
    """Sends a push notification via ntfy.sh."""
    try:
        requests.post(
            NTFY_URL,
            data=f"Motion detected at front door ({distance} cm away)".encode("utf-8"),
            headers={
                "Title": "Front Door Alert",
                "Priority": "high",
                "Tags": "warning,door",
            },
            timeout=5,
        )
        print(f"[{datetime.now()}] Notification sent (distance={distance}cm)")
    except requests.exceptions.RequestException as e:
        print(f"[{datetime.now()}] Failed to send notification: {e}")


def cooldown_active():
    """Returns True if we're still within the cooldown window."""
    if last_notified is None:
        return False
    return (time.time() - last_notified) < COOLDOWN_SECONDS


def main():
    global last_notified
    print("Starting front door motion detector... (Ctrl+C to stop)")

    try:
        while True:
            distance = get_distance_cm()

            if distance is not None and distance < DISTANCE_THRESHOLD_CM:
                if not cooldown_active():
                    send_notification(distance)
                    last_notified = time.time()
                else:
                    remaining = COOLDOWN_SECONDS - (time.time() - last_notified)
                    print(f"[{datetime.now()}] Motion detected but in cooldown "
                          f"({int(remaining)}s remaining)")

            time.sleep(CHECK_INTERVAL_SECONDS)

    except KeyboardInterrupt:
        print("\nStopping detector...")

    finally:
        GPIO.cleanup()


if __name__ == "__main__":
    main()
