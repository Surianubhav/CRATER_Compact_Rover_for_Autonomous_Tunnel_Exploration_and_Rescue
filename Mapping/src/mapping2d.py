import socket
import json
import threading
import math
import time

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap


# ============================================================
# NETWORK
# ============================================================

LIDAR_PORT = 4211
ODOM_PORT = 4212

BUFFER_SIZE = 4096


# ============================================================
# ROVER PARAMETERS
# ============================================================

# IMPORTANT:
# AS5600 IS ON MOTOR SHAFT.
#
# Replace this after calibration.
#
# Example only:
# If one complete motor-shaft revolution moves the tread 0.020 m:
#
# METERS_PER_MOTOR_REV = 0.020

LEFT_METERS_PER_REV = 0.147699
RIGHT_METERS_PER_REV = 0.148708

LEFT_DIRECTION = -1
RIGHT_DIRECTION = +1

# Distance between left/right tread centerlines

TRACK_WIDTH_M = 0.180


# ============================================================
# IMU
# ============================================================

# MPU6500 configured to ±2g
ACCEL_LSB_PER_G = 16384.0

# MPU6500 configured to ±250 deg/s
GYRO_LSB_PER_DPS = 131.0


# ============================================================
# IMU AXIS CONFIGURATION
# ============================================================
#
# We will calibrate these from the physical mounting.
#
# Current assumption:
#
#       FRONT
#         ↑
#         Y
#
#        MPU
#
# Z = up
#
# If your breakout orientation differs, change these.
#

ACCEL_FORWARD_AXIS = "y"
ACCEL_FORWARD_SIGN = 1.0

ACCEL_RIGHT_AXIS = "x"
ACCEL_RIGHT_SIGN = 1.0

ACCEL_UP_AXIS = "z"
ACCEL_UP_SIGN = 1.0

GYRO_YAW_AXIS = "z"
GYRO_YAW_SIGN = 1.0


# ============================================================
# LIDAR
# ============================================================

LIDAR_ANGLE_OFFSET_DEG = 0.0

LIDAR_OFFSET_X_M = 0.0
LIDAR_OFFSET_Y_M = 0.0


# ============================================================
# MAP
# ============================================================

MAP_SIZE_M = 100.0
MAP_RESOLUTION = 0.05

MAP_CELLS = int(
    MAP_SIZE_M / MAP_RESOLUTION
)

MAP_CENTER = MAP_CELLS // 2


# Log-odds map

log_odds = np.zeros(
    (MAP_CELLS, MAP_CELLS),
    dtype=np.float32
)


# Occupancy parameters

LO_FREE = -0.25
LO_OCCUPIED = 0.90

LO_MIN = -4.0
LO_MAX = 4.0


# ============================================================
# TRAIL
# ============================================================

trail_x = []
trail_y = []

MAX_TRAIL = 20000


# ============================================================
# THREAD STATE
# ============================================================

state_lock = threading.Lock()

latest_lidar = None
latest_odom = None

running = True


# ============================================================
# POSE
# ============================================================

x = 0.0
y = 0.0

heading = 0.0

velocity = 0.0

imu_velocity = 0.0

pose_initialized = False


# ============================================================
# ENCODERS
# ============================================================

previous_left = None
previous_right = None

previous_time = None


# ============================================================
# IMU
# ============================================================

previous_imu_time = None

gyro_heading = 0.0

roll = 0.0
pitch = 0.0


# ============================================================
# SLIP
# ============================================================

slip_score = 0.0

encoder_velocity = 0.0

accel_velocity = 0.0


# ============================================================
# HELPERS
# ============================================================

def get_axis(packet_value, axis):

    if axis == "x":
        return packet_value[0]

    if axis == "y":
        return packet_value[1]

    return packet_value[2]


def normalize_angle(angle):

    return math.atan2(
        math.sin(angle),
        math.cos(angle)
    )


def encoder_angle_difference(current, previous):

    delta = current - previous

    if delta > 2048:
        delta -= 4096

    elif delta < -2048:
        delta += 4096

    return delta


# ============================================================
# UDP — LIDAR
# ============================================================

def lidar_receiver():

    global latest_lidar

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
        ("0.0.0.0", LIDAR_PORT)
    )

    print(
        f"[LIDAR] UDP {LIDAR_PORT}"
    )

    while running:

        try:

            data, addr = sock.recvfrom(
                BUFFER_SIZE
            )

            packet = json.loads(
                data.decode()
            )

            with state_lock:
                latest_lidar = packet

        except Exception as e:

            print(
                "[LIDAR ERROR]",
                e
            )


