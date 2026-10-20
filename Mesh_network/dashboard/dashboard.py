#!/usr/bin/env python3
# CRATER MINE COMMUNICATION NETWORK - laptop dashboard (Tkinter + pyserial)
import math
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    raise SystemExit("pyserial is missing. Run:  py -m pip install pyserial")

NAMES = {1: "BASE", 2: "ROVER", 3: "RELAY1", 4: "RELAY2"}
POS = {2: (100, 170), 3: (290, 80), 4: (480, 260), 1: (670, 170)}
LINKS = [(2, 3), (3, 4), (4, 1), (2, 4), (3, 1)]

BG = "#0b1624"; PANEL = "#12263d"; EDGE = "#24415f"; TXT = "#e8f1f8"; MUTED = "#7f93a8"
GREEN = "#2ecc71"; RED = "#e74c3c"; ORANGE = "#f39c12"; CYAN = "#1abc9c"; BLUE = "#3b82f6"


class App:
    def __init__(self, root):
        self.root = root
        root.title("CRATER - Mine Communication Network")
        root.configure(bg=BG)
        root.geometry("1300x840")

        self.q = queue.Queue()
        self.ser = None
        self.stop_flag = threading.Event()
        self.last_line = 0.0
        self.online = {2: None, 3: None, 4: None}
        self.route_nodes = []
        self.route_ok = False
        self.have_route_ever = False
        self.last_tel = 0.0
        self.total_rx = 0
        self.last_pkt = None
        self.first_pkt = 0
        self.delivered = 0
        self.lost = 0
        self.rtt = 0
        self.route_changes = 0
        self.retry = 0
        self.retry_logged = 0
        self.filter_on = None
        self.stopped = False
        self.tel = None

        self.build_ui()
        self.refresh_ports()
        self.log("Dashboard started. Pick the BASE COM port and press CONNECT.", "info")
        self.tick()

    # ------------------------------------------------------------ UI
    def mk(self, parent, title, row, col, size=14, colspan=1):
        f = tk.Frame(parent, bg=PANEL)
        f.grid(row=row, column=col, columnspan=colspan, sticky="w", padx=14, pady=5)
        tk.Label(f, text=title, font=("Segoe UI", 9), fg=MUTED, bg=PANEL).pack(anchor="w")
        v = tk.Label(f, text="-", font=("Segoe UI", size, "bold"), fg=TXT, bg=PANEL)
        v.pack(anchor="w")
        return v

    def build_ui(self):
        r = self.root
        tk.Label(r, text="CRATER MINE COMMUNICATION NETWORK", font=("Segoe UI", 22, "bold"),
                 fg=TXT, bg=BG).pack(pady=(10, 0))
        self.lbl_filter = tk.Label(r, text="", font=("Segoe UI", 10), fg=ORANGE, bg=BG)
        self.lbl_filter.pack()

        bar = tk.Frame(r, bg=BG)
        bar.pack(fill="x", padx=14, pady=6)
        tk.Label(bar, text="BASE port:", fg=TXT, bg=BG, font=("Segoe UI", 11)).pack(side="left")
        self.port_var = tk.StringVar()
        self.port_box = ttk.Combobox(bar, textvariable=self.port_var, width=14, state="readonly")
        self.port_box.pack(side="left", padx=6)
        tk.Button(bar, text="Refresh", command=self.refresh_ports).pack(side="left")
        self.btn_conn = tk.Button(bar, text="CONNECT", width=12, command=self.toggle_connect,
                                  bg=BLUE, fg="white", font=("Segoe UI", 10, "bold"))
        self.btn_conn.pack(side="left", padx=8)
        self.lbl_link = tk.Label(bar, text="not connected", fg=MUTED, bg=BG, font=("Segoe UI", 10))
        self.lbl_link.pack(side="left", padx=8)

        main = tk.Frame(r, bg=BG)
        main.pack(fill="both", expand=True, padx=14, pady=4)
        left = tk.Frame(main, bg=BG)
        left.pack(side="left", fill="y")
        right = tk.Frame(main, bg=BG)
        right.pack(side="left", fill="both", expand=True, padx=(12, 0))

        self.canvas = tk.Canvas(left, width=770, height=340, bg=PANEL,
                                highlightthickness=1, highlightbackground=EDGE)
        self.canvas.pack()

        sp = tk.Frame(left, bg=PANEL, highlightthickness=1, highlightbackground=EDGE)
        sp.pack(fill="x", pady=8)
        self.v_route = self.mk(sp, "ACTIVE ROUTE", 0, 0, size=18, colspan=5)
        self.v_status = self.mk(sp, "STATUS", 1, 0, size=14)
        self.v_pkts = self.mk(sp, "PACKETS DELIVERED", 1, 1, size=14)
        self.v_last = self.mk(sp, "LAST PACKET", 1, 2, size=14)
        self.v_rtt = self.mk(sp, "ROUND-TRIP LATENCY", 1, 3, size=14)
        self.v_hops = self.mk(sp, "HOPS", 1, 4, size=14)
        self.v_chg = self.mk(sp, "ROUTE CHANGES", 2, 0, size=12)
        self.v_lost = self.mk(sp, "PACKETS LOST", 2, 1, size=12)
        self.v_state = self.mk(sp, "ROVER STATE", 2, 2, size=12)
        self.v_retry = self.mk(sp, "RETRY COUNTER", 2, 3, size=12)

        tp = tk.Frame(left, bg=PANEL, highlightthickness=1, highlightbackground=EDGE)
        tp.pack(fill="x")
        tk.Label(tp, text="TELEMETRY (simulated values)", font=("Segoe UI", 9, "bold"),
                 fg=MUTED, bg=PANEL).grid(row=0, column=0, columnspan=4, sticky="w", padx=14, pady=(6, 0))
        self.tv = {}
        for i, key in enumerate(["TEMP", "HUMIDITY", "CH4", "CO", "BATTERY", "ROLL", "PITCH"]):
            self.tv[key] = self.mk(tp, key, 1 + i // 4, i % 4, size=15)

        cp = tk.Frame(left, bg=PANEL, highlightthickness=1, highlightbackground=EDGE)
        cp.pack(fill="x", pady=8)
        tk.Label(cp, text="COMMANDS  BASE -> ROVER", font=("Segoe UI", 9, "bold"),
                 fg=MUTED, bg=PANEL).pack(anchor="w", padx=14, pady=(6, 0))
        row = tk.Frame(cp, bg=PANEL)
        row.pack(anchor="w", padx=10, pady=6)
        for name in ["PING", "STATUS", "STOP", "GO"]:
            tk.Button(row, text=name, width=9, font=("Segoe UI", 10, "bold"),
                      command=lambda c=name: self.send_cmd(c)).pack(side="left", padx=4)
        self.v_resp = tk.Label(cp, text="last response: -", font=("Segoe UI", 10), fg=TXT, bg=PANEL)
        self.v_resp.pack(anchor="w", padx=14, pady=(0, 8))

        tk.Label(right, text="EVENT LOG", font=("Segoe UI", 11, "bold"), fg=TXT, bg=BG).pack(anchor="w")
        lf = tk.Frame(right, bg=BG)
        lf.pack(fill="both", expand=True)
        sb = tk.Scrollbar(lf)
        sb.pack(side="right", fill="y")
        self.logbox = tk.Text(lf, bg="#08111d", fg=TXT, font=("Consolas", 10), wrap="word",
                              state="disabled", yscrollcommand=sb.set, relief="flat")
        self.logbox.pack(side="left", fill="both", expand=True)
        sb.config(command=self.logbox.yview)
        for tag, col in [("good", GREEN), ("bad", RED), ("warn", ORANGE), ("info", TXT), ("pkt", "#6fa8c9")]:
            self.logbox.tag_config(tag, foreground=col)

    def log(self, msg, tag="info"):
        ts = time.strftime("%H:%M:%S")
        self.logbox.configure(state="normal")
        self.logbox.insert("end", f"{ts}  {msg}\n", tag)
        if int(self.logbox.index("end-1c").split(".")[0]) > 600:
            self.logbox.delete("1.0", "60.0")
        self.logbox.see("end")
        self.logbox.configure(state="disabled")

    # ------------------------------------------------------------ serial
    def refresh_ports(self):
        ports = [p.device for p in serial.tools.list_ports.comports()]
        self.port_box["values"] = ports
        if ports and not self.port_var.get():
            self.port_var.set(ports[0])

    def toggle_connect(self):
        if self.ser:
            self.disconnect()
            return
        port = self.port_var.get()
        if not port:
            self.log("Choose a COM port first.", "warn")
            return
        try:
            s = serial.Serial()
            s.port = port
            s.baudrate = 115200
            s.timeout = 0.2
            s.dtr = False
            s.rts = False
            s.open()
        except Exception as e:
            self.log(f"Cannot open {port}: {e}  (close Arduino Serial Monitor first!)", "bad")
            return
        self.ser = s
        self.stop_flag.clear()
        self.last_line = time.time()
        threading.Thread(target=self.read_loop, args=(s,), daemon=True).start()
        self.btn_conn.config(text="DISCONNECT")
        self.log(f"Connected to {port}", "good")

    def disconnect(self):
        self.stop_flag.set()
        try:
            if self.ser:
                self.ser.close()
        except Exception:
            pass
        self.ser = None
        self.btn_conn.config(text="CONNECT")
        self.log("Disconnected.", "warn")

    def read_loop(self, s):
        buf = b""
        while not self.stop_flag.is_set():
            try:
                data = s.read(256)
            except Exception as e:
                self.q.put(("ERR", str(e)))
                return
            if data:
                buf += data
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    self.q.put(("LINE", line.decode("utf-8", "ignore")))

    def send_cmd(self, name):
        if not self.ser:
            self.log("Not connected to BASE.", "warn")
            return
        try:
            self.ser.write(f"CMD,{name}\n".encode())
            self.log(f"COMMAND {name} sent  BASE -> ROVER", "info")
        except Exception as e:
            self.log(f"Write failed: {e}", "bad")

    # ------------------------------------------------------------ protocol
    def route_text(self, nodes):
        return " -> ".join(NAMES.get(n, f"N{n}") for n in nodes)

    def handle_line(self, line):
        self.last_line = time.time()
        p = line.strip().split(",")
        try:
            if p[0] == "ST":
                self.on_status(p)
            elif p[0] == "TEL":
                self.on_telemetry(p)
            elif p[0] == "RSP":
                self.on_response(line.strip().split(",", 6))
            elif p[0] == "EVT":
                self.log(",".join(p[1:]), "warn")
        except (ValueError, IndexError):
            pass

    def mark_lost(self):
        if not self.route_ok:
            return
        self.route_ok = False
        self.log("ROUTE LOST", "bad")
        self.log(f"OLD ROUTE: {self.route_text(self.route_nodes)}", "info")
        self.log("SEARCHING FOR ROUTE...", "warn")

    def on_status(self, p):
        metrics = {2: int(p[2]), 3: int(p[4]), 4: int(p[6])}
        retry = int(p[8])
        self.filter_on = (p[9].strip() == "1")
        for nid, m in metrics.items():
            on = m < 255
            prev = self.online[nid]
            self.online[nid] = on
            if prev is not None and prev != on:
                if nid == 2:
                    self.log("ROVER " + ("REACHABLE" if on else "UNREACHABLE"), "good" if on else "bad")
                else:
                    self.log(f"{NAMES[nid]} " + ("ONLINE" if on else "OFFLINE"), "good" if on else "bad")
                    if on:
                        self.log("ROUTE DISCOVERY...", "info")
                if not on and nid in self.route_nodes:
                    self.mark_lost()
        if retry > 0 and retry != self.retry_logged:
            if retry == 1:
                self.log("NO ROUTE AVAILABLE", "bad")
            self.log(f"RETRYING...  RETRY #{retry}", "warn")
        self.retry_logged = retry
        self.retry = retry

    def on_telemetry(self, p):
        pkt = int(p[1])
        nodes = [int(x) for x in p[2].split("-")]
        self.tel = dict(temp=float(p[3]), hum=float(p[4]), ch4=int(p[5]), co=int(p[6]),
                        roll=float(p[7]), pitch=float(p[8]), batt=float(p[9]))
        self.rtt = int(p[10])
        self.stopped = bool(int(p[11]) & 1)

        if self.last_pkt is None or pkt < self.last_pkt:
            self.first_pkt = pkt
            self.delivered = 0
        self.last_pkt = pkt
        self.delivered += 1
        self.total_rx += 1
        self.lost = max(0, (pkt - self.first_pkt + 1) - self.delivered)
        self.last_tel = time.time()

        txt = self.route_text(nodes)
        prev = self.route_nodes
        if not self.route_ok:
            self.log("ROUTE FOUND", "good")
            self.log(f"NEW ROUTE: {txt}", "good")
            if self.have_route_ever:
                self.log("ROUTE RESTORED", "good")
                if nodes != prev:
                    self.route_changes += 1
        elif nodes != prev:
            self.route_changes += 1
            self.log(f"ROUTE CHANGED  OLD: {self.route_text(prev)}", "warn")
            self.log(f"NEW ROUTE: {txt}", "good")
        self.route_ok = True
        self.have_route_ever = True
        self.route_nodes = nodes
        rtt = f"  RTT {self.rtt} ms" if self.rtt else ""
        self.log(f"PACKET #{pkt} DELIVERED  {txt}{rtt}", "pkt")

    def on_response(self, p):
        cmd, cid, path, rtt, result = p[1], p[2], p[3], p[4], p[5]
        extra = p[6] if len(p) > 6 else ""
        if path in ("-", ""):
            txt = "-"
        else:
            txt = self.route_text([int(x) for x in path.split("-")])
        tag = "good" if result == "OK" else "bad"
        self.log(f"RESPONSE {cmd}: {result} {extra}  via {txt}  {rtt} ms", tag)
        self.v_resp.config(text=f"last response: {cmd} -> {result} {extra}  ({rtt} ms)")

    # ------------------------------------------------------------ periodic
    def tick(self):
        try:
            while True:
                kind, val = self.q.get_nowait()
                if kind == "LINE":
                    self.handle_line(val)
                elif kind == "ERR":
                    self.log(f"Serial error: {val}", "bad")
                    self.disconnect()
        except queue.Empty:
            pass
        now = time.time()
        if self.route_ok and now - self.last_tel > 2.4:
            self.mark_lost()
        self.refresh_labels()
        self.draw()
        self.root.after(150, self.tick)

    def base_alive(self):
        return self.ser is not None and (time.time() - self.last_line) < 4.0

    def refresh_labels(self):
        alive = self.base_alive()
        self.lbl_link.config(text="BASE linked" if alive else ("no data from BASE" if self.ser else "not connected"),
                             fg=GREEN if alive else MUTED)
        if self.filter_on:
            self.lbl_filter.config(text="VIRTUAL TUNNEL RANGE ON - boards share one desk, link table limits who can hear whom")
        elif self.filter_on is False:
            self.lbl_filter.config(text="REAL RF MODE - every board that can hear another is a neighbour")
        if not alive:
            self.v_route.config(text="-", fg=MUTED)
            self.v_status.config(text="DISCONNECTED", fg=MUTED)
        elif self.route_ok:
            self.v_route.config(text=self.route_text(self.route_nodes), fg=GREEN)
            self.v_status.config(text="CONNECTED", fg=GREEN)
        elif self.have_route_ever:
            self.v_route.config(text="NO ROUTE AVAILABLE", fg=RED)
            self.v_status.config(text="NO ROUTE", fg=RED)
        else:
            self.v_route.config(text="waiting for first packet...", fg=MUTED)
            self.v_status.config(text="WAITING", fg=ORANGE)
        self.v_pkts.config(text=str(self.total_rx))
        self.v_last.config(text=f"#{self.last_pkt}" if self.last_pkt is not None else "-")
        self.v_rtt.config(text=f"{self.rtt} ms" if self.rtt else "-")
        self.v_hops.config(text=str(len(self.route_nodes) - 1) if self.route_ok else "-")
        self.v_chg.config(text=str(self.route_changes))
        self.v_lost.config(text=str(self.lost))
        self.v_state.config(text="STOPPED" if self.stopped else ("RUNNING" if self.tel else "-"),
                            fg=ORANGE if self.stopped else TXT)
        self.v_retry.config(text=f"#{self.retry}" if self.retry else "-", fg=RED if self.retry else TXT)
        t = self.tel
        fresh = self.route_ok
        col = TXT if fresh else MUTED
        vals = {
            "TEMP": f"{t['temp']:.1f} C" if t else "-",
            "HUMIDITY": f"{t['hum']:.1f} %" if t else "-",
            "CH4": f"{t['ch4']}" if t else "-",
            "CO": f"{t['co']}" if t else "-",
            "BATTERY": f"{t['batt']:.2f} V" if t else "-",
            "ROLL": f"{t['roll']:.1f} deg" if t else "-",
            "PITCH": f"{t['pitch']:.1f} deg" if t else "-",
        }
        for k, v in vals.items():
            self.tv[k].config(text=v, fg=col)

    def draw(self):
        c = self.canvas
        c.delete("all")
        alive = self.base_alive()
        for a, b in LINKS:
            c.create_line(*POS[a], *POS[b], fill=EDGE, width=2)
        c.create_line(*POS[2], *POS[1], fill=EDGE, width=2, dash=(4, 6))

        if alive and self.route_ok and len(self.route_nodes) > 1:
            pts = [POS[n] for n in self.route_nodes if n in POS]
            for i in range(len(pts) - 1):
                c.create_line(*pts[i], *pts[i + 1], fill=GREEN, width=7,
                              arrow=tk.LAST, arrowshape=(16, 20, 7))
            lens = [math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
            total = sum(lens)
            tpos = ((time.time() % 1.4) / 1.4) * total
            for i, L in enumerate(lens):
                if tpos <= L:
                    f = tpos / L if L else 0
                    x = pts[i][0] + (pts[i + 1][0] - pts[i][0]) * f
                    y = pts[i][1] + (pts[i + 1][1] - pts[i][1]) * f
                    c.create_oval(x - 8, y - 8, x + 8, y + 8, fill="#ffffff", outline=CYAN, width=2)
                    break
                tpos -= L
        elif alive and self.have_route_ever and not self.route_ok:
            c.create_text(385, 24, text="NO ROUTE AVAILABLE", fill=RED, font=("Segoe UI", 18, "bold"))

        for nid, (x, y) in POS.items():
            if not alive:
                state = None
            elif nid == 1:
                state = True
            else:
                state = self.online.get(nid)
            outline = GREEN if state else (RED if state is False else MUTED)
            label = "ONLINE" if state else ("OFFLINE" if state is False else "-")
            on_route = self.route_ok and nid in self.route_nodes
            if on_route:
                c.create_oval(x - 50, y - 50, x + 50, y + 50, outline=CYAN, width=2)
            c.create_oval(x - 42, y - 42, x + 42, y + 42, fill=PANEL, outline=outline, width=4)
            c.create_text(x, y - 8, text=NAMES[nid], fill=TXT, font=("Segoe UI", 12, "bold"))
            c.create_text(x, y + 14, text=label, fill=outline, font=("Segoe UI", 9, "bold"))


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()