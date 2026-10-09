#!/usr/bin/env python3

import socket
import json
import threading
import time
import math

# ============================================================
# CONFIGURATION
# ============================================================

ODOM_PORT = 4212
CONTROL_PORT = 4210

ODOM_ESP_IP = "10.42.0.95"
BROADCAST_IP = "10.42.0.255"

# Your already-calibrated motor-shaft displacement
LEFT_METERS_PER_REV = 0.147699
RIGHT_METERS_PER_REV = 0.148708

# Encoder direction conventions from your 1 m calibration
LEFT_DIRECTION = -1
RIGHT_DIRECTION = +1

# ============================================================
# GLOBAL LATEST ENCODER DATA
# ============================================================

latest_left = None
latest_right = None
latest_seq = None
latest_time = None

data_lock = threading.Lock()
receiver_running = True


# ============================================================
# UDP RECEIVER
# ============================================================

def encoder_receiver():
    global latest_left
    global latest_right
    global latest_seq
    global latest_time

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
        sock.bind(("0.0.0.0", ODOM_PORT))
    except OSError as e:
        print(f"\nERROR: Could not bind UDP port {ODOM_PORT}: {e}")
        return

    sock.settimeout(0.5)

    print(f"Listening for odometry packets on UDP {ODOM_PORT}...")

    while receiver_running:
        try:
            data, addr = sock.recvfrom(4096)

            msg = json.loads(data.decode())

            if msg.get("device") != "odom":
                continue

            if "left" not in msg or "right" not in msg:
                continue

            with data_lock:
                latest_left = float(msg["left"])
                latest_right = float(msg["right"])
                latest_seq = msg.get("seq")
                latest_time = time.monotonic()

        except socket.timeout:
            continue

        except Exception as e:
            print(f"\nReceiver error: {e}")


# ============================================================
# GET LATEST ENCODER VALUES
# ============================================================

def get_encoder_values():

    with data_lock:
        if latest_left is None or latest_right is None:
            return None, None, None

        return latest_left, latest_right, latest_seq


# ============================================================
# SEND START COMMAND
# ============================================================

def send_start():

    print("\nSending START to odometry ESP32...")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    try:
        # Direct command
        sock.sendto(
            b"START",
            (ODOM_ESP_IP, CONTROL_PORT)
        )

        print(
            f"START sent directly to "
            f"{ODOM_ESP_IP}:{CONTROL_PORT}"
        )

        # Broadcast command
        sock.sendto(
            b"START",
            (BROADCAST_IP, CONTROL_PORT)
        )

        print(
            f"START broadcast to "
            f"{BROADCAST_IP}:{CONTROL_PORT}"
        )

    except Exception as e:
        print(f"WARNING: Could not send START: {e}")

    finally:
        sock.close()


# ============================================================
# WAIT FOR ENCODER DATA
# ============================================================

def wait_for_encoder():

    print("\nWaiting for odometry packets...")

    while True:

        left, right, seq = get_encoder_values()

        if left is not None and right is not None:

            print("\nODOMETRY ESP32 CONNECTED!")
            print(f"Left  = {left:.6f} rev")
            print(f"Right = {right:.6f} rev")

            return left, right

        time.sleep(0.05)


# ============================================================
# WAIT FOR STABLE DATA
# ============================================================

def wait_for_stable_data(seconds=0.5):

    print("\nWaiting for stable encoder data...")

    time.sleep(seconds)

    left, right, seq = get_encoder_values()

    if left is None:
        raise RuntimeError("Lost encoder data.")

    return left, right


# ============================================================
# CALCULATE TRACK WIDTH
# ============================================================

def calculate_track_width(
    start_left,
    start_right,
    end_left,
    end_right,
    angle_deg
):

    # Continuous revolution differences
    delta_left_rev = end_left - start_left
    delta_right_rev = end_right - start_right

    # Convert motor-shaft revolutions to physical displacement
    left_distance = (
        delta_left_rev
        * LEFT_METERS_PER_REV
        * LEFT_DIRECTION
    )

    right_distance = (
        delta_right_rev
        * RIGHT_METERS_PER_REV
        * RIGHT_DIRECTION
    )

    theta = math.radians(abs(angle_deg))

    if theta < 1e-6:
        raise ValueError("Rotation angle is too small.")

    # Differential-drive relationship:
    #
    # theta = (right_distance - left_distance) / track_width
    #
    # Therefore:
    #
    # track_width =
    # |right_distance - left_distance| / |theta|

    track_width = abs(
        right_distance - left_distance
    ) / theta

    return (
        delta_left_rev,
        delta_right_rev,
        left_distance,
        right_distance,
        track_width
    )


# ============================================================
# ONE CALIBRATION TEST
# ============================================================

