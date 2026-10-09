import socket
import math
import time

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from matplotlib.widgets import Button


# ============================================================
# CONFIG
# ============================================================

UDP_IP = "0.0.0.0"
UDP_PORT = 4211

# Map dimensions
MAP_SIZE_CM = 1000

# Resolution of each grid cell
# 5 cm = good starting point for testing
CELL_SIZE_CM = 5

# LiDAR limits
MIN_RANGE_CM = 5
MAX_RANGE_CM = 800

# Sensor angle correction
ANGLE_OFFSET = 0.0


# ============================================================
# OCCUPANCY GRID
# ============================================================
#
# Values:
#
# -1 = UNKNOWN
#  0 = FREE
#  1 = OCCUPIED
#
# ============================================================

GRID_SIZE = int(
    (MAP_SIZE_CM * 2) / CELL_SIZE_CM
)

grid = np.full(
    (GRID_SIZE, GRID_SIZE),
    -1,
    dtype=np.int8
)


# Scanner is at the center of the grid
ORIGIN = GRID_SIZE // 2


# ============================================================
# UDP
# ============================================================

sock = socket.socket(
    socket.AF_INET,
    socket.SOCK_DGRAM
)

sock.bind(
    (UDP_IP, UDP_PORT)
)

sock.setblocking(False)

print()
print("==========================================")
print("       STATIONARY OCCUPANCY MAPPER")
print("==========================================")
print(f"UDP port       : {UDP_PORT}")
print(f"Grid resolution: {CELL_SIZE_CM} cm")
print(f"Map size       : {MAP_SIZE_CM * 2} x {MAP_SIZE_CM * 2} cm")
print()
print("Waiting for LiDAR...")
print()


# ============================================================
# ROBOT POSE
# ============================================================
#
# Stationary for now.
#
# Later:
#
# robot_x
# robot_y
# robot_heading
#
# can come from encoder + IMU.
# ============================================================

robot_x = 0.0
robot_y = 0.0
robot_heading = 0.0


# ============================================================
# COORDINATE CONVERSION
# ============================================================

def world_to_grid(x_cm, y_cm):

    gx = int(
        round(
            x_cm / CELL_SIZE_CM
        )
        + ORIGIN
    )

    gy = int(
        round(
            y_cm / CELL_SIZE_CM
        )
        + ORIGIN
    )

    return gx, gy


# ============================================================
# MARK CELL
# ============================================================

def mark_cell(x_cm, y_cm, value):

    gx, gy = world_to_grid(
        x_cm,
        y_cm
    )

    if (
        0 <= gx < GRID_SIZE
        and
        0 <= gy < GRID_SIZE
    ):

        grid[gy, gx] = value


# ============================================================
# RAY TRACE
# ============================================================

def trace_ray(
    distance_cm,
    angle_deg
):

    # Apply angle correction
    angle_deg += ANGLE_OFFSET
    angle_deg += robot_heading

    angle_rad = math.radians(
        angle_deg
    )

    # ========================================================
    # End point of LiDAR measurement
    # ========================================================

    end_x = (
        robot_x
        + distance_cm
        * math.cos(angle_rad)
    )

    end_y = (
        robot_y
        + distance_cm
        * math.sin(angle_rad)
    )


    # ========================================================
    # Sample points along the ray
    # ========================================================

    # One sample approximately every cell
    steps = max(
        1,
        int(
            distance_cm
            / CELL_SIZE_CM
        )
    )


    for i in range(steps):

        t = i / steps

        x = (
            robot_x
            + t
            * distance_cm
            * math.cos(angle_rad)
        )

        y = (
            robot_y
            + t
            * distance_cm
            * math.sin(angle_rad)
        )

        # Everything before the obstacle is FREE
        mark_cell(
            x,
            y,
            0
        )


    # ========================================================
    # Last point is OCCUPIED
    # ========================================================

    mark_cell(
        end_x,
        end_y,
        1
    )


# ============================================================
# UDP READER
# ============================================================

last_distance = 0
last_angle = 0
packet_count = 0


def read_udp():

    global last_distance
    global last_angle
    global packet_count


    while True:

        try:

            data, addr = sock.recvfrom(
                1024
            )

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
        # Validate
        # ====================================================

        if (
            distance < MIN_RANGE_CM
            or
            distance > MAX_RANGE_CM
        ):
            continue


        if (
            angle < 0
            or
            angle > 360
        ):
            continue


        # ====================================================
        # Update occupancy grid
        # ====================================================

        trace_ray(
            distance,
            angle
        )


        last_distance = distance
        last_angle = angle

        packet_count += 1


# ============================================================
# DISPLAY
# ============================================================

plt.style.use(
    "dark_background"
)


fig = plt.figure(
    figsize=(12, 8)
)


ax = fig.add_axes(
    [0.07, 0.10, 0.70, 0.82]
)


