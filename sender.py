import socket
import json
import time
import math
import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from random import Random


def wrap360(deg: float) -> float:
    return deg % 360.0


@dataclass
class Entity:
    entity_id: int
    entity_type: str
    x: float
    y: float
    heading: float   # [0,360)
    speed: float
    status: str = "OK"


class UdpSimSender:
    """
    Sends EntityState messages over UDP at a fixed rate.

    Convention:
      - Demo world is 800x600 (screen-like coordinates).
      - 0° = up (north), 90° = right (east)
      - heading stored as [0,360)
    """

    def __init__(self, dest_ip="127.0.0.1", dest_port=30001, hz=20, entities=1, seed=1):
        self.dest = (dest_ip, dest_port)
        self.hz = hz
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.rng = Random(seed)

        # Sim bounds
        self.w, self.h = 800, 600
        self.margin = 50

        self.seq = 0
        self.entities = self._init_entities(count=entities)

    def _init_entities(self, count: int):
        # Some types to rotate through
        types = ["SUB", "UUV", "SHIP", "BUI", "DRONE", "CONTACT"]
        out = []
        for i in range(count):
            eid = 1001 + i
            etype = types[i % len(types)]
            x = self.rng.uniform(self.margin + 10, self.w - self.margin - 10)
            y = self.rng.uniform(self.margin + 10, self.h - self.margin - 10)
            heading = self.rng.uniform(0, 360)
            speed = self.rng.uniform(0.8, 4.0) if etype != "BUI" else 0.0
            out.append(Entity(eid, etype, x, y, heading, speed))
        return out

    def _bounce(self, ent: Entity):
        left = self.margin
        right = self.w - self.margin
        top = self.margin
        bottom = self.h - self.margin

        # Bounce top/bottom (invert Y velocity)
        if ent.y <= top or ent.y >= bottom:
            ent.heading = wrap360(180.0 - ent.heading)
            ent.y = top + 1 if ent.y <= top else bottom - 1

        # Bounce left/right (invert X velocity)
        if ent.x <= left or ent.x >= right:
            ent.heading = wrap360(360.0 - ent.heading)
            ent.x = left + 1 if ent.x <= left else right - 1

        ent.heading = wrap360(ent.heading)

    def step(self, dt: float):
        # Small heading wander (looks more organic)
        for ent in self.entities:
            if ent.speed > 0.01:
                ent.heading = wrap360(ent.heading + (self.rng.random() - 0.5) * 10.0 * dt)

                rad = math.radians(ent.heading)
                ent.x += math.sin(rad) * ent.speed
                ent.y -= math.cos(rad) * ent.speed

                self._bounce(ent)

    def send_all(self):
        self.seq += 1
        ts = datetime.now(timezone.utc).isoformat()

        for ent in self.entities:
            msg = {
                "msg_type": "EntityState",
                "entity_id": ent.entity_id,
                "entity_type": ent.entity_type,
                "x": float(ent.x),
                "y": float(ent.y),
                "heading_deg": float(ent.heading),
                "speed": float(ent.speed),
                "status": ent.status,
                "seq": self.seq,
                "timestamp_utc": ts,
            }
            data = json.dumps(msg).encode("utf-8")
            self.sock.sendto(data, self.dest)

    def run(self):
        print(f"[sender] UDP -> {self.dest} @ {self.hz} Hz | entities={len(self.entities)} (Ctrl+C to stop)")
        interval = 1.0 / float(self.hz)
        last = time.perf_counter()

        try:
            while True:
                now = time.perf_counter()
                dt = now - last
                last = now

                self.step(dt)
                self.send_all()

                time.sleep(interval)

        except KeyboardInterrupt:
            print("\n[sender] Stopped.")
        finally:
            try:
                self.sock.close()
            except Exception:
                pass


def main():
    parser = argparse.ArgumentParser(description="UDP EntityState telemetry sender (PORTS demo).")
    parser.add_argument("--ip", default="127.0.0.1", help="Destination IP (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=30001, help="Destination UDP port (default: 30001)")
    parser.add_argument("--hz", type=int, default=20, help="Send rate in Hz (default: 20)")
    parser.add_argument("--entities", type=int, default=4, help="Number of entities to simulate (default: 4)")
    parser.add_argument("--seed", type=int, default=1, help="RNG seed (default: 1)")
    args = parser.parse_args()

    UdpSimSender(
        dest_ip=args.ip,
        dest_port=args.port,
        hz=args.hz,
        entities=max(1, args.entities),
        seed=args.seed,
    ).run()


if __name__ == "__main__":
    main()