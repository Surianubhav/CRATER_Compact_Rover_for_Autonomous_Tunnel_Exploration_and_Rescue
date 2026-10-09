#!/usr/bin/env python3
"""
MINE ROVER SLAM V4

Laptop-side mapper for:
  - TF-Luna rotating LiDAR ESP32 -> UDP 4211
  - left/right AS5600 + MPU6500 ESP32 -> UDP 4212

Major changes from V3:
  * Encoder yaw is the primary turn estimate (calibrated effective track width).
  * Gyro is used as a secondary high-rate correction, not allowed to halve turns.
  * Encoder and gyro turn totals are shown in the status bar.
  * The rover marker is a ROTATING arrow, not a fixed '^' marker.
  * The travel trail is display-smoothed so straight motion does not look zig-zaggy.
  * LiDAR outliers are filtered before they reach the map display.
  * Occupancy display suppresses isolated occupied pixels.
  * Large turns are detected using accumulated turn since the previous scan.
  * Scan matching is conservative and cannot make a large heading jump.
  * Each useful scan is stored as a keyframe.
  * Every 15 seconds a fresh "optimized map" is rebuilt from the accumulated
    keyframes using sequential local scan-to-map refinement.
  * The optimized map becomes the displayed map, while the live map remains
    available as the source for matching.
  * No ESP32 firmware changes are required.
"""

import socket
import json
import threading
import math
import time
from collections import deque

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
from matplotlib.patches import Polygon

# ============================================================
# NETWORK
# ============================================================

LIDAR_PORT = 4211
ODOM_PORT = 4212
CONTROL_PORT = 4210
CONTROL_BROADCAST = "10.42.0.255"
BUFFER_SIZE = 4096

LIDAR_QUEUE_MAX = 25000
ODOM_QUEUE_MAX = 15000

# ============================================================
# CALIBRATED ROVER PARAMETERS
# ============================================================

LEFT_METERS_PER_REV = 0.147699
RIGHT_METERS_PER_REV = 0.148708

LEFT_DIRECTION = -1.0
RIGHT_DIRECTION = +1.0

# Slow-turn calibration result. Full-speed test 4 was discarded as slip.
TRACK_WIDTH_M = 0.2187
RUNTIME_TRACK_WIDTH_M = TRACK_WIDTH_M

# ============================================================
# IMU
# ============================================================

ACCEL_LSB_PER_G = 16384.0
GYRO_LSB_PER_DPS = 131.0

ACCEL_FORWARD_AXIS = "y"
ACCEL_FORWARD_SIGN = +1
ACCEL_RIGHT_AXIS = "x"
ACCEL_RIGHT_SIGN = +1
ACCEL_UP_AXIS = "z"
ACCEL_UP_SIGN = +1

GYRO_YAW_AXIS = "z"
GYRO_YAW_SIGN = +1.0

# Encoder is deliberately dominant because the track width was physically
# calibrated with real 360-degree turns. Gyro remains useful for slip/noise.
ENCODER_YAW_WEIGHT = 0.80
GYRO_YAW_WEIGHT = 0.20

# If gyro and encoder strongly disagree, trust the calibrated encoder even more.
TURN_DISAGREEMENT_DEG = 12.0
ENCODER_DOMINANT_WEIGHT = 0.90
GYRO_DOMINANT_WEIGHT = 0.10

# ============================================================
# STARTUP YAW CALIBRATION
# ============================================================
# Before mapping, the user performs one slow 360-degree CW turn.
# This establishes a clean map heading zero at the physical orientation
# where STARTUP CALIBRATION begins/ends and checks encoder/gyro yaw.
STARTUP_CALIBRATION_ENABLED = True
STARTUP_CALIBRATION_DEG = 360.0
STARTUP_CALIBRATION_TOLERANCE_DEG = 15.0
STARTUP_CALIBRATION_MIN_ENCODER_DEG = 270.0
STARTUP_CALIBRATION_TIMEOUT_SEC = 90.0
STARTUP_CALIBRATION_ADJUST_TRACK_WIDTH = True

# Map frame convention: the rover's physical forward direction at the end
# of startup calibration becomes map +X (0 degrees).
INITIAL_HEADING_DEG = 0.0


# ============================================================
# LIDAR
# ============================================================

LIDAR_OFFSET_X_M = 0.0
LIDAR_OFFSET_Y_M = 0.0
LIDAR_ANGLE_OFFSET_DEG = 0.0
LIDAR_ANGLE_SIGN = +1.0
LIDAR_WRAP_THRESHOLD_DEG = 180.0

LIDAR_MIN_DISTANCE_M = 0.03
LIDAR_MAX_DISTANCE_M = 8.0

# Reject an isolated range spike when both immediate angular neighbors exist.
# A large jump is allowed at genuine corners, but only if the point has support
# from at least one neighboring sample.
OUTLIER_JUMP_M = 1.20

# ============================================================
# MAP
# ============================================================

MAP_SIZE_M = 30.0
MAP_RESOLUTION = 0.05
MAP_CELLS = int(MAP_SIZE_M / MAP_RESOLUTION)
MAP_CENTER = MAP_CELLS // 2

# Live map used for online scan matching.
log_odds = np.zeros((MAP_CELLS, MAP_CELLS), dtype=np.float32)

# Rebuilt map used for the clean display / optimized result.
optimized_log_odds = np.zeros_like(log_odds)

LO_FREE = -0.08
LO_OCCUPIED = 0.70
LO_MIN = -3.5
LO_MAX = 3.5

OCCUPIED_THRESHOLD = 0.55
FREE_THRESHOLD = -0.45

# ============================================================
# ONLINE SCAN MATCHING
# ============================================================

SLAM_MIN_POINTS = 50
MAX_MATCH_POINTS = 280
MAX_INSERT_POINTS = 1400

COARSE_X_WINDOW_M = 0.14
COARSE_Y_WINDOW_M = 0.14
COARSE_YAW_WINDOW_DEG = 6.0
COARSE_X_STEP_M = 0.035
COARSE_Y_STEP_M = 0.035
COARSE_YAW_STEP_DEG = 1.5

FINE_X_WINDOW_M = 0.035
FINE_Y_WINDOW_M = 0.035
FINE_YAW_WINDOW_DEG = 1.5
FINE_X_STEP_M = 0.01
FINE_Y_STEP_M = 0.01
FINE_YAW_STEP_DEG = 0.5

MIN_MATCH_SCORE = 0.40
MIN_MATCH_IMPROVEMENT = 0.025
MAX_ACCEPTED_CORRECTION_M = 0.10
MAX_ACCEPTED_CORRECTION_DEG = 5.0

MIN_SCAN_MATCH_TRANSLATION_M = 0.04
MIN_SCAN_MATCH_ROTATION_DEG = 2.0

# A complete 90-degree turn is detected by accumulating all odometry packets,
# rather than looking at one 10-ms packet.
TURN_GATE_DEG = 18.0
TURN_MATCH_COOLDOWN_SCANS = 1

# ============================================================
# KEYFRAMES / OPTIMIZATION
# ============================================================