ax.set_title(
    "MINE OCCUPANCY MAP",
    fontsize=18,
    fontweight="bold",
    pad=15
)


ax.set_xlabel(
    "X (cm)"
)

ax.set_ylabel(
    "Y (cm)"
)


ax.set_aspect(
    "equal"
)


ax.set_xlim(
    -MAP_SIZE_CM,
    MAP_SIZE_CM
)

ax.set_ylim(
    -MAP_SIZE_CM,
    MAP_SIZE_CM
)


ax.grid(
    True,
    alpha=0.15,
    linestyle="--"
)


# ============================================================
# MAP IMAGE
# ============================================================

# Display:
#
# UNKNOWN    = dark
# FREE       = light
# OCCUPIED   = obstacle
#
# ============================================================

display_grid = np.zeros(
    grid.shape
)


map_image = ax.imshow(
    display_grid,
    origin="lower",

    extent=[
        -MAP_SIZE_CM,
        MAP_SIZE_CM,
        -MAP_SIZE_CM,
        MAP_SIZE_CM
    ],

    interpolation="nearest",

    vmin=-1,
    vmax=1,

    cmap="gray"
)


# ============================================================
# SCANNER
# ============================================================

scanner_plot, = ax.plot(
    [0],
    [0],
    "o",
    markersize=9,
    label="Scanner"
)


# ============================================================
# CURRENT BEAM
# ============================================================

beam_plot, = ax.plot(
    [],
    [],
    "-",
    linewidth=1,
    alpha=0.7
)


# ============================================================
# LEGEND
# ============================================================

ax.legend(
    loc="upper right"
)


# ============================================================
# INFO PANEL
# ============================================================

info_ax = fig.add_axes(
    [0.80, 0.48, 0.17, 0.35]
)

info_ax.axis(
    "off"
)


info_text = info_ax.text(
    0,
    1,
    "",
    verticalalignment="top",
    fontsize=11,
    family="monospace"
)


# ============================================================
# CLEAR BUTTON
# ============================================================

clear_ax = fig.add_axes(
    [0.82, 0.25, 0.13, 0.055]
)


clear_button = Button(
    clear_ax,
    "CLEAR MAP"
)


def clear_map(event):

    global grid

    grid.fill(-1)

    print("Map cleared.")


clear_button.on_clicked(
    clear_map
)


# ============================================================
# SAVE MAP
# ============================================================

save_ax = fig.add_axes(
    [0.82, 0.17, 0.13, 0.055]
)


save_button = Button(
    save_ax,
    "SAVE MAP"
)


def save_map(event):

    filename = (
        "occupancy_map_"
        + time.strftime(
            "%Y%m%d_%H%M%S"
        )
        + ".npy"
    )

    np.save(
        filename,
        grid
    )

    print(
        f"Map saved to {filename}"
    )


save_button.on_clicked(
    save_map
)


# ============================================================
# UPDATE
# ============================================================

last_save_time = 0

def update(frame):

    global last_save_time
    read_udp()


    # Update map image
    map_image.set_data(
        grid
    )


    # Scanner
    scanner_plot.set_data(
        [robot_x],
        [robot_y]
    )


    # ========================================================
    # Current LiDAR beam
    # ========================================================

    angle_rad = math.radians(
        last_angle
        + ANGLE_OFFSET
        + robot_heading
    )


    beam_end_x = (
        robot_x
        + last_distance
        * math.cos(angle_rad)
    )


    beam_end_y = (
        robot_y
        + last_distance
        * math.sin(angle_rad)
    )


    beam_plot.set_data(
        [
            robot_x,
            beam_end_x
        ],
        [
            robot_y,
            beam_end_y
        ]
    )


    # ========================================================
    # Statistics
    # ========================================================

    occupied = np.sum(
        grid == 1
    )

    free = np.sum(
        grid == 0
    )

    unknown = np.sum(
        grid == -1
    )


    info_text.set_text(
        f"""
MINE MAP

STATUS
────────────────
Packets : {packet_count}

DISTANCE
────────────────
{last_distance:.1f} cm

ANGLE
────────────────
{last_angle:.1f}°

GRID
────────────────
Cell    : {CELL_SIZE_CM} cm

Occupied: {occupied}
Free    : {free}
Unknown : {unknown}

POSE
────────────────
X       : {robot_x:.1f}
Y       : {robot_y:.1f}
Heading : {robot_heading:.1f}°
"""
    )


    current_time = time.time()
    if current_time - last_save_time > 1.0:
        try:
            # Avoid bbox_inches='tight' in FuncAnimation as it can cause renderer issues
            fig.savefig('current_map.png', facecolor=fig.get_facecolor())
            last_save_time = current_time
        except Exception as e:
            print("SAVE FIG ERROR:", e)


    return (
        map_image,
        scanner_plot,
        beam_plot
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