# ============================================================
# UDP — ODOMETRY
# ============================================================

def odom_receiver():

    global latest_odom

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
        ("0.0.0.0", ODOM_PORT)
    )

    print(
        f"[ODOM] UDP {ODOM_PORT}"
    )

    while running:

        try:

            data, addr = sock.recvfrom(
                BUFFER_SIZE
            )

            packet = json.loads(
                data.decode()
            )

            with state_lock:
                latest_odom = packet

        except Exception as e:

            print(
                "[ODOM ERROR]",
                e
            )


# ============================================================
# UPDATE IMU
# ============================================================

def update_imu(packet):

    global previous_imu_time

    global gyro_heading

    global roll
    global pitch

    global imu_velocity

    global accel_velocity

    global slip_score


    if packet is None:
        return


    if not packet.get(
        "imuOK",
        False
    ):
        return


    now = time.monotonic()


    if previous_imu_time is None:

        previous_imu_time = now

        return


    dt = now - previous_imu_time

    previous_imu_time = now


    if dt <= 0 or dt > 0.2:
        return


    # --------------------------------------------------------
    # Raw accelerometer
    # --------------------------------------------------------

    raw_accel = np.array([
        float(packet.get("ax", 0)),
        float(packet.get("ay", 0)),
        float(packet.get("az", 0))
    ])


    accel_g = raw_accel / ACCEL_LSB_PER_G

    accel = accel_g * 9.80665


    # --------------------------------------------------------
    # Gyroscope
    # --------------------------------------------------------

    raw_gyro = np.array([
        float(packet.get("gx", 0)),
        float(packet.get("gy", 0)),
        float(packet.get("gz", 0))
    ])


    gyro_dps = (
        raw_gyro /
        GYRO_LSB_PER_DPS
    )


    gyro = np.radians(
        gyro_dps
    )


    # --------------------------------------------------------
    # Extract axes
    # --------------------------------------------------------

    forward = (
        get_axis(
            accel,
            ACCEL_FORWARD_AXIS
        )
        *
        ACCEL_FORWARD_SIGN
    )


    right = (
        get_axis(
            accel,
            ACCEL_RIGHT_AXIS
        )
        *
        ACCEL_RIGHT_SIGN
    )


    up = (
        get_axis(
            accel,
            ACCEL_UP_AXIS
        )
        *
        ACCEL_UP_SIGN
    )


    yaw_rate = (
        get_axis(
            gyro,
            GYRO_YAW_AXIS
        )
        *
        GYRO_YAW_SIGN
    )


    # --------------------------------------------------------
    # Integrate yaw gyro
    # --------------------------------------------------------

    gyro_heading += (
        yaw_rate * dt
    )

    gyro_heading = normalize_angle(
        gyro_heading
    )


    # --------------------------------------------------------
    # Estimate roll/pitch from gravity
    # --------------------------------------------------------

    measured_roll = math.atan2(
        right,
        up
    )


    measured_pitch = math.atan2(
        -forward,
        math.sqrt(
            right * right +
            up * up
        )
    )


    # Complementary filter

    alpha = 0.98

    roll = (
        alpha * roll +
        (1 - alpha) * measured_roll
    )

    pitch = (
        alpha * pitch +
        (1 - alpha) * measured_pitch
    )


    # --------------------------------------------------------
    # Gravity compensation
    # --------------------------------------------------------
    #
    # Approximate forward gravity component.
    #
    # During pitch:
    #
    # gravity_forward ≈ g * sin(pitch)
    #

    gravity_forward = (
        9.80665 *
        math.sin(pitch)
    )


    linear_forward_accel = (
        forward -
        gravity_forward
    )


    # Ignore tiny sensor noise

    if abs(linear_forward_accel) < 0.12:
        linear_forward_accel = 0.0


    # --------------------------------------------------------
    # Integrate acceleration
    # --------------------------------------------------------

    accel_velocity += (
        linear_forward_accel *
        dt
    )


    # --------------------------------------------------------
    # Dampen IMU drift
    # --------------------------------------------------------

    accel_velocity *= 0.995


    # --------------------------------------------------------
    # Slip indicator
    # --------------------------------------------------------

    velocity_difference = abs(
        encoder_velocity -
        accel_velocity
    )


    # Soft slip score

    slip_target = min(
        velocity_difference / 0.5,
        1.0
    )


    slip_score = (
        0.95 * slip_score +
        0.05 * slip_target
    )