KEYFRAME_MAX = 500
KEYFRAME_MIN_DISTANCE_M = 0.12
KEYFRAME_MIN_ROTATION_DEG = 8.0
KEYFRAME_MAX_POINTS = 700

OPTIMIZE_PERIOD_SEC = 15.0
OPTIMIZE_MAX_KEYFRAMES = 350
OPTIMIZE_MATCH_POINTS = 160
OPTIMIZE_X_WINDOW_M = 0.10
OPTIMIZE_Y_WINDOW_M = 0.10
OPTIMIZE_YAW_WINDOW_DEG = 4.0
OPTIMIZE_X_STEP_M = 0.025
OPTIMIZE_Y_STEP_M = 0.025
OPTIMIZE_YAW_STEP_DEG = 1.0
OPTIMIZE_MIN_SCORE = 0.32

# ============================================================
# STATE
# ============================================================

state_lock = threading.Lock()
lidar_queue = deque(maxlen=LIDAR_QUEUE_MAX)
odom_queue = deque(maxlen=ODOM_QUEUE_MAX)
running = True

x = 0.0
y = 0.0
heading = 0.0

gyro_heading = 0.0

roll = 0.0
pitch = 0.0

previous_left = None
previous_right = None
previous_odom_time = None
previous_imu_time = None

encoder_velocity = 0.0

# Most recent gyro increment generated by process_imu for the same UDP packet.
latest_gyro_delta = 0.0
latest_gyro_rate_dps = 0.0

# Accumulated heading changes since the last completed scan.
encoder_turn_since_scan = 0.0
gyro_turn_since_scan = 0.0
fused_turn_since_scan = 0.0

# Heading values at last scan/keyframe.
last_scan_heading = 0.0
last_scan_x = 0.0
last_scan_y = 0.0

imu_calibrated = False
mapping_started = False
mapping_start_host_time = None

startup_calibration_active = False
startup_calibration_complete = False
startup_calibration_start_left = None
startup_calibration_start_right = None
startup_calibration_start_heading = None
startup_calibration_start_time = None
startup_calibration_encoder_turn = 0.0
startup_calibration_gyro_turn = 0.0
startup_calibration_last_time = None
startup_calibration_last_left = None
startup_calibration_last_right = None
startup_calibration_error_deg = 0.0


pose_history = deque(maxlen=30000)

last_match_pose = None
last_match_ok = False
last_match_score = 0.0
completed_scans = 0
turn_cooldown = 0

current_scan = []
previous_lidar_angle = None

trail_x = []
trail_y = []
MAX_TRAIL = 20000

# Raw local scan keyframes: {points, pose, time}
keyframes = deque(maxlen=KEYFRAME_MAX)

# Optimized keyframe poses are kept separately so the 15-second rebuild can
# refine the previous result instead of starting from zero each time.
optimized_keyframe_poses = []
last_optimization_time = 0.0
optimization_count = 0

# The pose saved immediately before an online scan match.
last_pre_match_pose = (0.0, 0.0, 0.0)

control_socket = None

# ============================================================
# HELPERS
# ============================================================

def normalize_angle(a):
    return math.atan2(math.sin(a), math.cos(a))


def get_axis(v, axis):
    if axis == "x":
        return v[0]
    if axis == "y":
        return v[1]
    return v[2]


def world_to_grid(wx, wy):
    return (
        int(math.floor(wx / MAP_RESOLUTION)) + MAP_CENTER,
        int(math.floor(wy / MAP_RESOLUTION)) + MAP_CENTER,
    )


def valid_grid(gx, gy):
    return 0 <= gx < MAP_CELLS and 0 <= gy < MAP_CELLS


def ray_cells(x0, y0, x1, y1):
    dx = x1 - x0
    dy = y1 - y0
    steps = int(max(abs(dx), abs(dy)))
    if steps <= 0:
        return
    for i in range(steps):
        a = i / steps
        yield int(round(x0 + a * dx)), int(round(y0 + a * dy))


def pose_distance(p0, p1):
    return (
        math.hypot(p1[0] - p0[0], p1[1] - p0[1]),
        abs(normalize_angle(p1[2] - p0[2])),
    )

# ============================================================
# RESET / CONTROL
# ============================================================

def reset_local_mapping_state():
    global x, y, heading, gyro_heading
    global roll, pitch
    global previous_left, previous_right, previous_odom_time, previous_imu_time
    global encoder_velocity, latest_gyro_delta, latest_gyro_rate_dps
    global encoder_turn_since_scan, gyro_turn_since_scan, fused_turn_since_scan
    global last_scan_heading, last_scan_x, last_scan_y
    global imu_calibrated, trail_x, trail_y, pose_history
    global current_scan, previous_lidar_angle
    global completed_scans, turn_cooldown, last_match_pose
    global last_match_ok, last_match_score
    global keyframes, optimized_keyframe_poses
    global last_optimization_time, optimization_count
    global optimized_log_odds
    global RUNTIME_TRACK_WIDTH_M
    global startup_calibration_active, startup_calibration_complete
    global startup_calibration_start_left, startup_calibration_start_right
    global startup_calibration_start_heading, startup_calibration_start_time
    global startup_calibration_encoder_turn, startup_calibration_gyro_turn
    global startup_calibration_last_time, startup_calibration_last_left
    global startup_calibration_last_right, startup_calibration_error_deg

    x = 0.0
    y = 0.0
    heading = 0.0
    gyro_heading = 0.0
    roll = 0.0
    pitch = 0.0

    previous_left = None
    previous_right = None
    previous_odom_time = None
    previous_imu_time = None
    encoder_velocity = 0.0
    latest_gyro_delta = 0.0
    latest_gyro_rate_dps = 0.0

    encoder_turn_since_scan = 0.0
    gyro_turn_since_scan = 0.0
    fused_turn_since_scan = 0.0
    last_scan_heading = 0.0
    last_scan_x = 0.0
    last_scan_y = 0.0

    imu_calibrated = False
    trail_x = []
    trail_y = []
    pose_history.clear()

    current_scan = []
    previous_lidar_angle = None

    completed_scans = 0
    turn_cooldown = 0
    last_match_pose = None
    last_match_ok = False
    last_match_score = 0.0

    keyframes = deque(maxlen=KEYFRAME_MAX)
    optimized_keyframe_poses = []
    last_optimization_time = time.monotonic()
    optimization_count = 0

    log_odds.fill(0.0)
    optimized_log_odds.fill(0.0)
    RUNTIME_TRACK_WIDTH_M = TRACK_WIDTH_M

    startup_calibration_active = False
    startup_calibration_complete = False
    startup_calibration_start_left = None
    startup_calibration_start_right = None
    startup_calibration_start_heading = None
    startup_calibration_start_time = None
    startup_calibration_encoder_turn = 0.0
    startup_calibration_gyro_turn = 0.0
    startup_calibration_last_time = None
    startup_calibration_last_left = None
    startup_calibration_last_right = None
    startup_calibration_error_deg = 0.0


