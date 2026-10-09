import socket
import json
import threading
import time

# ============================================================
# SETTINGS
# ============================================================

LIDAR_PORT = 4211
ODOM_PORT = 4212

BUFFER_SIZE = 2048

# ============================================================
# SHARED DATA
# ============================================================

latest_lidar = None
latest_odom = None

data_lock = threading.Lock()

# ============================================================
# LIDAR RECEIVER
# ============================================================

def lidar_receiver():

    global latest_lidar

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    sock.bind(("0.0.0.0", LIDAR_PORT))

    print(f"[LIDAR] Listening on UDP port {LIDAR_PORT}")

    while True:

        try:

            data, address = sock.recvfrom(BUFFER_SIZE)

            receive_time = time.time()

            packet = json.loads(data.decode("utf-8"))

            if packet.get("device") != "lidar":
                continue

            with data_lock:
                latest_lidar = {
                    "packet": packet,
                    "receive_time": receive_time,
                    "address": address
                }

        except Exception as e:

            print("[LIDAR ERROR]", e)


# ============================================================
# ODOMETRY RECEIVER
# ============================================================

def odom_receiver():

    global latest_odom

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    sock.bind(("0.0.0.0", ODOM_PORT))

    print(f"[ODOM] Listening on UDP port {ODOM_PORT}")

    while True:

        try:

            data, address = sock.recvfrom(BUFFER_SIZE)

            receive_time = time.time()

            packet = json.loads(data.decode("utf-8"))

            if packet.get("device") != "odom":
                continue

            with data_lock:
                latest_odom = {
                    "packet": packet,
                    "receive_time": receive_time,
                    "address": address
                }

        except Exception as e:

            print("[ODOM ERROR]", e)


# ============================================================
# DISPLAY
# ============================================================

def display():

    global latest_lidar
    global latest_odom

    while True:

        time.sleep(0.1)

        with data_lock:

            lidar = latest_lidar
            odom = latest_odom

        print("\033[2J\033[H", end="")

        print("==============================================")
        print("        ESP32 ROVER DATA RECEIVER")
        print("==============================================")

        # ----------------------------------------------------
        # LIDAR
        # ----------------------------------------------------

        print("\n[LIDAR]")

        if lidar:

            p = lidar["packet"]

            print("ESP IP       :", lidar["address"][0])
            print("ESP timestamp:", p["t"])
            print("Angle        :", p["angle"], "deg")
            print("Distance     :", p["distance"], "cm")

        else:

            print("Waiting for LiDAR data...")

        # ----------------------------------------------------
        # ODOMETRY
        # ----------------------------------------------------

        print("\n[ODOMETRY]")

        if odom:

            p = odom["packet"]

            print("ESP IP       :", odom["address"][0])
            print("ESP timestamp:", p["t"])
            print("Left encoder :", p["left"])
            print("Right encoder:", p["right"])

            print(
                "Gyro         :",
                "X =", p["gx"],
                "Y =", p["gy"],
                "Z =", p["gz"]
            )

        else:

            print("Waiting for odometry data...")

        # ----------------------------------------------------
        # SYSTEM TIME
        # ----------------------------------------------------

        print("\n[RECEIVER]")

        print(
            "Laptop time:",
            time.time()
        )

        print("\nPress Ctrl+C to stop.")


# ============================================================
# MAIN
# ============================================================

def main():

    print("Starting UDP receiver...")
    print()

    lidar_thread = threading.Thread(
        target=lidar_receiver,
        daemon=True
    )

    odom_thread = threading.Thread(
        target=odom_receiver,
        daemon=True
    )

    display_thread = threading.Thread(
        target=display,
        daemon=True
    )

    lidar_thread.start()
    odom_thread.start()
    display_thread.start()

    try:

        while True:
            time.sleep(1)

    except KeyboardInterrupt:

        print("\nStopping receiver...")


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    main()