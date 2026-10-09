import socket
import json
import math
import time
import statistics

# ============================================================
# CONFIGURATION
# ============================================================

ODOM_PORT = 4212
BUFFER_SIZE = 4096

# MPU6500 configured for +/-250 degrees/second
GYRO_LSB_PER_DPS = 131.0

# Adjust only if your firmware uses different field names.
GYRO_FIELDS = ("gx", "gy", "gz")

# ============================================================
# STATE
# ============================================================

latest = None
samples = []

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
sock.bind(("0.0.0.0", ODOM_PORT))
sock.settimeout(0.5)


def receive_packet():
    """Receive one valid odometry packet."""
    while True:
        try:
            data, address = sock.recvfrom(BUFFER_SIZE)
            arrival = time.monotonic()
            packet = json.loads(data.decode())

            if packet.get("device") != "odom":
                continue

            if not packet.get("imuOK", False):
                continue

            if not all(k in packet for k in GYRO_FIELDS):
                continue

            return arrival, address, packet

        except socket.timeout:
            continue

        except (ValueError, UnicodeDecodeError, KeyError):
            continue


def gyro_dps(packet):
    return tuple(
        float(packet[k]) / GYRO_LSB_PER_DPS
        for k in GYRO_FIELDS
    )


def get_timestamp(packet, arrival):
    """
    Use ESP32 microsecond timestamp when available.

    ESP32 micros() can wrap after ~71.6 minutes.
    For short calibration runs, that is not an issue
    unless a wrap occurs during the test.
    """
    if "t" in packet:
        return float(packet["t"]) / 1_000_000.0

    return arrival


def collect(duration, label):
    """
    Collect gyro readings and integrate all three axes.

    Assumes the odometry ESP32 is already streaming.
    """
    print()
    print("=" * 62)
    print(label)
    print("=" * 62)
    print(f"Recording for {duration:.1f} seconds...")
    print()

    readings = []
    integrated = [0.0, 0.0, 0.0]

    previous_t = None
    start = time.monotonic()
    last_print = start

    while time.monotonic() - start < duration:
        try:
            arrival, address, packet = receive_packet()
        except KeyboardInterrupt:
            break

        t = get_timestamp(packet, arrival)
        rates = gyro_dps(packet)

        if previous_t is not None:
            dt = t - previous_t

            # Reject bad or discontinuous timestamps.
            if 0.0 < dt <= 0.2:
                for i in range(3):
                    integrated[i] += rates[i] * dt

        previous_t = t
        readings.append(rates)

        if arrival - last_print >= 0.25:
            print(
                f"GX {rates[0]:+8.2f} °/s | "
                f"GY {rates[1]:+8.2f} °/s | "
                f"GZ {rates[2]:+8.2f} °/s"
            )
            last_print = arrival

    if not readings:
        print("No IMU packets received.")
        return None

    means = [
        statistics.mean(r[i] for r in readings)
        for i in range(3)
    ]

    peaks = [
        max(abs(r[i]) for r in readings)
        for i in range(3)
    ]

    print()
    print("RESULTS")
    print("-" * 62)

    for i, name in enumerate(("X", "Y", "Z")):
        print(
            f"{name}: "
            f"mean={means[i]:+8.3f} °/s | "
            f"peak={peaks[i]:8.2f} °/s | "
            f"integrated={integrated[i]:+9.2f}°"
        )

    print(f"\nReceived {len(readings)} samples.")

    return {
        "means": means,
        "peaks": peaks,
        "integrated": integrated,
        "samples": len(readings),
    }