def send_start_command():
    global mapping_started, mapping_start_host_time

    if control_socket is None:
        return

    with state_lock:
        lidar_queue.clear()
        odom_queue.clear()

    reset_local_mapping_state()

    try:
        control_socket.sendto(b"START", (CONTROL_BROADCAST, CONTROL_PORT))
    except OSError as e:
        print(f"[CONTROL] START failed: {e}")
        return

    mapping_start_host_time = time.monotonic()
    mapping_started = True
    begin_startup_calibration()
    print("\n[MAPPING] START sent. Startup calibration is required before mapping.\n")


def send_reset_command():
    if control_socket is None:
        return
    try:
        control_socket.sendto(b"RESET", (CONTROL_BROADCAST, CONTROL_PORT))
    except OSError:
        pass


def begin_startup_calibration():
    """Start the one-time physical CW 360-degree calibration."""
    global startup_calibration_active, startup_calibration_complete
    global startup_calibration_start_left, startup_calibration_start_right
    global startup_calibration_start_heading, startup_calibration_start_time
    global startup_calibration_encoder_turn, startup_calibration_gyro_turn
    global startup_calibration_last_time, startup_calibration_last_left
    global startup_calibration_last_right, startup_calibration_error_deg
    global x, y, heading, gyro_heading

    startup_calibration_active = STARTUP_CALIBRATION_ENABLED
    startup_calibration_complete = not STARTUP_CALIBRATION_ENABLED
    startup_calibration_start_left = None
    startup_calibration_start_right = None
    startup_calibration_start_heading = heading
    startup_calibration_start_time = time.monotonic()
    startup_calibration_encoder_turn = 0.0
    startup_calibration_gyro_turn = 0.0
    startup_calibration_last_time = None
    startup_calibration_last_left = None
    startup_calibration_last_right = None
    startup_calibration_error_deg = 0.0

    if STARTUP_CALIBRATION_ENABLED:
        print("""
============================================================
 STARTUP YAW CALIBRATION
============================================================

The map frame will be defined from the rover orientation NOW.

1. Put the rover on the floor at the desired mapping start point.
2. Mark its FRONT direction.
3. Press ENTER here.
4. Slowly rotate the rover exactly 360 degrees CLOCKWISE.
5. Return to the same physical orientation.
6. Press ENTER again.

This is NOT a mapping movement. The calibration turn is discarded.
The rover must end facing exactly the same way it started.

Do NOT use full speed.
""")
        input("Press ENTER when the rover is positioned and ready...")
        print(">>> ROTATE CLOCKWISE 360 DEGREES NOW <<<")
        input("When you have returned to the same orientation, press ENTER to finish calibration...")
        finish_startup_calibration()


def startup_calibration_update(left, right, packet_time):
    """Accumulate encoder turn during the startup calibration."""
    global startup_calibration_start_left, startup_calibration_start_right
    global startup_calibration_last_left, startup_calibration_last_right
    global startup_calibration_last_time, startup_calibration_encoder_turn

    if not startup_calibration_active:
        return

    if startup_calibration_start_left is None:
        startup_calibration_start_left = left
        startup_calibration_start_right = right
        startup_calibration_last_left = left
        startup_calibration_last_right = right
        startup_calibration_last_time = packet_time
        return

    dl_rev = left - startup_calibration_last_left
    dr_rev = right - startup_calibration_last_right
    startup_calibration_last_left = left
    startup_calibration_last_right = right

    dl = dl_rev * LEFT_METERS_PER_REV * LEFT_DIRECTION
    dr = dr_rev * RIGHT_METERS_PER_REV * RIGHT_DIRECTION
    dtheta = (dr - dl) / TRACK_WIDTH_M
    startup_calibration_encoder_turn += dtheta


def finish_startup_calibration():
    """Finish the physical calibration and zero the map frame."""
    global startup_calibration_active, startup_calibration_complete
    global startup_calibration_error_deg
    global x, y, heading, gyro_heading
    global pose_history, trail_x, trail_y
    global previous_left, previous_right, previous_odom_time, previous_imu_time
    global encoder_turn_since_scan, gyro_turn_since_scan, fused_turn_since_scan
    global last_scan_heading, last_scan_x, last_scan_y
    global current_scan, previous_lidar_angle
    global RUNTIME_TRACK_WIDTH_M

    if not startup_calibration_active:
        return True

    enc_deg = math.degrees(startup_calibration_encoder_turn)
    startup_calibration_error_deg = abs(abs(enc_deg) - STARTUP_CALIBRATION_DEG)

    print("\\n============================================================")
    print(" STARTUP CALIBRATION RESULT")
    print("============================================================")
    print(f"Encoder accumulated turn : {enc_deg:+.1f} deg")
    print(f"Target magnitude        : {STARTUP_CALIBRATION_DEG:.1f} deg (CW should be negative)")
    print(f"Magnitude error         : {startup_calibration_error_deg:.1f} deg")

    if abs(enc_deg) < STARTUP_CALIBRATION_MIN_ENCODER_DEG:
        print("CALIBRATION FAILED: encoder did not detect enough rotation.")
        print("Do the turn again slowly and make sure both tracks move.")
        return False

    if startup_calibration_error_deg > STARTUP_CALIBRATION_TOLERANCE_DEG:
        print("WARNING: 360-degree turn was outside the recommended tolerance.")
        print("The map frame will still be reset, but repeat slowly for best results.")
    else:
        print("Calibration accepted.")

    # Use the real 360-degree turn to make a small surface-specific correction
    # to the experimentally calibrated effective track width.
    if STARTUP_CALIBRATION_ADJUST_TRACK_WIDTH and abs(enc_deg) >= STARTUP_CALIBRATION_MIN_ENCODER_DEG:
        RUNTIME_TRACK_WIDTH_M = TRACK_WIDTH_M * (abs(enc_deg) / STARTUP_CALIBRATION_DEG)
        print(f"Runtime effective track width: {RUNTIME_TRACK_WIDTH_M*1000:.1f} mm")
    else:
        RUNTIME_TRACK_WIDTH_M = TRACK_WIDTH_M

    # The physical orientation at the end of the 360-degree turn is the map
    # reference. The turn itself is deliberately discarded from the map.
    x = 0.0
    y = 0.0
    heading = math.radians(INITIAL_HEADING_DEG)
    gyro_heading = heading

    # Prevent pre-calibration encoder displacement from entering the first map sample.
    previous_left = startup_calibration_last_left
    previous_right = startup_calibration_last_right
    previous_odom_time = None
    previous_imu_time = None

    encoder_turn_since_scan = 0.0
    gyro_turn_since_scan = 0.0
    fused_turn_since_scan = 0.0
    last_scan_heading = heading
    last_scan_x = x
    last_scan_y = y
    pose_history.clear()
    trail_x.clear()
    trail_y.clear()
    current_scan.clear()
    previous_lidar_angle = None

    startup_calibration_active = False
    startup_calibration_complete = True

    print("MAP FRAME ZEROED: rover forward = map +X (0 deg).")
    print("Startup turn discarded. Begin mapping now.\n")
    return True


