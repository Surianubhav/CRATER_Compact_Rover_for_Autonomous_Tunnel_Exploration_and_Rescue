import socket
import math
import time

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from matplotlib.widgets import Button


# ============================================================
# CONFIGURATION
# ============================================================

UDP_IP = "0.0.0.0"
UDP_PORT = 4210

# Maximum LiDAR range displayed, in centimeters
MAX_RANGE_CM = 800

# Minimum valid distance
MIN_RANGE_CM = 5

# Ignore measurements farther than this
# Set to MAX_RANGE_CM if you don't want additional filtering
VALID_MAX_CM = 800

# Angle correction.
# Change this if the physical 0° direction isn't where you
# want the map's 0° direction.
ANGLE_OFFSET = 0.0

# Map point size
POINT_SIZE = 3

# Transparency of accumulated points
MAP_ALPHA = 0.85


# ============================================================
# UDP
# ============================================================

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind((UDP_IP, UDP_PORT))
sock.setblocking(False)

print()
print("==========================================")
print("        MINE LiDAR MAPPING SYSTEM")
print("==========================================")
print(f"UDP port : {UDP_PORT}")
print("Waiting for ESP32...")
print()


# ============================================================
# MAP DATA
# ============================================================

map_x = []
map_y = []

current_x = []
current_y = []

previous_angle = None

scan_count = 0
total_points = 0

last_distance = 0
last_angle = 0

scan_start_time = time.time()


# ============================================================
# ROBOT POSE
# ============================================================
#
# IMPORTANT:
#
# Right now the rover is stationary:
#
#     x = 0
#     y = 0
#     heading = 0
#
# Later, encoder + IMU/SLAM data will update these.
#
# The mapper below already uses this pose architecture.
# ============================================================

robot_x = 0.0
robot_y = 0.0
robot_heading = 0.0


# ============================================================
# FIGURE
# ============================================================

plt.style.use("dark_background")

fig = plt.figure(figsize=(12, 8))

ax = fig.add_axes([0.07, 0.10, 0.72, 0.82])

ax.set_title(
    "MINE LiDAR MAP",
    fontsize=18,
    fontweight="bold",
    pad=15
)

ax.set_xlabel("X (cm)")
ax.set_ylabel("Y (cm)")

ax.set_aspect("equal", adjustable="box")

ax.set_xlim(-MAX_RANGE_CM, MAX_RANGE_CM)
ax.set_ylim(-MAX_RANGE_CM, MAX_RANGE_CM)

ax.grid(
    True,
    alpha=0.15,
    linestyle="--"
)


# ============================================================
# MAP PLOT
# ============================================================

map_plot, = ax.plot(
    [],
    [],
    ".",
    markersize=POINT_SIZE,
    alpha=MAP_ALPHA,
    label="Mapped obstacles"
)


# ============================================================
# CURRENT SCAN
# ============================================================

scan_plot, = ax.plot(
    [],
    [],
    ".",
    markersize=4,
    alpha=0.7,
    label="Current scan"
)


# ============================================================
# ROBOT
# ============================================================

robot_plot, = ax.plot(
    [robot_x],
    [robot_y],
    "o",
    markersize=10,
    markeredgewidth=2,
    label="Scanner"
)


# ============================================================
# HEADING LINE
# ============================================================

heading_length = 40

heading_plot, = ax.plot(
    [
        robot_x,
        robot_x + heading_length * math.cos(
            math.radians(robot_heading)
        )
    ],
    [
        robot_y,
        robot_y + heading_length * math.sin(
            math.radians(robot_heading)
        )
    ],
    "-",
    linewidth=2
)


# ============================================================
# LEGEND
# ============================================================

ax.legend(
    loc="upper right",
    framealpha=0.5
)


# ============================================================
# INFORMATION PANEL
# ============================================================

info_ax = fig.add_axes(
    [0.82, 0.48, 0.16, 0.38]
)

info_ax.axis("off")

info_text = info_ax.text(
    0,
    1,
    "",
    verticalalignment="top",
    fontsize=11,
    family="monospace"
)


# ============================================================
# STATUS PANEL
# ============================================================

status_ax = fig.add_axes(
    [0.82, 0.32, 0.16, 0.10]
)

status_ax.axis("off")

status_text = status_ax.text(
    0,
    0.8,
    "● WAITING",
    fontsize=11,
    fontweight="bold"
)


# ============================================================
# CLEAR BUTTON
# ============================================================

clear_ax = fig.add_axes(
    [0.82, 0.20, 0.13, 0.055]
)

clear_button = Button(
    clear_ax,
    "CLEAR MAP"
)


# ============================================================
# SAVE BUTTON
# ============================================================

save_ax = fig.add_axes(
    [0.82, 0.12, 0.13, 0.055]
)

save_button = Button(
    save_ax,
    "SAVE MAP"
)


# ============================================================
# CLEAR MAP
# ============================================================