# ============================================================
# UPDATE ENCODER ODOMETRY
# ============================================================

def update_odometry(packet):

    global previous_left
    global previous_right
    global previous_time

    global x
    global y
    global heading

    global encoder_velocity


    if packet is None:
        return


    if not packet.get(
        "leftOK",
        False
    ):
        return


    if not packet.get(
        "rightOK",
        False
    ):
        return


    left = int(
        packet["left"]
    )

    right = int(
        packet["right"]
    )


    now = time.monotonic()


    if previous_left is None:

        previous_left = left
        previous_right = right
        previous_time = now

        return


    dt = now - previous_time

    previous_time = now


    if dt <= 0 or dt > 0.2:
        previous_left = left
        previous_right = right
        return


    # --------------------------------------------------------
    # AS5600 angular displacement
    # --------------------------------------------------------

    dl_counts = encoder_angle_difference(
        left,
        previous_left
    )

    dr_counts = encoder_angle_difference(
        right,
        previous_right
    )


    previous_left = left
    previous_right = right


    # --------------------------------------------------------
    # Motor shaft revolutions
    # --------------------------------------------------------

    left_revs = (
        dl_counts /
        4096.0
    )

    right_revs = (
        dr_counts /
        4096.0
    )


    # --------------------------------------------------------
    # Convert to tread movement
    # --------------------------------------------------------

    dl = left_revs * LEFT_METERS_PER_REV * LEFT_DIRECTION
    dr = right_revs * RIGHT_METERS_PER_REV * RIGHT_DIRECTION


    # --------------------------------------------------------
    # Skid-steer kinematics
    # --------------------------------------------------------

    forward_distance = (
        dl + dr
    ) / 2.0


    dtheta_encoder = (
        dr - dl
    ) / TRACK_WIDTH_M


    # --------------------------------------------------------
    # Encoder velocity
    # --------------------------------------------------------

    encoder_velocity = (
        forward_distance /
        dt
    )


    # --------------------------------------------------------
    # IMU-based heading correction
    # --------------------------------------------------------
    #
    # We don't trust either source completely.
    #
    # Small slip:
    #       mostly encoder
    #
    # Large slip:
    #       more gyro
    #

    slip_weight = np.clip(
        slip_score,
        0.0,
        0.9
    )


    encoder_heading = (
        heading +
        dtheta_encoder
    )


    gyro_weight = (
        0.15 +
        0.70 * slip_weight
    )


    encoder_weight = (
        1.0 -
        gyro_weight
    )


    heading = normalize_angle(

        encoder_weight *
        encoder_heading

        +

        gyro_weight *
        gyro_heading
    )


    # --------------------------------------------------------
    # Forward displacement
    # --------------------------------------------------------
    #
    # As slip increases, reduce encoder displacement.
    #

    motion_confidence = (
        1.0 -
        0.55 * slip_weight
    )


    corrected_distance = (
        forward_distance *
        motion_confidence
    )


    # --------------------------------------------------------
    # Integrate position
    # --------------------------------------------------------

    x += (
        corrected_distance *
        math.cos(heading)
    )


    y += (
        corrected_distance *
        math.sin(heading)
    )


# ============================================================
# WORLD → MAP
# ============================================================

def world_to_grid(wx, wy):

    gx = int(
        wx /
        MAP_RESOLUTION
    ) + MAP_CENTER

    gy = int(
        wy /
        MAP_RESOLUTION
    ) + MAP_CENTER

    return gx, gy


# ============================================================
# RAY TRACE
# ============================================================

def ray_cells(
    x0,
    y0,
    x1,
    y1
):

    dx = x1 - x0
    dy = y1 - y0

    steps = int(
        max(
            abs(dx),
            abs(dy)
        )
    )

    if steps <= 0:
        return []

    xs = np.linspace(
        x0,
        x1,
        steps
    )

    ys = np.linspace(
        y0,
        y1,
        steps
    )

    return zip(
        xs.astype(int),
        ys.astype(int)
    )


# ============================================================
# UPDATE OCCUPANCY GRID
# ============================================================