def control_input_thread():
    global running, mapping_started
    while running:
        try:
            command = input().strip().lower()
        except (EOFError, KeyboardInterrupt):
            running = False
            break

        if command == "start":
            if not mapping_started:
                send_start_command()
            else:
                print("[CONTROL] Already running.")
        elif command in ("reset", "stop"):
            mapping_started = False
            send_reset_command()
            reset_local_mapping_state()
            with state_lock:
                lidar_queue.clear()
                odom_queue.clear()
            print("[CONTROL] Reset complete.")
        elif command in ("quit", "exit"):
            running = False
            break
        elif command:
            print("[CONTROL] Use START, RESET or QUIT.")

# ============================================================
# UDP RECEIVERS
# ============================================================

def lidar_receiver():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", LIDAR_PORT))
    sock.settimeout(0.5)
    print(f"[LIDAR] UDP {LIDAR_PORT}")

    while running:
        try:
            data, _ = sock.recvfrom(BUFFER_SIZE)
            host_t = time.monotonic()
            packet = json.loads(data.decode())
            with state_lock:
                lidar_queue.append((host_t, packet))
        except socket.timeout:
            continue
        except Exception as e:
            if running:
                print("[LIDAR ERROR]", e)
    sock.close()


def odom_receiver():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", ODOM_PORT))
    sock.settimeout(0.5)
    print(f"[ODOM] UDP {ODOM_PORT}")

    while running:
        try:
            data, _ = sock.recvfrom(BUFFER_SIZE)
            host_t = time.monotonic()
            packet = json.loads(data.decode())
            with state_lock:
                odom_queue.append((host_t, packet))
        except socket.timeout:
            continue
        except Exception as e:
            if running:
                print("[ODOM ERROR]", e)
    sock.close()

# ============================================================
# IMU / HEADING
# ============================================================

def process_imu(packet, packet_time):
    global previous_imu_time, gyro_heading
    global roll, pitch, imu_calibrated
    global latest_gyro_delta, latest_gyro_rate_dps
    global gyro_turn_since_scan

    if not mapping_started or packet is None or not packet.get("imuOK", False):
        latest_gyro_delta = 0.0
        return

    if startup_calibration_active:
        latest_gyro_delta = 0.0
        return

    raw_accel = np.array([
        float(packet.get("ax", 0.0)),
        float(packet.get("ay", 0.0)),
        float(packet.get("az", 0.0)),
    ], dtype=np.float64)

    gyro_raw = np.array([
        float(packet.get("gx", 0.0)),
        float(packet.get("gy", 0.0)),
        float(packet.get("gz", 0.0)),
    ], dtype=np.float64)

    if previous_imu_time is None:
        previous_imu_time = packet_time
        gyro_heading = heading
        latest_gyro_delta = 0.0
        latest_gyro_rate_dps = 0.0
        imu_calibrated = True
        return

    dt = packet_time - previous_imu_time
    previous_imu_time = packet_time

    if dt <= 0.0 or dt > 0.2:
        latest_gyro_delta = 0.0
        return

    accel = raw_accel / ACCEL_LSB_PER_G * 9.80665
    gyro = np.radians(gyro_raw / GYRO_LSB_PER_DPS)

    forward = get_axis(accel, ACCEL_FORWARD_AXIS) * ACCEL_FORWARD_SIGN
    right = get_axis(accel, ACCEL_RIGHT_AXIS) * ACCEL_RIGHT_SIGN
    up = get_axis(accel, ACCEL_UP_AXIS) * ACCEL_UP_SIGN

    yaw_rate = get_axis(gyro, GYRO_YAW_AXIS) * GYRO_YAW_SIGN
    latest_gyro_rate_dps = math.degrees(yaw_rate)
    latest_gyro_delta = yaw_rate * dt
    gyro_turn_since_scan += latest_gyro_delta
    gyro_heading = normalize_angle(gyro_heading + latest_gyro_delta)

    measured_roll = math.atan2(right, up)
    measured_pitch = math.atan2(-forward, math.sqrt(right * right + up * up))
    alpha = 0.98
    roll = alpha * roll + (1.0 - alpha) * measured_roll
    pitch = alpha * pitch + (1.0 - alpha) * measured_pitch

# ============================================================
# ENCODER ODOMETRY
# ============================================================

def process_odometry(packet, packet_time):
    global previous_left, previous_right, previous_odom_time
    global x, y, heading, gyro_heading, encoder_velocity
    global encoder_turn_since_scan, fused_turn_since_scan
    global turn_cooldown
    global RUNTIME_TRACK_WIDTH_M

    if not mapping_started or packet is None:
        return
    if not packet.get("leftOK", False) or not packet.get("rightOK", False):
        return

    left = float(packet["left"])
    right = float(packet["right"])

    if startup_calibration_active:
        startup_calibration_update(left, right, packet_time)
        return

    if not startup_calibration_complete:
        return

    if previous_left is None:
        previous_left = left
        previous_right = right
        previous_odom_time = packet_time
        pose_history.append((packet_time, x, y, heading))
        gyro_heading = heading
        return

    dt = packet_time - previous_odom_time
    if dt <= 0.0 or dt > 0.2:
        previous_left = left
        previous_right = right
        previous_odom_time = packet_time
        return

    dl_revs = left - previous_left
    dr_revs = right - previous_right
    previous_left = left
    previous_right = right
    previous_odom_time = packet_time

    dl = dl_revs * LEFT_METERS_PER_REV * LEFT_DIRECTION
    dr = dr_revs * RIGHT_METERS_PER_REV * RIGHT_DIRECTION

    ds = 0.5 * (dl + dr)
    dtheta_encoder = (dr - dl) / RUNTIME_TRACK_WIDTH_M
    dtheta_gyro = latest_gyro_delta

    encoder_turn_since_scan += dtheta_encoder
    fused_turn_since_scan += 0.0  # filled below after fusion

    encoder_velocity = ds / dt

    # If gyro and encoder agree, blend. If they strongly disagree, encoder is
    # deliberately dominant because its effective width was physically tested.
    if abs(math.degrees(dtheta_encoder - dtheta_gyro)) > TURN_DISAGREEMENT_DEG:
        ew = ENCODER_DOMINANT_WEIGHT
        gw = GYRO_DOMINANT_WEIGHT
    else:
        ew = ENCODER_YAW_WEIGHT
        gw = GYRO_YAW_WEIGHT

    dtheta_fused = ew * dtheta_encoder + gw * dtheta_gyro
    fused_turn_since_scan += dtheta_fused

    mid_heading = normalize_angle(heading + 0.5 * dtheta_fused)
    x += ds * math.cos(mid_heading)
    y += ds * math.sin(mid_heading)
    heading = normalize_angle(heading + dtheta_fused)

    pose_history.append((packet_time, x, y, heading))

    # Re-anchor the independent gyro estimate to the fused pose. This is the
    # original gyro-heading fix, retained here.
    gyro_heading = heading

# ============================================================
# POSE HISTORY
# ============================================================

