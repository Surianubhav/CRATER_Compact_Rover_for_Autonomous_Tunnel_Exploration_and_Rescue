#!/usr/bin/env python3
"""
Mine Rover SLAM - revised laptop mapper

Key fixes:
- Uses continuous encoder revolutions directly (NO 0..4095 wrap logic).
- Uses calibrated effective track width = 0.2187 m.
- Uses MPU6500 Z gyro as the yaw-rate source with sign +1.
- Scan-match heading corrections are immediately re-anchored into
  gyro_heading, so the gyro cannot undo a LiDAR correction on the next packet.
- Scan matching is done with motion-compensated scan points in the current
  rover frame, then the accepted SE(2) correction is applied to the current pose.
- The completed scan is inserted using the corrected pose, rather than using
  stale pre-match pose history.
- Pose history is maintained as an ordered list/deque for timestamp interpolation.
- LiDAR angle wrap is handled robustly using the reported scan direction.
- Scan matcher uses a two-stage coarse/fine search and an occupied/free score.
- Low-confidence scan matches are rejected.
- Mapping can be START/RESET controlled without changing ESP32 firmware.
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

# Experimentally calibrated effective width.
# Tests 1,2,3,5: 217.4, 214.7, 222.5, 220.2 mm.
# Full-speed Test 4 (183.7 mm) was treated as a slip outlier.
TRACK_WIDTH_M = 0.2187

# ============================================================
# IMU
# ============================================================

ACCEL_LSB_PER_G = 16384.0
GYRO_LSB_PER_DPS = 131.0

# Physical mounting/calibration already established.
ACCEL_FORWARD_AXIS = "y"
ACCEL_FORWARD_SIGN = +1
ACCEL_RIGHT_AXIS = "x"
ACCEL_RIGHT_SIGN = +1
ACCEL_UP_AXIS = "z"
ACCEL_UP_SIGN = +1

# MPU6500 yaw axis calibration result.
GYRO_YAW_AXIS = "z"
GYRO_YAW_SIGN = +1.0

# ============================================================
# LIDAR MOUNT CALIBRATION
# ============================================================

LIDAR_OFFSET_X_M = 0.0
LIDAR_OFFSET_Y_M = 0.0
LIDAR_ANGLE_OFFSET_DEG = 0.0
LIDAR_ANGLE_SIGN = +1.0

# Packet angle is expected to be [0,360), but wrap handling does not rely
# on an exact endpoint.
LIDAR_WRAP_THRESHOLD_DEG = 180.0

LIDAR_MIN_DISTANCE_M = 0.02
LIDAR_MAX_DISTANCE_M = 12.0

# ============================================================
# MAP
# ============================================================

MAP_SIZE_M = 30.0
MAP_RESOLUTION = 0.05
MAP_CELLS = int(MAP_SIZE_M / MAP_RESOLUTION)
MAP_CENTER = MAP_CELLS // 2

log_odds = np.zeros((MAP_CELLS, MAP_CELLS), dtype=np.float32)

LO_FREE = -0.10
LO_OCCUPIED = 0.65
LO_MIN = -4.0
LO_MAX = 4.0

# ============================================================
# SCAN / MATCHING
# ============================================================

SLAM_MIN_POINTS = 40
MAX_MATCH_POINTS = 320
MAX_INSERT_POINTS = 1800

# Search around the odometric pose. Two stages are used below.
COARSE_X_WINDOW_M = 0.25
COARSE_Y_WINDOW_M = 0.25
COARSE_YAW_WINDOW_DEG = 15.0
COARSE_X_STEP_M = 0.05
COARSE_Y_STEP_M = 0.05
COARSE_YAW_STEP_DEG = 3.0

FINE_X_WINDOW_M = 0.06
FINE_Y_WINDOW_M = 0.06
FINE_YAW_WINDOW_DEG = 3.0
FINE_X_STEP_M = 0.015
FINE_Y_STEP_M = 0.015
FINE_YAW_STEP_DEG = 0.75

MIN_MATCH_SCORE = 0.20
MIN_MATCH_IMPROVEMENT = 0.015
MAX_ACCEPTED_CORRECTION_M = 0.35
MAX_ACCEPTED_CORRECTION_DEG = 18.0

# Score uses a 3x3 occupied neighborhood and penalizes known-free cells.
OCCUPIED_THRESHOLD = 0.45
FREE_THRESHOLD = -0.45

# Only perform a scan-match correction when enough new motion has occurred.
MIN_SCAN_MATCH_TRANSLATION_M = 0.03
MIN_SCAN_MATCH_ROTATION_DEG = 1.5

# ============================================================
# DISPLAY / TRAIL
# ============================================================

MAX_TRAIL = 20000
trail_x = []
trail_y = []

# ============================================================
# PACKETS / STATE
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

imu_calibrated = False
mapping_started = False
mapping_start_host_time = None

# Timestamped pose history. Every entry is (host_time,x,y,heading).
pose_history = deque(maxlen=30000)

# Last accepted pose from a scan match. Used to avoid matching identical
# stationary scans repeatedly.
last_match_pose = None
last_match_ok = False
last_match_score = 0.0
completed_scans = 0

# Current LiDAR scan.
current_scan = []
previous_lidar_angle = None

control_socket = None

# ============================================================
# HELPERS
# ============================================================

def normalize_angle(angle):
    return math.atan2(math.sin(angle), math.cos(angle))


def get_axis(v, axis):
    if axis == "x":
        return v[0]
    if axis == "y":
        return v[1]
    return v[2]


def world_to_grid(wx, wy):
    gx = int(math.floor(wx / MAP_RESOLUTION)) + MAP_CENTER
    gy = int(math.floor(wy / MAP_RESOLUTION)) + MAP_CENTER
    return gx, gy


def valid_grid(gx, gy):
    return 0 <= gx < MAP_CELLS and 0 <= gy < MAP_CELLS


def ray_cells(x0, y0, x1, y1):
    dx = x1 - x0
    dy = y1 - y0
    steps = int(max(abs(dx), abs(dy)))
    if steps <= 0:
        return
    # Avoid np.linspace allocating huge arrays for individual rays.
    for i in range(steps):
        a = i / steps
        yield int(round(x0 + a * dx)), int(round(y0 + a * dy))


def pose_distance(p0, p1):
    dx = p1[0] - p0[0]
    dy = p1[1] - p0[1]
    dh = normalize_angle(p1[2] - p0[2])
    return math.hypot(dx, dy), abs(dh)

# ============================================================
# RESET / CONTROL
# ============================================================

def reset_local_mapping_state():
    global x, y, heading, gyro_heading
    global roll, pitch
    global previous_left, previous_right
    global previous_odom_time, previous_imu_time
    global encoder_velocity, imu_calibrated
    global trail_x, trail_y, pose_history
    global current_scan, previous_lidar_angle
    global completed_scans, last_match_ok, last_match_score
    global last_match_pose

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
    imu_calibrated = False

    trail_x = []
    trail_y = []
    pose_history.clear()

    current_scan = []
    previous_lidar_angle = None

    completed_scans = 0
    last_match_ok = False
    last_match_score = 0.0
    last_match_pose = None

    log_odds.fill(0.0)


def send_start_command():
    global mapping_started, mapping_start_host_time

    if control_socket is None:
        print("[CONTROL] Control socket not initialized.")
        return

    with state_lock:
        lidar_queue.clear()
        odom_queue.clear()

    reset_local_mapping_state()

    try:
        control_socket.sendto(b"START", (CONTROL_BROADCAST, CONTROL_PORT))
    except OSError as e:
        print(f"[CONTROL] START broadcast failed: {e}")
        return

    mapping_start_host_time = time.monotonic()
    mapping_started = True

    print("\n================================================")
    print(" MAPPING START SENT")
    print(" Both ESP32s should reset seq/timestamp.")
    print(" Waiting for live LiDAR + odometry data...")
    print("================================================\n")


def send_reset_command():
    if control_socket is None:
        return
    try:
        control_socket.sendto(b"RESET", (CONTROL_BROADCAST, CONTROL_PORT))
    except OSError as e:
        print(f"[CONTROL] RESET failed: {e}")


def control_input_thread():
    global running, mapping_started

    while running:
        try:
            command = input().strip().lower()
        except (EOFError, KeyboardInterrupt):
            running = False
            break

        if command == "start":
            if mapping_started:
                print("[CONTROL] Mapping is already running.")
            else:
                send_start_command()
        elif command in ("reset", "stop"):
            mapping_started = False
            send_reset_command()
            reset_local_mapping_state()
            with state_lock:
                lidar_queue.clear()
                odom_queue.clear()
            print("[CONTROL] Reset complete. Type START for a new run.")
        elif command in ("quit", "exit"):
            running = False
            break
        elif command:
            print("[CONTROL] Type START, RESET, or QUIT.")

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
# IMU
# ============================================================

def process_imu(packet, packet_time):
    global previous_imu_time, gyro_heading
    global roll, pitch, imu_calibrated

    if not mapping_started or packet is None or not packet.get("imuOK", False):
        return

    raw_accel = np.array([
        float(packet.get("ax", 0.0)),
        float(packet.get("ay", 0.0)),
        float(packet.get("az", 0.0)),
    ], dtype=np.float64)

    filtered_gyro_raw = np.array([
        float(packet.get("gx", 0.0)),
        float(packet.get("gy", 0.0)),
        float(packet.get("gz", 0.0)),
    ], dtype=np.float64)

    if previous_imu_time is None:
        previous_imu_time = packet_time
        imu_calibrated = True
        # Keep the gyro anchor consistent with the pose heading.
        gyro_heading = heading
        return

    dt = packet_time - previous_imu_time
    previous_imu_time = packet_time

    if dt <= 0.0 or dt > 0.2:
        return

    accel = raw_accel / ACCEL_LSB_PER_G * 9.80665
    gyro = np.radians(filtered_gyro_raw / GYRO_LSB_PER_DPS)

    forward = get_axis(accel, ACCEL_FORWARD_AXIS) * ACCEL_FORWARD_SIGN
    right = get_axis(accel, ACCEL_RIGHT_AXIS) * ACCEL_RIGHT_SIGN
    up = get_axis(accel, ACCEL_UP_AXIS) * ACCEL_UP_SIGN

    yaw_rate = get_axis(gyro, GYRO_YAW_AXIS) * GYRO_YAW_SIGN

    # Gyro heading is an independent short-term orientation estimate.
    gyro_heading = normalize_angle(gyro_heading + yaw_rate * dt)

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

    if not mapping_started or packet is None:
        return
    if not packet.get("leftOK", False) or not packet.get("rightOK", False):
        return

    # Firmware sends CONTINUOUS UNWRAPPED REVOLUTIONS.
    left = float(packet["left"])
    right = float(packet["right"])

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
    dtheta_encoder = (dr - dl) / TRACK_WIDTH_M

    encoder_velocity = ds / dt

    # Use the gyro increment as the primary short-term yaw measurement,
    # but constrain it to the encoder turn so an occasional gyro spike
    # cannot rotate the entire map.
    gyro_delta = normalize_angle(gyro_heading - heading)

    # Blend incremental heading changes rather than blending absolute
    # headings. This avoids discontinuities after a scan-match correction.
    # 65% gyro / 35% encoder is intentionally conservative for a tracked rover.
    dtheta_fused = 0.65 * gyro_delta + 0.35 * dtheta_encoder

    mid_heading = normalize_angle(heading + 0.5 * dtheta_fused)

    x += ds * math.cos(mid_heading)
    y += ds * math.sin(mid_heading)
    heading = normalize_angle(heading + dtheta_fused)

    pose_history.append((packet_time, x, y, heading))

    # IMPORTANT: keep the independent gyro estimate anchored to the newly
    # fused heading. This prevents the next gyro sample from reintroducing
    # the old heading after encoder/scan corrections.
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

    # Deque is ordered. Binary search over a temporary timestamp array keeps
    # interpolation much cheaper than scanning all 30k entries each LiDAR point.
    # In practice scans are short, so a reverse scan from the end is sufficient.
    for i in range(len(hist) - 1, 0, -1):
        t1, x1, y1, h1 = hist[i]
        t0, x0, y0, h0 = hist[i - 1]
        if t0 <= t <= t1:
            if t1 == t0:
                return x1, y1, h1
            a = (t - t0) / (t1 - t0)
            px = x0 + a * (x1 - x0)
            py = y0 + a * (y1 - y0)
            ph = normalize_angle(h0 + a * normalize_angle(h1 - h0))
            return px, py, ph

    return x, y, heading

# ============================================================
# LIDAR CONVERSION
# ============================================================

def lidar_packet_to_local(packet):
    try:
        distance_m = float(packet["distance"]) / 100.0
        angle_deg = float(packet["angle"])
    except Exception:
        return None

    if not (LIDAR_MIN_DISTANCE_M <= distance_m <= LIDAR_MAX_DISTANCE_M):
        return None

    angle_deg = LIDAR_ANGLE_SIGN * angle_deg + LIDAR_ANGLE_OFFSET_DEG
    angle = math.radians(angle_deg)

    lx = LIDAR_OFFSET_X_M + distance_m * math.cos(angle)
    ly = LIDAR_OFFSET_Y_M + distance_m * math.sin(angle)
    return lx, ly, distance_m

# ============================================================
# 360-DEGREE SCAN BUILDER
# ============================================================

def add_lidar_packet(host_time, packet):
    global current_scan, previous_lidar_angle

    try:
        angle = float(packet["angle"])
    except Exception:
        return None

    # Ignore impossible angles instead of corrupting scan segmentation.
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
# SCAN POINT BUILDING / MOTION COMPENSATION
# ============================================================

def build_scan_points(scan, max_points=MAX_MATCH_POINTS):
    """Return scan points in the CURRENT rover coordinate frame.

    Each LiDAR measurement is transformed using the pose at its timestamp,
    then transformed back into the current rover frame. This compensates for
    rover motion during the 360-degree sweep.
    """
    if not scan:
        return None

    points = []
    current_x, current_y, current_h = x, y, heading
    cc = math.cos(current_h)
    ss = math.sin(current_h)

    for host_t, packet in scan:
        local = lidar_packet_to_local(packet)
        if local is None:
            continue
        lx, ly, _ = local

        px, py, ph = pose_at(host_t)
        c = math.cos(ph)
        s = math.sin(ph)

        # Measurement -> world.
        wx = px + lx * c - ly * s
        wy = py + lx * s + ly * c

        # World -> current rover frame.
        dx = wx - current_x
        dy = wy - current_y
        rx = dx * cc + dy * ss
        ry = -dx * ss + dy * cc
        points.append((rx, ry))

    if len(points) < SLAM_MIN_POINTS:
        return None

    points = np.asarray(points, dtype=np.float32)

    # Uniform angular-ish sampling by input order. This keeps the whole room
    # represented without allowing dense sectors to dominate the score.
    if len(points) > max_points:
        idx = np.linspace(0, len(points) - 1, max_points).astype(np.int32)
        points = points[idx]

    return points

# ============================================================
# MAP SCORING
# ============================================================

def score_pose(points, test_x, test_y, test_heading):
    if points is None or len(points) < SLAM_MIN_POINTS:
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

    if np.count_nonzero(valid) < SLAM_MIN_POINTS:
        return -1e9

    gxv = gx[valid]
    gyv = gy[valid]

    # 3x3 neighborhood max: tolerates small map discretization errors.
    v00 = log_odds[gyv, gxv]
    v01 = log_odds[gyv - 1, gxv]
    v02 = log_odds[gyv + 1, gxv]
    v10 = log_odds[gyv, gxv - 1]
    v11 = log_odds[gyv, gxv + 1]
    v12 = log_odds[gyv - 1, gxv - 1]
    v13 = log_odds[gyv - 1, gxv + 1]
    v14 = log_odds[gyv + 1, gxv - 1]
    v15 = log_odds[gyv + 1, gxv + 1]

    neighborhood = np.maximum.reduce([v00, v01, v02, v10, v11, v12, v13, v14, v15])

    occupied_reward = np.clip(neighborhood / LO_MAX, 0.0, 1.0)
    free_penalty = np.clip(-neighborhood / abs(LO_MIN), 0.0, 1.0)

    # Known occupied cells matter much more than unknown space. Known free
    # cells provide a useful penalty against sliding a scan through walls.
    score = np.mean(occupied_reward) - 0.25 * np.mean(free_penalty)
    return float(score)

# ============================================================
# SCAN MATCHING
# ============================================================

def search_window(points, center_x, center_y, center_h,
                  x_window, y_window, yaw_window_deg,
                  x_step, y_step, yaw_step_deg):
    best_x = center_x
    best_y = center_y
    best_h = center_h
    best_score = score_pose(points, center_x, center_y, center_h)

    x_offsets = np.arange(-x_window, x_window + x_step * 0.5, x_step)
    y_offsets = np.arange(-y_window, y_window + y_step * 0.5, y_step)
    h_offsets = np.arange(
        -math.radians(yaw_window_deg),
        math.radians(yaw_window_deg) + math.radians(yaw_step_deg) * 0.5,
        math.radians(yaw_step_deg),
    )

    for dh in h_offsets:
        th = normalize_angle(center_h + dh)
        for dx in x_offsets:
            tx = center_x + dx
            for dy in y_offsets:
                ty = center_y + dy
                sc = score_pose(points, tx, ty, th)
                if sc > best_score:
                    best_score = sc
                    best_x = tx
                    best_y = ty
                    best_h = th

    return best_x, best_y, best_h, best_score


def scan_match(points):
    if points is None or len(points) < SLAM_MIN_POINTS:
        return False, 0.0, (x, y, heading)

    initial_score = score_pose(points, x, y, heading)

    # Coarse search.
    bx, by, bh, bs = search_window(
        points, x, y, heading,
        COARSE_X_WINDOW_M, COARSE_Y_WINDOW_M,
        COARSE_YAW_WINDOW_DEG,
        COARSE_X_STEP_M, COARSE_Y_STEP_M,
        COARSE_YAW_STEP_DEG,
    )

    # Fine search centered on the coarse winner.
    bx, by, bh, bs = search_window(
        points, bx, by, bh,
        FINE_X_WINDOW_M, FINE_Y_WINDOW_M,
        FINE_YAW_WINDOW_DEG,
        FINE_X_STEP_M, FINE_Y_STEP_M,
        FINE_YAW_STEP_DEG,
    )

    dx = bx - x
    dy = by - y
    dh = normalize_angle(bh - heading)
    correction_m = math.hypot(dx, dy)
    correction_deg = abs(math.degrees(dh))

    # Require a meaningful improvement. Otherwise the matcher can slowly
    # wander through unknown map cells.
    improvement = bs - initial_score

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
# APPLY SCAN MATCH CORRECTION
# ============================================================

def apply_scan_match(new_x, new_y, new_heading, match_time):
    """Accept a LiDAR pose correction and re-anchor all heading estimates.

    This is the critical gyro-heading fix. The old mapper changed `heading`
    after scan matching but left `gyro_heading` unchanged, allowing the next
    IMU update to pull the pose back toward the old heading. Here both are
    explicitly anchored to the accepted LiDAR pose.
    """
    global x, y, heading, gyro_heading

    x = new_x
    y = new_y
    heading = normalize_angle(new_heading)
    gyro_heading = heading

    # Add an exact timestamped anchor so the next LiDAR scan can interpolate
    # from the corrected pose instead of a stale heading.
    if not pose_history or match_time >= pose_history[-1][0]:
        pose_history.append((match_time, x, y, heading))

# ============================================================
# OCCUPANCY INSERTION
# ============================================================

def ray_update(rover_gx, rover_gy, hit_gx, hit_gy):
    for gx, gy in ray_cells(rover_gx, rover_gy, hit_gx, hit_gy):
        if valid_grid(gx, gy):
            log_odds[gy, gx] += LO_FREE
    if valid_grid(hit_gx, hit_gy):
        log_odds[hit_gy, hit_gx] += LO_OCCUPIED


def insert_scan_into_map(scan, corrected_pose):
    """Insert the scan using the accepted pose.

    For a complete rotating scan, the rover may move substantially. We still
    use timestamped pose interpolation for each ray, but we apply a single
    SE(2) correction from the old current pose to the accepted pose so the
    scan and the current trajectory remain in the same corrected frame.
    """
    if not scan:
        return

    corr_x, corr_y, corr_h = corrected_pose
    old_x, old_y, old_h = x, y, heading

    # We need the pose BEFORE the accepted correction to transform each
    # historical point into the corrected world frame. The caller captures
    # this separately below, so this function receives already-corrected
    # pose and uses a fresh interpolation only for the scan geometry.
    points_to_insert = []

    # Use current pose history. The accepted correction has already been
    # appended at match_time; each scan sample still has a valid interpolated
    # pose. To avoid double-applying correction, calculate a rigid correction
    # relative to the current pose at the end of the scan.
    for host_t, packet in scan:
        local = lidar_packet_to_local(packet)
        if local is None:
            continue
        lx, ly, _ = local
        px, py, ph = pose_at(host_t)
        c = math.cos(ph)
        s = math.sin(ph)
        wx = px + lx * c - ly * s
        wy = py + lx * s + ly * c
        points_to_insert.append((wx, wy, px, py))

    if not points_to_insert:
        return

    # Because apply_scan_match may have changed the current pose, the pose
    # history already contains the corrected anchor only at the end. For map
    # insertion we use the scan points as generated and apply the same rigid
    # correction that was accepted at the scan end.
    #
    # The caller passes corrected_pose and has saved the pre-match pose in
    # `last_pre_match_pose` through the global below.
    pre_x, pre_y, pre_h = last_pre_match_pose

    dc = math.cos(corr_h - pre_h)
    ds = math.sin(corr_h - pre_h)

    # Transform old-world coordinates by the correction SE(2):
    # p_new = T_corr * T_pre^-1 * p_old.
    out = []
    for wx, wy, _, _ in points_to_insert:
        dx = wx - pre_x
        dy = wy - pre_y
        nx = corr_x + dx * dc - dy * ds
        ny = corr_y + dx * ds + dy * dc
        out.append((nx, ny))

    # Uniformly subsample for bounded CPU load.
    if len(out) > MAX_INSERT_POINTS:
        idx = np.linspace(0, len(out) - 1, MAX_INSERT_POINTS).astype(np.int32)
        out = [out[i] for i in idx]

    rover_gx, rover_gy = world_to_grid(corr_x, corr_y)
    if not valid_grid(rover_gx, rover_gy):
        return

    for wx, wy in out:
        hit_gx, hit_gy = world_to_grid(wx, wy)
        if not valid_grid(hit_gx, hit_gy):
            continue
        ray_update(rover_gx, rover_gy, hit_gx, hit_gy)

    np.clip(log_odds, LO_MIN, LO_MAX, out=log_odds)

# Global saved immediately before a scan match.
last_pre_match_pose = (0.0, 0.0, 0.0)

# ============================================================
# DISPLAY
# ============================================================

def occupancy_image():
    image = np.full((MAP_CELLS, MAP_CELLS), 0.08, dtype=np.float32)
    free = log_odds < -0.30
    occupied = log_odds > OCCUPIED_THRESHOLD
    image[free] = 0.18
    image[occupied] = 0.95
    return image

# ============================================================
# MAIN
# ============================================================

def main():
    global running, control_socket
    global completed_scans, last_match_ok, last_match_score
    global last_match_pose, last_pre_match_pose

    print("\n==============================================")
    print("       MINE ROVER CORRECTED SLAM")
    print("==============================================")
    print(f"Left  m/rev : {LEFT_METERS_PER_REV:.6f}")
    print(f"Right m/rev : {RIGHT_METERS_PER_REV:.6f}")
    print(f"Track width : {TRACK_WIDTH_M:.4f} m")
    print(f"Yaw gyro    : {GYRO_YAW_AXIS} axis, sign {GYRO_YAW_SIGN:+.0f}")
    print(f"Map         : {MAP_SIZE_M:.1f} m @ {MAP_RESOLUTION:.2f} m")
    print("\nType START and press ENTER to begin mapping.")
    print("Type RESET to reset the current run.")
    print("Type QUIT to exit.\n")

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
        occupancy_image(),
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

    trail_plot, = ax.plot([], [], color="#36c5f0", linewidth=1.6, alpha=0.9)
    rover_plot, = ax.plot([], [], marker="^", markersize=11,
                          color="#4da3ff", markeredgecolor="#d9f2ff",
                          markeredgewidth=0.8)
    heading_plot, = ax.plot([], [], color="#5cc8ff", linewidth=2)
    scan_plot, = ax.plot([], [], linestyle="None", marker=".",
                         markersize=1.2, color="#8aa0aa", alpha=0.35)

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

                for host_t, packet in lidar_items:
                    completed = add_lidar_packet(host_t, packet)
                    if completed is None:
                        continue
                    if len(completed) < SLAM_MIN_POINTS:
                        continue

                    completed_scans += 1

                    # First scan establishes the initial map without matching.
                    if completed_scans == 1:
                        last_pre_match_pose = (x, y, heading)
                        insert_scan_into_map(
                            completed,
                            (x, y, heading),
                        )
                        last_match_ok = False
                        last_match_score = 0.0
                        last_match_pose = (x, y, heading)
                        continue

                    # Do not repeatedly match a stationary scan. The map is
                    # already being updated and there is no new motion to solve.
                    current_pose = (x, y, heading)
                    if last_match_pose is not None:
                        moved_m, moved_rad = pose_distance(last_match_pose, current_pose)
                        if moved_m < MIN_SCAN_MATCH_TRANSLATION_M and \
                           math.degrees(moved_rad) < MIN_SCAN_MATCH_ROTATION_DEG:
                            last_pre_match_pose = current_pose
                            insert_scan_into_map(completed, current_pose)
                            continue

                    match_points = build_scan_points(completed)
                    if match_points is None:
                        continue

                    last_pre_match_pose = (x, y, heading)
                    ok, score, matched_pose = scan_match(match_points)
                    last_match_ok = ok
                    last_match_score = score

                    if ok:
                        apply_scan_match(*matched_pose, completed[-1][0])
                        last_match_pose = matched_pose
                        insert_scan_into_map(completed, matched_pose)
                    else:
                        # No correction: insert at odometric pose.
                        last_match_pose = current_pose
                        insert_scan_into_map(completed, current_pose)

            # Trail.
            trail_x.append(x)
            trail_y.append(y)
            if len(trail_x) > MAX_TRAIL:
                del trail_x[:-MAX_TRAIL]
                del trail_y[:-MAX_TRAIL]

            map_display.set_data(occupancy_image())

            gx, gy = world_to_grid(x, y)
            rover_plot.set_data([gx], [gy])

            heading_length = 0.5 / MAP_RESOLUTION
            hx = gx + heading_length * math.cos(heading)
            hy = gy + heading_length * math.sin(heading)
            heading_plot.set_data([gx, hx], [gy, hy])

            trail_gx = []
            trail_gy = []
            for tx, ty in zip(trail_x[-5000:], trail_y[-5000:]):
                tgx, tgy = world_to_grid(tx, ty)
                trail_gx.append(tgx)
                trail_gy.append(tgy)
            trail_plot.set_data(trail_gx, trail_gy)

            # Current scan display.
            if current_scan:
                scan_x = []
                scan_y = []
                for host_t, packet in current_scan:
                    local = lidar_packet_to_local(packet)
                    if local is None:
                        continue
                    lx, ly, _ = local
                    px, py, ph = pose_at(host_t)
                    c = math.cos(ph)
                    s = math.sin(ph)
                    wx = px + lx * c - ly * s
                    wy = py + lx * s + ly * c
                    sgx, sgy = world_to_grid(wx, wy)
                    scan_x.append(sgx)
                    scan_y.append(sgy)
                scan_plot.set_data(scan_x, scan_y)
            else:
                scan_plot.set_data([], [])

            status = (
                "MINE ROVER SLAM"
                + (" | RUNNING" if mapping_started else " | WAITING FOR START")
                + f" | POS {x:.2f}, {y:.2f} m"
                + f" | HDG {math.degrees(heading):.1f}°"
                + f" | SCANS {completed_scans}"
                + f" | MATCH {'OK' if last_match_ok else 'ODOM'} {last_match_score:.2f}"
                + f" | V {encoder_velocity:.2f} m/s"
                + f" | IMU {'OK' if imu_calibrated else 'WAIT'}"
            )
            ax.set_title(status, loc="left", fontsize=11, color="#dce7eb")

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
        plt.ioff()
        plt.show()


if __name__ == "__main__":
    main()