def update_map(
    lidar_packet
):

    if lidar_packet is None:
        return


    try:

        distance_cm = float(
            lidar_packet["distance"]
        )

        angle_deg = float(
            lidar_packet["angle"]
        )

    except:

        return


    # --------------------------------------------------------
    # Filter
    # --------------------------------------------------------

    if distance_cm <= 2:
        return

    if distance_cm > 1200:
        return


    distance = (
        distance_cm /
        100.0
    )


    # --------------------------------------------------------
    # LiDAR angle
    # --------------------------------------------------------

    angle = math.radians(
        angle_deg +
        LIDAR_ANGLE_OFFSET_DEG
    )


    # --------------------------------------------------------
    # Point relative to rover
    # --------------------------------------------------------

    local_x = (
        distance *
        math.cos(angle)
    )

    local_y = (
        distance *
        math.sin(angle)
    )


    local_x += LIDAR_OFFSET_X_M
    local_y += LIDAR_OFFSET_Y_M


    # --------------------------------------------------------
    # Rotate into world
    # --------------------------------------------------------

    c = math.cos(
        heading
    )

    s = math.sin(
        heading
    )


    world_x = (
        x +
        local_x * c -
        local_y * s
    )


    world_y = (
        y +
        local_x * s +
        local_y * c
    )


    # --------------------------------------------------------
    # Rover cell
    # --------------------------------------------------------

    rover_gx, rover_gy = world_to_grid(
        x,
        y
    )


    hit_gx, hit_gy = world_to_grid(
        world_x,
        world_y
    )


    # --------------------------------------------------------
    # Ray trace FREE cells
    # --------------------------------------------------------

    for cx, cy in ray_cells(
        rover_gx,
        rover_gy,
        hit_gx,
        hit_gy
    ):

        if (
            0 <= cx < MAP_CELLS and
            0 <= cy < MAP_CELLS
        ):

            log_odds[
                cy,
                cx
            ] += LO_FREE


    # --------------------------------------------------------
    # Mark obstacle
    # --------------------------------------------------------

    if (
        0 <= hit_gx < MAP_CELLS and
        0 <= hit_gy < MAP_CELLS
    ):

        log_odds[
            hit_gy,
            hit_gx
        ] += LO_OCCUPIED


    # Clamp

    np.clip(
        log_odds,
        LO_MIN,
        LO_MAX,
        out=log_odds
    )


# ============================================================
# DISPLAY
# ============================================================

def occupancy_image():

    image = np.zeros(
        (MAP_CELLS, MAP_CELLS)
    )


    # Unknown
    image[:] = 0.08


    # Free
    free = log_odds < -0.3

    image[free] = 0.18


    # Occupied
    occupied = log_odds > 0.5

    image[occupied] = 0.95


    return image


# ============================================================
# MAIN
# ============================================================