def pose_at(t):
    if not pose_history:
        return x, y, heading

    hist = pose_history
    if t <= hist[0][0]:
        _, px, py, ph = hist[0]
        return px, py, ph
    if t >= hist[-1][0]:
        return x, y, heading

    for i in range(len(hist) - 1, 0, -1):
        t1, x1, y1, h1 = hist[i]
        t0, x0, y0, h0 = hist[i - 1]
        if t0 <= t <= t1:
            if t1 == t0:
                return x1, y1, h1
            a = (t - t0) / (t1 - t0)
            return (
                x0 + a * (x1 - x0),
                y0 + a * (y1 - y0),
                normalize_angle(h0 + a * normalize_angle(h1 - h0)),
            )

    return x, y, heading

# ============================================================
# LIDAR FILTERING
# ============================================================

def lidar_packet_to_local(packet):
    try:
        distance_m = float(packet["distance"]) / 100.0
        angle_deg = float(packet["angle"])
    except Exception:
        return None

    if not math.isfinite(distance_m) or not math.isfinite(angle_deg):
        return None
    if distance_m < LIDAR_MIN_DISTANCE_M or distance_m > LIDAR_MAX_DISTANCE_M:
        return None

    angle_deg = LIDAR_ANGLE_SIGN * angle_deg + LIDAR_ANGLE_OFFSET_DEG
    a = math.radians(angle_deg)
    return (
        LIDAR_OFFSET_X_M + distance_m * math.cos(a),
        LIDAR_OFFSET_Y_M + distance_m * math.sin(a),
        distance_m,
        angle_deg,
    )


def filtered_scan_local_points(scan, max_points=None):
    """Convert a scan to local points and suppress obvious isolated spikes."""
    vals = []
    for item in scan:
        local = lidar_packet_to_local(item[1])
        if local is not None:
            vals.append((item[0], *local))

    if len(vals) < SLAM_MIN_POINTS:
        return []

    # Range-neighbor filter. A point is retained if at least one immediate
    # angular neighbor is reasonably close, or if it is part of a short run.
    kept = []
    n = len(vals)
    for i, v in enumerate(vals):
        d = v[3]
        if i == 0 or i == n - 1:
            kept.append(v)
            continue
        d0 = vals[i - 1][3]
        d1 = vals[i + 1][3]
        if abs(d - d0) <= OUTLIER_JUMP_M or abs(d - d1) <= OUTLIER_JUMP_M:
            kept.append(v)

    if max_points is not None and len(kept) > max_points:
        idx = np.linspace(0, len(kept) - 1, max_points).astype(np.int32)
        kept = [kept[i] for i in idx]

    return kept

# ============================================================
# SCAN BUILDING
# ============================================================

current_scan = []
previous_lidar_angle = None


def add_lidar_packet(host_time, packet):
    global current_scan, previous_lidar_angle

    try:
        angle = float(packet["angle"])
    except Exception:
        return None

    if not math.isfinite(angle):
        return None

    if previous_lidar_angle is None:
        previous_lidar_angle = angle
        current_scan = [(host_time, packet)]
        return None

    delta = angle - previous_lidar_angle
    wrapped = abs(delta) > LIDAR_WRAP_THRESHOLD_DEG
    previous_lidar_angle = angle

    if wrapped:
        completed = current_scan
        current_scan = [(host_time, packet)]
        return completed

    current_scan.append((host_time, packet))
    if len(current_scan) > 5000:
        completed = current_scan
        current_scan = []
        return completed
    return None

# ============================================================
# SCAN MOTION COMPENSATION
# ============================================================

def build_scan_points(scan, max_points=MAX_MATCH_POINTS):
    vals = filtered_scan_local_points(scan, max_points=None)
    if len(vals) < SLAM_MIN_POINTS:
        return None

    current_x, current_y, current_h = x, y, heading
    cc = math.cos(current_h)
    ss = math.sin(current_h)
    points = []

    for host_t, lx, ly, _, _ in vals:
        px, py, ph = pose_at(host_t)
        c = math.cos(ph)
        s = math.sin(ph)
        wx = px + lx * c - ly * s
        wy = py + lx * s + ly * c

        dx = wx - current_x
        dy = wy - current_y
        rx = dx * cc + dy * ss
        ry = -dx * ss + dy * cc
        points.append((rx, ry))

    if len(points) < SLAM_MIN_POINTS:
        return None

    points = np.asarray(points, dtype=np.float32)
    if len(points) > max_points:
        idx = np.linspace(0, len(points) - 1, max_points).astype(np.int32)
        points = points[idx]
    return points

# ============================================================
# MAP SCORING
# ============================================================

def score_points_on_grid(points, test_x, test_y, test_heading, grid):
    if points is None or len(points) < 20:
        return -1e9

    c = math.cos(test_heading)
    s = math.sin(test_heading)
    px = points[:, 0]
    py = points[:, 1]
    wx = test_x + px * c - py * s
    wy = test_y + px * s + py * c

    gx = np.floor(wx / MAP_RESOLUTION + MAP_CENTER).astype(np.int32)
    gy = np.floor(wy / MAP_RESOLUTION + MAP_CENTER).astype(np.int32)

    valid = (
        (gx >= 1) & (gx < MAP_CELLS - 1) &
        (gy >= 1) & (gy < MAP_CELLS - 1)
    )
    if np.count_nonzero(valid) < 20:
        return -1e9

    gx = gx[valid]
    gy = gy[valid]

    v = [
        grid[gy, gx], grid[gy - 1, gx], grid[gy + 1, gx],
        grid[gy, gx - 1], grid[gy, gx + 1],
        grid[gy - 1, gx - 1], grid[gy - 1, gx + 1],
        grid[gy + 1, gx - 1], grid[gy + 1, gx + 1],
    ]
    neighborhood = np.maximum.reduce(v)

    occupied = np.clip(neighborhood / LO_MAX, 0.0, 1.0)
    free = np.clip(-neighborhood / abs(LO_MIN), 0.0, 1.0)
    return float(np.mean(occupied) - 0.20 * np.mean(free))


def score_pose(points, test_x, test_y, test_heading):
    return score_points_on_grid(points, test_x, test_y, test_heading, log_odds)

# ============================================================
# SEARCH
# ============================================================

def search_grid(points, center_pose, grid,
                x_window, y_window, yaw_window_deg,
                x_step, y_step, yaw_step_deg):
    cx, cy, ch = center_pose
    best = (cx, cy, ch)
    best_score = score_points_on_grid(points, cx, cy, ch, grid)

    xs = np.arange(-x_window, x_window + x_step * 0.5, x_step)
    ys = np.arange(-y_window, y_window + y_step * 0.5, y_step)
    hs = np.arange(
        -math.radians(yaw_window_deg),
        math.radians(yaw_window_deg) + math.radians(yaw_step_deg) * 0.5,
        math.radians(yaw_step_deg),
    )

    for dh in hs:
        th = normalize_angle(ch + dh)
        for dx in xs:
            tx = cx + dx
            for dy in ys:
                ty = cy + dy
                sc = score_points_on_grid(points, tx, ty, th, grid)
                if sc > best_score:
                    best_score = sc
                    best = (tx, ty, th)
    return (*best, best_score)


