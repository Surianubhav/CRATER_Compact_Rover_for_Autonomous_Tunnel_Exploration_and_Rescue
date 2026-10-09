import socket
import json

UDP_PORT = 4212

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(("0.0.0.0", UDP_PORT))
sock.settimeout(1)

print("Listening for odometry...")
print("Drive the rover and watch the values.\n")

while True:
    try:
        data, addr = sock.recvfrom(4096)
        msg = json.loads(data.decode())

        if msg.get("device") == "odom":
            print(
                f"\rLeft: {msg['left']:10.5f} rev   "
                f"Right: {msg['right']:10.5f} rev   "
                f"seq: {msg['seq']:6d}",
                end="",
                flush=True
            )

    except KeyboardInterrupt:
        print("\nStopped.")
        break

    except socket.timeout:
        pass

    except Exception as e:
        print("\nError:", e)