def print_comparison(cw, ccw):
    if cw is None or ccw is None:
        return

    names = ("X", "Y", "Z")

    print()
    print("=" * 62)
    print("YAW AXIS IDENTIFICATION")
    print("=" * 62)

    for i, name in enumerate(names):
        print(
            f"{name}: "
            f"CW={cw['integrated'][i]:+8.2f}° | "
            f"CCW={ccw['integrated'][i]:+8.2f}°"
        )

    # The yaw axis should respond strongly to BOTH rotations,
    # with opposite signs.
    strengths = [
        min(
            abs(cw["integrated"][i]),
            abs(ccw["integrated"][i])
        )
        for i in range(3)
    ]

    yaw_i = max(range(3), key=lambda i: strengths[i])

    cw_angle = cw["integrated"][yaw_i]
    ccw_angle = ccw["integrated"][yaw_i]

    print()
    print(f"Strongest candidate yaw axis: {names[yaw_i]}")

    if cw_angle * ccw_angle >= 0:
        print(
            "WARNING: Clockwise and counter-clockwise tests "
            "did not produce opposite integrated signs."
        )
        print("Repeat the tests before selecting the yaw axis.")
        return

    # Rover heading convention used by the mapper:
    # positive heading = counter-clockwise.
    yaw_sign = +1 if ccw_angle > 0 else -1

    print()
    print("PROVISIONAL MAPPER SETTINGS")
    print(f'GYRO_YAW_AXIS = "{names[yaw_i].lower()}"')
    print(f"GYRO_YAW_SIGN = {yaw_sign:+d}")

    print()
    print("Expected for a 90° physical rotation:")
    print(f"Clockwise:        {-90:+.1f}°")
    print(f"Counter-clockwise: {90:+.1f}°")

    print("Measured using candidate axis:")
    print(f"Clockwise:        {yaw_sign * cw_angle:+.1f}°")
    print(f"Counter-clockwise: {yaw_sign * ccw_angle:+.1f}°")

    print()
    print(
        "These are provisional results. Confirm the physical "
        "rotation angle and mounting before using them in SLAM."
    )


def wait_for_enter(message):
    input(f"\n{message}\nPress ENTER when ready...")


def main():
    print()
    print("=" * 62)
    print("       MPU6500 YAW CALIBRATION")
    print("=" * 62)

    print()
    print("Listening for odometry ESP32 on UDP port", ODOM_PORT)
    print("Waiting for the first IMU packet...")

    arrival, address, packet = receive_packet()

    print()
    print(f"Connected to odometry stream from {address[0]}")
    print("First gyro reading (degrees/second):")

    gx, gy, gz = gyro_dps(packet)

    print(f"GX={gx:+.3f}, GY={gy:+.3f}, GZ={gz:+.3f}")

    print()
    print("IMPORTANT:")
    print("1. Let the ESP32 finish its startup gyro calibration.")
    print("2. Keep the rover flat on the floor.")
    print("3. Rotate the WHOLE rover, not just the LiDAR.")
    print("4. Do not tilt the rover during yaw tests.")
    print("5. Perform each rotation during its recording window.")

    wait_for_enter(
        "TEST 1: Keep the rover COMPLETELY STILL for 10 seconds."
    )
    stationary = collect(10.0, "TEST 1: STATIONARY DRIFT")

    wait_for_enter(
        "TEST 2: Rotate the rover exactly 90° CLOCKWISE "
        "during the next 8 seconds."
    )
    clockwise = collect(8.0, "TEST 2: 90° CLOCKWISE")

    wait_for_enter(
        "TEST 3: Rotate the rover exactly 90° COUNTER-CLOCKWISE "
        "during the next 8 seconds."
    )
    counterclockwise = collect(
        8.0,
        "TEST 3: 90° COUNTER-CLOCKWISE"
    )

    print_comparison(clockwise, counterclockwise)

    wait_for_enter(
        "TEST 4: Rotate the rover exactly 360° COUNTER-CLOCKWISE "
        "during the next 15 seconds."
    )
    full_turn = collect(15.0, "TEST 4: 360° COUNTER-CLOCKWISE")

    print()
    print("=" * 62)
    print("FINAL SUMMARY")
    print("=" * 62)

    if stationary:
        print(
            "Stationary integrated angles:",
            [round(v, 2) for v in stationary["integrated"]]
        )

    if clockwise:
        print(
            "90° CW integrated angles:",
            [round(v, 2) for v in clockwise["integrated"]]
        )

    if counterclockwise:
        print(
            "90° CCW integrated angles:",
            [round(v, 2) for v in counterclockwise["integrated"]]
        )

    if full_turn:
        print(
            "360° CCW integrated angles:",
            [round(v, 2) for v in full_turn["integrated"]]
        )

    print()
    print("Copy these results into ChatGPT.")

    sock.close()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nCalibration interrupted.")
    finally:
        sock.close()