def scan_match(points):
    if points is None or len(points) < SLAM_MIN_POINTS:
        return False, 0.0, (x, y, heading)

    initial = score_pose(points, x, y, heading)
    if initial < 0:
        return False, initial, (x, y, heading)

    bx, by, bh, bs = search_grid(
        points, (x, y, heading), log_odds,
        COARSE_X_WINDOW_M, COARSE_Y_WINDOW_M, COARSE_YAW_WINDOW_DEG,
        COARSE_X_STEP_M, COARSE_Y_STEP_M, COARSE_YAW_STEP_DEG,
    )

    bx, by, bh, bs = search_grid(
        points, (bx, by, bh), log_odds,
        FINE_X_WINDOW_M, FINE_Y_WINDOW_M, FINE_YAW_WINDOW_DEG,
        FINE_X_STEP_M, FINE_Y_STEP_M, FINE_YAW_STEP_DEG,
    )

    correction_m = math.hypot(bx - x, by - y)
    correction_deg = abs(math.degrees(normalize_angle(bh - heading)))
    improvement = bs - initial

    accepted = (
        bs >= MIN_MATCH_SCORE and
        improvement >= MIN_MATCH_IMPROVEMENT and
        correction_m <= MAX_ACCEPTED_CORRECTION_M and
        correction_deg <= MAX_ACCEPTED_CORRECTION_DEG
    )
    if not accepted:
        return False, bs, (x, y, heading)
    return True, bs, (bx, by, bh)

# ============================================================
# ONLINE POSE CORRECTION
# ============================================================

def apply_scan_match(new_x, new_y, new_heading, match_time):
    global x, y, heading, gyro_heading
    x = new_x
    y = new_y
    heading = normalize_angle(new_heading)
    gyro_heading = heading
    if not pose_history or match_time >= pose_history[-1][0]:
        pose_history.append((match_time, x, y, heading))

# ============================================================
# MAP INSERTION
# ============================================================

def ray_update_grid(grid, rover_gx, rover_gy, hit_gx, hit_gy):
    for gx, gy in ray_cells(rover_gx, rover_gy, hit_gx, hit_gy):
        if valid_grid(gx, gy):
            grid[gy, gx] += LO_FREE
    if valid_grid(hit_gx, hit_gy):
        grid[hit_gy, hit_gx] += LO_OCCUPIED


def world_points_from_scan(scan):
    vals = filtered_scan_local_points(scan, max_points=MAX_INSERT_POINTS)
    if not vals:
        return []

    out = []
    pre_x, pre_y, pre_h = last_pre_match_pose
    corr_x, corr_y, corr_h = x, y, heading
    dc = math.cos(corr_h - pre_h)
    ds = math.sin(corr_h - pre_h)

    for host_t, lx, ly, _, _ in vals:
        px, py, ph = pose_at(host_t)
        c = math.cos(ph)
        s = math.sin(ph)
        wx = px + lx * c - ly * s
        wy = py + lx * s + ly * c

        # Apply accepted rigid correction from pre-match pose to current pose.
        dx = wx - pre_x
        dy = wy - pre_y
        nx = corr_x + dx * dc - dy * ds
        ny = corr_y + dx * ds + dy * dc
        out.append((nx, ny))
    return out


def insert_world_points(grid, world_points, rover_pose):
    rx, ry, _ = rover_pose
    rgx, rgy = world_to_grid(rx, ry)
    if not valid_grid(rgx, rgy):
        return
    for wx, wy in world_points:
        hgx, hgy = world_to_grid(wx, wy)
        if valid_grid(hgx, hgy):
            ray_update_grid(grid, rgx, rgy, hgx, hgy)
    np.clip(grid, LO_MIN, LO_MAX, out=grid)

# ============================================================
# KEYFRAMES
# ============================================================

def maybe_add_keyframe(scan_points, pose, host_time):
    global last_scan_heading, last_scan_x, last_scan_y

    if scan_points is None or len(scan_points) < SLAM_MIN_POINTS:
        return False
    pts = np.asarray(scan_points, dtype=np.float32)
    if len(pts) > KEYFRAME_MAX_POINTS:
        idx = np.linspace(0, len(pts) - 1, KEYFRAME_MAX_POINTS).astype(np.int32)
        pts = pts[idx]

    distance = math.hypot(pose[0] - last_scan_x, pose[1] - last_scan_y)
    rotation = abs(math.degrees(normalize_angle(pose[2] - last_scan_heading)))

    if not keyframes or distance >= KEYFRAME_MIN_DISTANCE_M or rotation >= KEYFRAME_MIN_ROTATION_DEG:
        keyframes.append({
            "points": pts.copy(),
            "pose": pose,
            "optimized_pose": pose,
            "time": host_time,
        })
        last_scan_x, last_scan_y = pose[0], pose[1]
        last_scan_heading = pose[2]
        return True
    return False

# ============================================================
# OPTIMIZED MAP
# ============================================================

def transform_local_points(points, pose):
    px, py, ph = pose
    c = math.cos(ph)
    s = math.sin(ph)
    lx = points[:, 0]
    ly = points[:, 1]
    return np.column_stack((
        px + lx * c - ly * s,
        py + lx * s + ly * c,
    ))


def rebuild_optimized_map():
    """Rebuild the clean map from all accumulated keyframes.

    Each keyframe is refined against the map made from earlier keyframes.
    The previous optimized poses are used as the initial guesses, so the map
    improves progressively instead of resetting to raw odometry each cycle.
    """
    global optimized_log_odds, optimized_keyframe_poses, optimization_count

    frames = list(keyframes)[-OPTIMIZE_MAX_KEYFRAMES:]
    if len(frames) < 2:
        optimized_log_odds[:] = log_odds
        return

    new_grid = np.zeros_like(log_odds)
    new_poses = []

    for i, frame in enumerate(frames):
        guess = frame.get("optimized_pose", frame["pose"])
        points = frame["points"]

        if i > 0 and len(points) >= 30:
            # Small sequential refinement. This is intentionally much smaller
            # than the live matcher so the 15-second rebuild stays bounded.
            bx, by, bh, bs = search_grid(
                points[:OPTIMIZE_MATCH_POINTS],
                guess,
                new_grid,
                OPTIMIZE_X_WINDOW_M,
                OPTIMIZE_Y_WINDOW_M,
                OPTIMIZE_YAW_WINDOW_DEG,
                OPTIMIZE_X_STEP_M,
                OPTIMIZE_Y_STEP_M,
                OPTIMIZE_YAW_STEP_DEG,
            )
            if bs >= OPTIMIZE_MIN_SCORE:
                # Never let the periodic optimizer move a keyframe wildly.
                dm = math.hypot(bx - guess[0], by - guess[1])
                dh = abs(math.degrees(normalize_angle(bh - guess[2])))
                if dm <= 0.12 and dh <= 5.0:
                    guess = (bx, by, bh)

        new_poses.append(guess)
        frame["optimized_pose"] = guess

        world = transform_local_points(points, guess)
        # Insert with enough rays to keep walls solid but not make the rebuild huge.
        if len(world) > MAX_INSERT_POINTS:
            idx = np.linspace(0, len(world) - 1, MAX_INSERT_POINTS).astype(np.int32)
            world = world[idx]
        insert_world_points(new_grid, world, guess)

    np.clip(new_grid, LO_MIN, LO_MAX, out=new_grid)
    optimized_log_odds = new_grid
    optimized_keyframe_poses = new_poses
    optimization_count += 1

