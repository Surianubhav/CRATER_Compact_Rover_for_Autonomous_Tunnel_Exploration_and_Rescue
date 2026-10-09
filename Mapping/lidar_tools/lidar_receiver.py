import socket

UDP_IP = "0.0.0.0"
UDP_PORT = 4210

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind((UDP_IP, UDP_PORT))

print(f"Listening for LiDAR data on UDP port {UDP_PORT}...")

while True:
    data, addr = sock.recvfrom(1024)

    message = data.decode().strip()

    print(f"From {addr[0]}: {message}")