def clear_map(event):

    global map_x
    global map_y
    global scan_count

    map_x.clear()
    map_y.clear()

    current_x.clear()
    current_y.clear()

    scan_count = 0

    map_plot.set_data([], [])
    scan_plot.set_data([], [])

    print("Map cleared.")


clear_button.on_clicked(clear_map)


# ============================================================
# SAVE MAP
# ============================================================

def save_map(event):

    if len(map_x) == 0:
        print("Nothing to save.")
        return

    filename = (
        time.strftime("mine_map_%Y%m%d_%H%M%S.csv")
    )

    data = np.column_stack(
        (map_x, map_y)
    )

    np.savetxt(
        filename,
        data,
        delimiter=",",
        header="x_cm,y_cm",
        comments=""
    )

    print(f"Map saved: {filename}")


save_button.on_clicked(save_map)


# ============================================================
# POLAR → GLOBAL COORDINATES
# ============================================================

def lidar_to_global(
    distance,
    angle
):

    # Correct sensor angle
    corrected_angle = (
        angle
        + ANGLE_OFFSET
        + robot_heading
    )

    angle_rad = math.radians(
        corrected_angle
    )

    # Local LiDAR coordinates
    local_x = (
        distance *
        math.cos(angle_rad)
    )

    local_y = (
        distance *
        math.sin(angle_rad)
    )

    # Translate into global map
    global_x = (
        robot_x +
        local_x
    )

    global_y = (
        robot_y +
        local_y
    )

    return global_x, global_y


# ============================================================
# READ UDP
# ============================================================

def read_udp():

    global previous_angle
    global scan_count
    global total_points

    global last_distance
    global last_angle
    global scan_start_time

    while True:

        try:

            data, addr = sock.recvfrom(1024)

        except BlockingIOError:

            break

        try:

            message = (
                data
                .decode()
                .strip()
            )

            distance_str, angle_str = (
                message.split(",")
            )

            distance = float(
                distance_str
            )

            angle = float(
                angle_str
            )

        except Exception:

            continue


        # ====================================================
        # VALIDATION
        # ====================================================

        if (
            distance < MIN_RANGE_CM
            or distance > VALID_MAX_CM
        ):
            continue

        if angle < 0 or angle > 360:
            continue


        # ====================================================
        # DETECT NEW REVOLUTION
        # ====================================================

        if previous_angle is not None:

            # 359 → 1
            if (
                previous_angle > 300
                and angle < 60
            ):

                scan_count += 1

                scan_time = (
                    time.time()
                    - scan_start_time
                )

                print(
                    f"Scan #{scan_count:4d} | "
                    f"{len(current_x):4d} points | "
                    f"{scan_time:.2f}s"
                )

                current_x.clear()
                current_y.clear()

                scan_start_time = time.time()


        previous_angle = angle


        # ====================================================
        # CONVERT TO GLOBAL POSITION
        # ====================================================

        x, y = lidar_to_global(
            distance,
            angle
        )


        # ====================================================
        # STORE POINT
        # ====================================================

        current_x.append(x)
        current_y.append(y)

        map_x.append(x)
        map_y.append(y)

        total_points += 1

        last_distance = distance
        last_angle = angle


# ============================================================
# UPDATE DISPLAY
# ============================================================

def update(frame):

    read_udp()


    # Current scan
    scan_plot.set_data(
        current_x,
        current_y
    )


    # Persistent map
    map_plot.set_data(
        map_x,
        map_y
    )


    # Robot position
    robot_plot.set_data(
        [robot_x],
        [robot_y]
    )


    # Heading
    heading_rad = math.radians(
        robot_heading
    )

    heading_plot.set_data(
        [
            robot_x,
            robot_x
            + heading_length
            * math.cos(heading_rad)
        ],
        [
            robot_y,
            robot_y
            + heading_length
            * math.sin(heading_rad)
        ]
    )


    # ========================================================
    # INFORMATION PANEL
    # ========================================================

    info_text.set_text(
        f"""
MINE MAPPING

STATUS
──────────────
Scans       : {scan_count}

Points      : {total_points}

DISTANCE
──────────────
Current     : {last_distance:.1f} cm

ANGLE
──────────────
Current     : {last_angle:.1f}°

POSE
──────────────
X           : {robot_x:.1f} cm
Y           : {robot_y:.1f} cm
Heading     : {robot_heading:.1f}°

UDP
──────────────
Port        : {UDP_PORT}
"""
    )


    if total_points > 0:

        status_text.set_text(
            "● RECEIVING"
        )

    else:

        status_text.set_text(
            "● WAITING"
        )


    return (
        map_plot,
        scan_plot,
        robot_plot,
        heading_plot
    )


# ============================================================
# START
# ============================================================

ani = FuncAnimation(
    fig,
    update,
    interval=30,
    blit=False,
    cache_frame_data=False
)

plt.show()