# ============================================================
# DISPLAY FILTERING / TRAIL
# ============================================================

def clean_occupancy_image(grid):
    image = np.full((MAP_CELLS, MAP_CELLS), 0.08, dtype=np.float32)

    free = grid < -0.35
    image[free] = 0.18

    occupied = grid > OCCUPIED_THRESHOLD

    # Remove isolated occupied pixels. A wall cell should have nearby support.
    support = np.zeros_like(grid, dtype=np.int16)
    occ = occupied.astype(np.int16)
    support[1:-1, 1:-1] = (
        occ[:-2, :-2] + occ[:-2, 1:-1] + occ[:-2, 2:] +
        occ[1:-1, :-2] + occ[1:-1, 1:-1] + occ[1:-1, 2:] +
        occ[2:, :-2] + occ[2:, 1:-1] + occ[2:, 2:]
    )
    occupied &= support >= 2
    image[occupied] = 0.95
    return image


def smoothed_trail_world():
    if len(trail_x) < 5:
        return trail_x[:], trail_y[:]

    # Downsample first, then moving-average. This is DISPLAY ONLY.
    pts = np.column_stack((trail_x[::5], trail_y[::5]))
    if len(pts) < 5:
        return pts[:, 0].tolist(), pts[:, 1].tolist()

    w = min(7, len(pts) if len(pts) % 2 == 1 else len(pts) - 1)
    if w < 3:
        return pts[:, 0].tolist(), pts[:, 1].tolist()
    kernel = np.ones(w, dtype=np.float32) / w
    sx = np.convolve(pts[:, 0], kernel, mode="same")
    sy = np.convolve(pts[:, 1], kernel, mode="same")
    return sx.tolist(), sy.tolist()


def travel_heading():
    """Direction of travel for the UI arrow.

    While moving, use the direction of the recent trajectory. When stopped,
    keep the last travel direction; if unavailable, fall back to SLAM heading.
    """
    if len(trail_x) < 15:
        return heading

    # Look back far enough to suppress 100-Hz encoder jitter.
    n = min(30, len(trail_x) - 1)
    dx = trail_x[-1] - trail_x[-1 - n]
    dy = trail_y[-1] - trail_y[-1 - n]
    if math.hypot(dx, dy) > 0.08:
        return math.atan2(dy, dx)
    return heading

# ============================================================
# FINAL SAVE
# ============================================================

def save_final_result(fig):
    """Save the latest optimized map and trajectory when the run ends."""
    try:
        final_grid = optimized_log_odds if optimization_count > 0 else log_odds
        fig.savefig("mine_rover_final_optimized_map.png", dpi=180, bbox_inches="tight")
        np.savez_compressed(
            "mine_rover_final_optimized_map.npz",
            log_odds=final_grid,
            trail_x=np.asarray(trail_x, dtype=np.float32),
            trail_y=np.asarray(trail_y, dtype=np.float32),
            keyframe_poses=np.asarray(optimized_keyframe_poses, dtype=np.float32),
            resolution=np.float32(MAP_RESOLUTION),
        )
        print("[SAVE] mine_rover_final_optimized_map.png")
        print("[SAVE] mine_rover_final_optimized_map.npz")
    except Exception as e:
        print("[SAVE ERROR]", e)

# ============================================================
# MAIN
# ============================================================

