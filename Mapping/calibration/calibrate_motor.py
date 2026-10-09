import socket
import json
import time

# ============================================================
# CONFIG
# ============================================================

PORT = 4212
BUFFER_SIZE = 4096

COUNTS_PER_REV = 4096


# ============================================================
# ANGLE DELTA
# ============================================================

def wrapped_delta(current, previous):

    delta = current - previous

    if delta > 2048:
        delta -= 4096

    elif delta < -2048:
        delta += 4096

    return delta


# ============================================================
# UDP
# ============================================================

sock = socket.socket(
    socket.AF_INET,
    socket.SOCK_DGRAM
)

sock.setsockopt(
    socket.SOL_SOCKET,
    socket.SO_REUSEADDR,
    1
)

sock.bind(
    ("0.0.0.0", PORT)
)

sock.settimeout(0.1)


print()
print("==========================================")
print("     MOTOR / TREAD REVOLUTION CALIBRATION")
print("==========================================")
print()
print(f"Listening on UDP {PORT}...")
print()
print("Waiting for odometry data...")


# ============================================================
# WAIT FOR PACKET
# ============================================================

while True:

    try:

        data, addr = sock.recvfrom(
            BUFFER_SIZE
        )

        packet = json.loads(
            data.decode()
        )

        if (
            packet.get("device") == "odom"
            and packet.get("leftOK", False)
            and packet.get("rightOK", False)
        ):
            break

    except socket.timeout:
        continue


print()
print("Odometry data received.")
print()

print(
    f"Current encoder angles:"
)

print(
    f"LEFT  = {packet['left']}"
)

print(
    f"RIGHT = {packet['right']}"
)

print()

input(
    "Place rover at START and press ENTER..."
)


# ============================================================
# GET FRESH START POSITION
# ============================================================

while True:

    try:

        data, addr = sock.recvfrom(
            BUFFER_SIZE
        )

        packet = json.loads(
            data.decode()
        )

        if (
            packet.get("device") == "odom"
            and packet.get("leftOK", False)
            and packet.get("rightOK", False)
        ):
            break

    except socket.timeout:
        continue


previous_left = int(packet["left"])
previous_right = int(packet["right"])

left_total_counts = 0
right_total_counts = 0


print()
print("==========================================")
print("CALIBRATION STARTED")
print("==========================================")
print()
print("Move the rover EXACTLY 1.000 m forward.")
print()
print("The script will continuously count")
print("motor-shaft revolutions.")
print()
print("Press ENTER when you reach 1.000 m.")
print()


# ============================================================
# CALIBRATION LOOP
# ============================================================

import select
import sys

while True:

    # --------------------------------------------------------
    # Check whether user pressed ENTER
    # --------------------------------------------------------

    ready, _, _ = select.select(
        [sys.stdin],
        [],
        [],
        0
    )

    if ready:

        sys.stdin.readline()

        break


    # --------------------------------------------------------
    # Receive packet
    # --------------------------------------------------------

    try:

        data, addr = sock.recvfrom(
            BUFFER_SIZE
        )

        packet = json.loads(
            data.decode()
        )

    except socket.timeout:

        continue

    except Exception:

        continue


    # --------------------------------------------------------
    # Validate
    # --------------------------------------------------------

    if (
        packet.get("device") != "odom"
        or not packet.get("leftOK", False)
        or not packet.get("rightOK", False)
    ):
        continue


    current_left = int(
        packet["left"]
    )

    current_right = int(
        packet["right"]
    )


    # --------------------------------------------------------
    # Calculate incremental angle
    # --------------------------------------------------------

    left_delta = wrapped_delta(
        current_left,
        previous_left
    )

    right_delta = wrapped_delta(
        current_right,
        previous_right
    )


    # --------------------------------------------------------
    # Accumulate
    # --------------------------------------------------------

    left_total_counts += left_delta
    right_total_counts += right_delta


    # --------------------------------------------------------
    # Update previous
    # --------------------------------------------------------

    previous_left = current_left
    previous_right = current_right


    # --------------------------------------------------------
    # Convert to revolutions
    # --------------------------------------------------------

    left_revolutions = (
        left_total_counts /
        COUNTS_PER_REV
    )

    right_revolutions = (
        right_total_counts /
        COUNTS_PER_REV
    )


    # --------------------------------------------------------
    # Display
    # --------------------------------------------------------

    print(
        f"\r"
        f"L: {left_revolutions:+9.3f} rev   "
        f"R: {right_revolutions:+9.3f} rev",
        end="",
        flush=True
    )


# ============================================================
# RESULT
# ============================================================

left_revolutions = (
    left_total_counts /
    COUNTS_PER_REV
)

right_revolutions = (
    right_total_counts /
    COUNTS_PER_REV
)


print()
print()
print("==========================================")
print("CALIBRATION RESULT")
print("==========================================")
print()

print(
    f"Left motor revolutions : "
    f"{left_revolutions:.6f}"
)

print(
    f"Right motor revolutions: "
    f"{right_revolutions:.6f}"
)

print()


# ============================================================
# METERS PER REV
# ============================================================

if abs(left_revolutions) > 0.01:

    left_m_per_rev = (
        1.0 /
        abs(left_revolutions)
    )

    print(
        f"LEFT  = "
        f"{left_m_per_rev:.6f} m/rev"
    )


if abs(right_revolutions) > 0.01:

    right_m_per_rev = (
        1.0 /
        abs(right_revolutions)
    )

    print(
        f"RIGHT = "
        f"{right_m_per_rev:.6f} m/rev"
    )


print()
print("------------------------------------------")
print("IMPORTANT")
print("------------------------------------------")
print()
print("Positive/negative signs only indicate")
print("encoder rotation direction.")
print()
print("For the mapper we can normalize both")
print("directions so forward movement is positive.")
print()