def run_test(test_number):

    print("\n" + "=" * 70)
    print(f"TRACK WIDTH TEST {test_number}")
    print("=" * 70)

    print("""
PHYSICAL SETUP:

1. Put the rover on a surface where it can rotate.
2. Mark the FRONT of the rover and a reference line.
3. The rover should rotate approximately in place.
4. Do NOT use the MPU to judge the angle.
5. Use the physical floor/reference mark.
""")

    while True:

        direction = input(
            "Will this rotation be CW or CCW? [CW/CCW]: "
        ).strip().upper()

        if direction in ("CW", "CCW"):
            break

        print("Please enter CW or CCW.")

    while True:

        try:
            angle_deg = float(
                input(
                    "Enter the physical rotation angle "
                    "(normally 360): "
                )
            )

            if abs(angle_deg) > 0:
                break

        except ValueError:
            pass

        print("Please enter a valid angle.")

    # --------------------------------------------------------
    # Make sure receiver is still getting data
    # --------------------------------------------------------

    start_left, start_right = wait_for_stable_data()

    print("\nSTART ENCODERS")
    print(f"Left :  {start_left:.6f} rev")
    print(f"Right:  {start_right:.6f} rev")

    print("\n>>> ROTATE THE ROVER NOW <<<")
    print(
        f"\nRotate exactly {angle_deg:.1f}° {direction}."
    )

    print(
        "\nThe encoder receiver is running continuously "
        "in the background."
    )

    input(
        "\nWhen the rover has returned to the physical "
        "reference orientation,\n"
        "press ENTER to finish this test..."
    )

    # --------------------------------------------------------
    # IMPORTANT:
    #
    # The background thread has been collecting packets
    # continuously while input() was waiting.
    #
    # We now take the MOST RECENT encoder values.
    # --------------------------------------------------------

    time.sleep(0.05)

    end_left, end_right = wait_for_stable_data(0.0)

    print("\nEND ENCODERS")
    print(f"Left :  {end_left:.6f} rev")
    print(f"Right:  {end_right:.6f} rev")

    # --------------------------------------------------------
    # Calculate
    # --------------------------------------------------------

    (
        delta_left_rev,
        delta_right_rev,
        left_distance,
        right_distance,
        track_width
    ) = calculate_track_width(
        start_left,
        start_right,
        end_left,
        end_right,
        angle_deg
    )

    print("\nRESULT")
    print("-" * 70)

    print(
        f"Left encoder change : "
        f"{delta_left_rev:+.6f} rev"
    )

    print(
        f"Right encoder change: "
        f"{delta_right_rev:+.6f} rev"
    )

    print(
        f"Left displacement   : "
        f"{left_distance:+.4f} m"
    )

    print(
        f"Right displacement  : "
        f"{right_distance:+.4f} m"
    )

    signed_angle = (
        -abs(angle_deg)
        if direction == "CW"
        else abs(angle_deg)
    )

    print(
        f"Physical rotation   : "
        f"{signed_angle:+.1f}°"
    )

    print(
        f"\n>>> EFFECTIVE TRACK WIDTH = "
        f"{track_width:.4f} m "
        f"({track_width * 1000:.1f} mm)"
    )

    return track_width


# ============================================================
# MAIN
# ============================================================

def main():

    global receiver_running

    print("=" * 70)
    print("       TRACK WIDTH CALIBRATION")
    print("=" * 70)

    print("\nEncoder calibration being used:")
    print(
        f"Left  = {LEFT_METERS_PER_REV:.6f} m/rev"
    )
    print(
        f"Right = {RIGHT_METERS_PER_REV:.6f} m/rev"
    )

    print("\nEncoder direction:")
    print(f"Left  = {LEFT_DIRECTION:+d}")
    print(f"Right = {RIGHT_DIRECTION:+d}")

    # --------------------------------------------------------
    # START BACKGROUND RECEIVER FIRST
    # --------------------------------------------------------

    receiver_thread = threading.Thread(
        target=encoder_receiver,
        daemon=True
    )

    receiver_thread.start()

    time.sleep(0.2)

    # --------------------------------------------------------
    # Tell ESP32 to reset/start
    # --------------------------------------------------------

    send_start()

    # --------------------------------------------------------
    # Wait for actual encoder packets
    # --------------------------------------------------------

    wait_for_encoder()

    # --------------------------------------------------------
    # Tests
    # --------------------------------------------------------

    results = []

    try:

        for test_number in range(1, 6):

            width = run_test(test_number)

            if width > 0:
                results.append(width)

            if test_number < 5:

                print(
                    "\nPrepare the rover for the next test."
                )

                input(
                    "Press ENTER when ready..."
                )

    except KeyboardInterrupt:

        print("\n\nCalibration interrupted.")

    finally:

        receiver_running = False

    # --------------------------------------------------------
    # FINAL RESULT
    # --------------------------------------------------------

    print("\n")
    print("=" * 70)
    print("FINAL TRACK WIDTH RESULTS")
    print("=" * 70)

    if not results:

        print(
            "\nNo valid measurements were collected."
        )

        return

    print("\nIndividual measurements:")

    for i, width in enumerate(results, 1):

        print(
            f"Test {i}: "
            f"{width:.4f} m "
            f"({width * 1000:.1f} mm)"
        )

    average = sum(results) / len(results)

    print("\n----------------------------------------")

    print(
        f"Average effective track width:"
    )

    print(
        f"{average:.4f} m "
        f"({average * 1000:.1f} mm)"
    )

    print("----------------------------------------")

    print(
        "\nUse this value as TRACK_WIDTH_M "
        "in the SLAM code."
    )


if __name__ == "__main__":
    main()