def main():
    global running, control_socket
    global completed_scans, last_match_ok, last_match_score
    global last_match_pose, last_pre_match_pose
    global turn_cooldown
    global encoder_turn_since_scan, gyro_turn_since_scan, fused_turn_since_scan
    global last_scan_heading, last_scan_x, last_scan_y
    global last_optimization_time
    global startup_calibration_active, startup_calibration_complete

    print("\n==============================================")
    print("       MINE ROVER SLAM V4")
    print("==============================================")
    print(f"Left  m/rev : {LEFT_METERS_PER_REV:.6f}")
    print(f"Right m/rev : {RIGHT_METERS_PER_REV:.6f}")
    print(f"Track width : {TRACK_WIDTH_M:.4f} m")
    print(f"Yaw fusion  : encoder {ENCODER_YAW_WEIGHT:.0%} / gyro {GYRO_YAW_WEIGHT:.0%}")
    print(f"Optimization: every {OPTIMIZE_PERIOD_SEC:.0f} s")
    print("\nType START and press ENTER to begin mapping.")
    print("Type RESET or QUIT.\n")

    control_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    control_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    threading.Thread(target=lidar_receiver, daemon=True).start()
    threading.Thread(target=odom_receiver, daemon=True).start()
    threading.Thread(target=control_input_thread, daemon=True).start()

    plt.ion()
    fig, ax = plt.subplots(figsize=(12, 8))
    fig.patch.set_facecolor("#0b1014")
    ax.set_facecolor("#0b1014")

    map_display = ax.imshow(
        clean_occupancy_image(optimized_log_odds),
        cmap=ListedColormap(["#0b1014", "#1b252b", "#d9e0e3"]),
        origin="lower",
        interpolation="nearest",
        vmin=0.0,
        vmax=1.0,
    )

    grid_spacing = max(1, int(1.0 / MAP_RESOLUTION))
    ax.set_xticks(np.arange(0, MAP_CELLS, grid_spacing))
    ax.set_yticks(np.arange(0, MAP_CELLS, grid_spacing))
    ax.grid(True, color="#263238", linewidth=0.5, alpha=0.35)

    trail_plot, = ax.plot([], [], color="#36c5f0", linewidth=1.5, alpha=0.75)
    heading_plot, = ax.plot([], [], color="#5cc8ff", linewidth=2.0)
    scan_plot, = ax.plot([], [], linestyle="None", marker=".",
                         markersize=1.0, color="#8aa0aa", alpha=0.20)

    # Actual rotating rover arrow. Unlike marker='^', this does not stay fixed.
    rover_arrow = Polygon(
        [[0, 0], [0, 0], [0, 0]],
        closed=True,
        facecolor="#4da3ff",
        edgecolor="#d9f2ff",
        linewidth=0.8,
        zorder=10,
    )
    ax.add_patch(rover_arrow)

    last_ui_time = time.monotonic()

    try:
        while running:
            with state_lock:
                odom_items = list(odom_queue)
                odom_queue.clear()
                lidar_items = list(lidar_queue)
                lidar_queue.clear()

            if mapping_started:
                for host_t, packet in odom_items:
                    process_imu(packet, host_t)
                    process_odometry(packet, host_t)

                if startup_calibration_active:
                    # Drain LiDAR packets but do not build or insert mapping scans.
                    for host_t, packet in lidar_items:
                        add_lidar_packet(host_t, packet)
                for host_t, packet in ([] if startup_calibration_active else lidar_items):
                    completed = add_lidar_packet(host_t, packet)
                    if completed is None or len(completed) < SLAM_MIN_POINTS:
                        continue

                    completed_scans += 1
                    current_pose = (x, y, heading)
                    scan_enc_turn = math.degrees(encoder_turn_since_scan)
                    scan_gyro_turn = math.degrees(gyro_turn_since_scan)
                    scan_fused_turn = math.degrees(fused_turn_since_scan)

                    # Save the scan as a keyframe candidate before corrections.
                    match_points = build_scan_points(completed)

                    if completed_scans == 1:
                        last_pre_match_pose = current_pose
                        world_pts = world_points_from_scan(completed)
                        insert_world_points(log_odds, world_pts, current_pose)
                        maybe_add_keyframe(match_points, current_pose, completed[-1][0])
                        last_match_pose = current_pose
                    else:
                        moved_m, moved_rad = pose_distance(
                            last_match_pose if last_match_pose is not None else current_pose,
                            current_pose,
                        )

                        last_pre_match_pose = current_pose
                        large_turn = abs(scan_fused_turn) > TURN_GATE_DEG

                        if match_points is None:
                            ok, score, matched_pose = False, 0.0, current_pose
                        elif large_turn:
                            # Never let a 90-degree transition be reinterpreted
                            # as a different room by local correlation.
                            ok, score, matched_pose = False, 0.0, current_pose
                            turn_cooldown = TURN_MATCH_COOLDOWN_SCANS
                        elif turn_cooldown > 0:
                            turn_cooldown -= 1
                            ok, score, matched_pose = False, 0.0, current_pose
                        elif moved_m < MIN_SCAN_MATCH_TRANSLATION_M and \
                                math.degrees(moved_rad) < MIN_SCAN_MATCH_ROTATION_DEG:
                            ok, score, matched_pose = False, 0.0, current_pose
                        else:
                            ok, score, matched_pose = scan_match(match_points)

                        last_match_ok = ok
                        last_match_score = score

                        if ok:
                            apply_scan_match(*matched_pose, completed[-1][0])
                            current_pose = matched_pose
                        else:
                            current_pose = (x, y, heading)

                        world_pts = world_points_from_scan(completed)
                        insert_world_points(log_odds, world_pts, current_pose)
                        maybe_add_keyframe(match_points, current_pose, completed[-1][0])
                        last_match_pose = current_pose

                    # Reset per-scan turn accumulators ONLY after the scan has
                    # consumed them. This makes the displayed encoder turn real.
                    encoder_turn_since_scan = 0.0
                    gyro_turn_since_scan = 0.0
                    fused_turn_since_scan = 0.0

                    np.clip(log_odds, LO_MIN, LO_MAX, out=log_odds)

            # --------------------------------------------------------
            # PERIODIC OPTIMIZATION
            # --------------------------------------------------------
            now = time.monotonic()
            if mapping_started and now - last_optimization_time >= OPTIMIZE_PERIOD_SEC:
                try:
                    rebuild_optimized_map()
                    last_optimization_time = now
                except Exception as e:
                    print("[OPTIMIZER ERROR]", e)
                    last_optimization_time = now

            # --------------------------------------------------------
            # DISPLAY TRAIL
            # --------------------------------------------------------
            if mapping_started:
                trail_x.append(x)
                trail_y.append(y)
                if len(trail_x) > MAX_TRAIL:
                    del trail_x[:-MAX_TRAIL]
                    del trail_y[:-MAX_TRAIL]

            display_grid = optimized_log_odds if optimization_count > 0 else log_odds
            map_display.set_data(clean_occupancy_image(display_grid))

            gx, gy = world_to_grid(x, y)
            course = travel_heading()

            # Rotating arrow: nose points along recent travel direction.
            size = 7.0
            width = 4.0
            c = math.cos(course)
            s = math.sin(course)
            fx, fy = gx + size * c, gy + size * s
            lx = gx - size * 0.65 * c + width * (-s)
            ly = gy - size * 0.65 * s + width * c
            rx = gx - size * 0.65 * c - width * (-s)
            ry = gy - size * 0.65 * s - width * c
            rover_arrow.set_xy([[fx, fy], [lx, ly], [rx, ry]])

            # Heading line uses actual SLAM heading, separate from the UI travel arrow.
            heading_length = 8.0
            hx = gx + heading_length * math.cos(heading)
            hy = gy + heading_length * math.sin(heading)
            heading_plot.set_data([gx, hx], [gy, hy])

            sx, sy = smoothed_trail_world()
            if sx:
                trail_gx = []
                trail_gy = []
                for tx, ty in zip(sx[-1500:], sy[-1500:]):
                    tgx, tgy = world_to_grid(tx, ty)
                    trail_gx.append(tgx)
                    trail_gy.append(tgy)
                trail_plot.set_data(trail_gx, trail_gy)
            else:
                trail_plot.set_data([], [])

            # Current LiDAR scan, filtered and displayed faintly.
            if current_scan:
                vals = filtered_scan_local_points(current_scan, max_points=500)
                scan_x = []
                scan_y = []
                for host_t, lx, ly, _, _ in vals:
                    px, py, ph = pose_at(host_t)
                    cph = math.cos(ph)
                    sph = math.sin(ph)
                    wx = px + lx * cph - ly * sph
                    wy = py + lx * sph + ly * cph
                    sgx, sgy = world_to_grid(wx, wy)
                    scan_x.append(sgx)
                    scan_y.append(sgy)
                scan_plot.set_data(scan_x, scan_y)
            else:
                scan_plot.set_data([], [])

            if mapping_started and startup_calibration_active:
                status = (
                    "MINE ROVER SLAM V4 | STARTUP CALIBRATION"
                    f" | ENC TURN {math.degrees(startup_calibration_encoder_turn):+.1f}°"
                    f" | TARGET -360° CW"
                )
            elif mapping_started:
                status = (
                    "MINE ROVER SLAM V4"
                    f" | POS {x:.2f},{y:.2f}m"
                    f" | HDG {math.degrees(heading):.1f}°"
                    f" | W {RUNTIME_TRACK_WIDTH_M*1000:.0f}mm"
                    f" | ENC {math.degrees(encoder_turn_since_scan):+.1f}°"
                    f" | GYR {math.degrees(gyro_turn_since_scan):+.1f}°"
                    f" | MATCH {'OK' if last_match_ok else 'ODOM'} {last_match_score:.2f}"
                    f" | KF {len(keyframes)}"
                    f" | OPT {optimization_count}"
                )
            else:
                status = "MINE ROVER SLAM V4 | WAITING FOR START"

            ax.set_title(status, loc="left", fontsize=10, color="#dce7eb")
            fig.canvas.draw_idle()
            fig.canvas.flush_events()
            time.sleep(0.02)

    except KeyboardInterrupt:
        print("\nStopping SLAM...")
    finally:
        running = False
        if control_socket is not None:
            try:
                control_socket.close()
            except Exception:
                pass
        save_final_result(fig)
        plt.ioff()
        plt.show()


if __name__ == "__main__":
    main()
