import socket
import json
import time
import math
from datetime import datetime, timezone


def wrap360(deg: float) -> float:
    return deg % 360.0


class UdpSimSender:
    """
    Sends EntityState messages over UDP at a fixed rate.

    Convention:
      - Screen/world space is 800x600 pixels for the demo.
      - 0° = up (north), 90° = right (east)
      - heading stored as [0,360)
    """

    def __init__(self, dest_ip="127.0.0.1", dest_port=30001, hz=20):
        self.dest = (dest_ip, dest_port)
        self.hz = hz
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        # Sim bounds
        self.w, self.h = 800, 600
        self.margin = 50

        # State
        self.entity_id = 1001
        self.entity_type = "CONTACT"
        self.x, self.y = self.w / 2.0, self.h / 2.0
        self.heading = 0.0  # [0,360)
        self.speed = 1.5
        self.status = "OK"

        self.seq = 0

    def step(self, dt: float):
        # Kinematics: 0° up, y down on screen so subtract cos component
        rad = math.radians(self.heading)
        self.x += math.sin(rad) * self.speed
        self.y -= math.cos(rad) * self.speed

        left = self.margin
        right = self.w - self.margin
        top = self.margin
        bottom = self.h - self.margin

        # Bounce top/bottom (invert Y velocity)
        if self.y <= top or self.y >= bottom:
            self.heading = wrap360(180.0 - self.heading)
            self.y = top + 1 if self.y <= top else bottom - 1

        # Bounce left/right (invert X velocity)
        if self.x <= left or self.x >= right:
            self.heading = wrap360(360.0 - self.heading)
            self.x = left + 1 if self.x <= left else right - 1

        self.heading = wrap360(self.heading)

    def send(self):
        self.seq += 1
        msg = {
            "msg_type": "EntityState",
            "entity_id": self.entity_id,
            "entity_type": self.entity_type,
            "x": float(self.x),
            "y": float(self.y),
            "heading_deg": float(self.heading),
            "speed": float(self.speed),
            "status": self.status,
            "seq": self.seq,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        }
        data = json.dumps(msg).encode("utf-8")
        self.sock.sendto(data, self.dest)

    def run(self):
        print(f"[sender] UDP -> {self.dest} @ {self.hz} Hz (Ctrl+C to stop)")
        interval = 1.0 / float(self.hz)
        last = time.perf_counter()

        try:
            while True:
                now = time.perf_counter()
                dt = now - last
                last = now

                self.step(dt)
                self.send()

                time.sleep(interval)

        except KeyboardInterrupt:
            print("\n[sender] Stopped.")
        finally:
            try:
                self.sock.close()
            except Exception:
                pass


if __name__ == "__main__":
    UdpSimSender().run()