def main():

    global latest_lidar
    global latest_odom

    # --------------------------------------------------------
    # Receivers
    # --------------------------------------------------------

    threading.Thread(
        target=lidar_receiver,
        daemon=True
    ).start()


    threading.Thread(
        target=odom_receiver,
        daemon=True
    ).start()


    time.sleep(1)


    print()
    print("======================================")
    print("       MINE ROVER SLAM SYSTEM")
    print("======================================")
    print()
    print(
        "Track width:",
        TRACK_WIDTH_M,
        "m"
    )
    print(
        "Meters / motor revolution:",
        METERS_PER_MOTOR_REV
    )
    print()


    # --------------------------------------------------------
    # Dark UI
    # --------------------------------------------------------

    plt.style.use(
        "dark_background"
    )


    fig, ax = plt.subplots(
        figsize=(12, 8)
    )


    fig.patch.set_facecolor(
        "#0b1014"
    )

    ax.set_facecolor(
        "#0b1014"
    )


    # --------------------------------------------------------
    # Occupancy
    # --------------------------------------------------------

    image = occupancy_image()


    map_display = ax.imshow(
        image,
        cmap=ListedColormap([
            "#0b1014",
            "#1b252b",
            "#d9e0e3"
        ]),
        origin="lower",
        interpolation="nearest"
    )


    # --------------------------------------------------------
    # Grid
    # --------------------------------------------------------

    grid_spacing = int(
        1.0 /
        MAP_RESOLUTION
    )


    ax.set_xticks(
        np.arange(
            0,
            MAP_CELLS,
            grid_spacing
        )
    )


    ax.set_yticks(
        np.arange(
            0,
            MAP_CELLS,
            grid_spacing
        )
    )


    ax.grid(
        True,
        color="#263238",
        linewidth=0.5,
        alpha=0.45
    )


    # --------------------------------------------------------
    # Trail
    # --------------------------------------------------------

    trail_plot, = ax.plot(
        [],
        [],
        color="#36c5f0",
        linewidth=1.6,
        alpha=0.9
    )


    # --------------------------------------------------------
    # Rover
    # --------------------------------------------------------

    rover_plot, = ax.plot(
        [],
        [],
        marker="^",
        markersize=11,
        color="#4da3ff",
        markeredgecolor="#d9f2ff",
        markeredgewidth=0.8
    )


    # --------------------------------------------------------
    # Heading
    # --------------------------------------------------------

    heading_plot, = ax.plot(
        [],
        [],
        color="#5cc8ff",
        linewidth=2
    )


    # --------------------------------------------------------
    # Current LiDAR scan
    # --------------------------------------------------------

    scan_plot, = ax.plot(
        [],
        [],
        linestyle="None",
        marker=".",
        markersize=1.2,
        color="#8aa0aa",
        alpha=0.35
    )


    # --------------------------------------------------------
    # Labels
    # --------------------------------------------------------

    ax.set_title(
        "MAP / SLAM VIEW",
        loc="left",
        fontsize=13,
        color="#dce7eb"
    )


    ax.set_xlabel(
        "X (m)",
        color="#71838c"
    )


    ax.set_ylabel(
        "Y (m)",
        color="#71838c"
    )


    ax.tick_params(
        colors="#60727a"
    )


    # ========================================================
    # LOOP
    # ========================================================

    while True:

        try:

            # ------------------------------------------------
            # Retrieve newest packets
            # ------------------------------------------------

            with state_lock:

                odom = latest_odom
                lidar = latest_lidar

                latest_odom = None
                latest_lidar = None


            # ------------------------------------------------
            # IMU first
            # ------------------------------------------------

            if odom is not None:

                update_imu(
                    odom
                )

                update_odometry(
                    odom
                )


            # ------------------------------------------------
            # LiDAR
            # ------------------------------------------------

            if lidar is not None:

                update_map(
                    lidar
                )


            # ------------------------------------------------
            # Trail
            # ------------------------------------------------

            trail_x.append(
                x
            )

            trail_y.append(
                y
            )


            if len(trail_x) > MAX_TRAIL:

                del trail_x[
                    :-MAX_TRAIL
                ]

                del trail_y[
                    :-MAX_TRAIL
                ]


            # ------------------------------------------------
            # Update map
            # ------------------------------------------------

            map_display.set_data(
                occupancy_image()
            )


            # ------------------------------------------------
            # Rover position
            # ------------------------------------------------

            gx, gy = world_to_grid(
                x,
                y
            )


            rover_plot.set_data(
                [gx],
                [gy]
            )


            # ------------------------------------------------
            # Heading
            # ------------------------------------------------

            heading_length = (
                0.5 /
                MAP_RESOLUTION
            )


            hx = (
                gx +
                heading_length *
                math.cos(heading)
            )


            hy = (
                gy +
                heading_length *
                math.sin(heading)
            )


            heading_plot.set_data(
                [gx, hx],
                [gy, hy]
            )


            # ------------------------------------------------
            # Trail in grid coordinates
            # ------------------------------------------------

            trail_gx = []
            trail_gy = []


            for tx, ty in zip(
                trail_x[-5000:],
                trail_y[-5000:]
            ):

                tgx, tgy = world_to_grid(
                    tx,
                    ty
                )

                trail_gx.append(
                    tgx
                )

                trail_gy.append(
                    tgy
                )


            trail_plot.set_data(
                trail_gx,
                trail_gy
            )


            # ------------------------------------------------
            # Status
            # ------------------------------------------------

            ax.set_title(
                "MAP / SLAM VIEW   "
                f"| POS {x:.2f}, {y:.2f} m   "
                f"| HDG {math.degrees(heading):.1f}°   "
                f"| SLIP {slip_score * 100:.0f}%",
                loc="left",
                fontsize=12,
                color="#dce7eb"
            )


            fig.canvas.draw_idle()
            fig.canvas.flush_events()


            time.sleep(
                0.03
            )


        except KeyboardInterrupt:

            print(
                "\nStopping mapper..."
            )

            break


        except Exception as e:

            print(
                "[MAP ERROR]",
                e
            )

            time.sleep(
                0.1
            )


    plt.ioff()
    plt.show()


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    main()