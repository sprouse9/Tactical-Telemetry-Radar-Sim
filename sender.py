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

    def __init__(
        self,
        dest_ip="127.0.0.1",
        dest_port=30001,
        hz=20,
        entities=1,
        seed=1,
        faults_enabled=True,
        fault_check_interval=1.0,
        fault_trigger_prob=0.10,
        fault_debug=True,
    ):
        self.dest = (dest_ip, dest_port)
        self.hz = hz
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.rng = Random(seed)

        # Sim bounds
        self.w, self.h = 800, 600
        # Sim bounds (reserve space for HUD at top)
        self.left_margin = 20
        self.right_margin = 20
        self.top_margin = 110
        self.bottom_margin = 20

        self.seq = 0
        self.entities = self._init_entities(count=entities)

        # Fault injection config
        self.faults_enabled = faults_enabled
        self.fault_check_interval = max(0.1, float(fault_check_interval))
        self.fault_trigger_prob = max(0.0, min(1.0, float(fault_trigger_prob)))
        self.fault_debug = fault_debug
        self.last_fault_check = time.time()

        # Per-entity fault states (keyed by entity_id int)
        self.faults = {ent.entity_id: self._default_fault_state() for ent in self.entities}

        # Optional counters (useful later if you want sender-side stats)
        self.total_packets_attempted = 0
        self.total_packets_sent = 0
        self.total_packets_dropped_fault = 0
        self.total_packets_jammed_fault = 0

    def _default_fault_state(self):
        return {
            "jam_until": 0.0,               # if now < jam_until, suppress sends
            "drop_burst_remaining": 0,      # drop next N packets
            "heading_noise_until": 0.0,     # if now < this, apply random heading noise
            "heading_noise_deg": 0.0,       # max +/- noise
        }

    def _init_entities(self, count: int):
        # Some types to rotate through
        types = ["SUB", "UUV", "SHIP", "BUI", "DRONE", "CONTACT"]
        out = []
        for i in range(count):
            eid = 1001 + i
            etype = types[i % len(types)]
            x = self.rng.uniform(self.left_margin + 10, self.w - self.right_margin - 10)
            y = self.rng.uniform(self.top_margin + 10, self.h - self.bottom_margin - 10)
            heading = self.rng.uniform(0, 360)
            speed = self.rng.uniform(0.8, 4.0) if etype != "BUI" else 0.0
            out.append(Entity(eid, etype, x, y, heading, speed))
        return out

    def _bounce(self, ent: Entity):
        left = self.left_margin
        right = self.w - self.right_margin
        top = self.top_margin
        bottom = self.h - self.bottom_margin

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

    # ---------------------------
    # Fault injection
    # ---------------------------

    def _fault_active(self, f: dict, now_ts: float) -> bool:
        return (
            (now_ts < f["jam_until"]) or
            (f["drop_burst_remaining"] > 0) or
            (now_ts < f["heading_noise_until"])
        )

    def maybe_inject_random_fault(self):
        if not self.faults_enabled or not self.entities:
            return

        now_ts = time.time()

        # Throttle checks (e.g., once per second)
        if (now_ts - self.last_fault_check) < self.fault_check_interval:
            return
        self.last_fault_check = now_ts

        # Trigger chance
        if self.rng.random() > self.fault_trigger_prob:
            return

        # Pick a random entity
        ent = self.rng.choice(self.entities)
        eid = ent.entity_id
        f = self.faults.setdefault(eid, self._default_fault_state())

        # Keep it simple: only trigger if entity isn't already faulted
        if self._fault_active(f, now_ts):
            return

        # Choose a fault type
        fault_type = self.rng.choice(["jam", "drop_burst", "heading_noise"])

        if fault_type == "jam":
            dur = self.rng.uniform(2.0, 6.0)
            f["jam_until"] = now_ts + dur
            if self.fault_debug:
                print(f"[FAULT] EID {eid} ({ent.entity_type}) JAM / LOSS OF SIGNAL for {dur:.1f}s")

        elif fault_type == "drop_burst":
            count = self.rng.randint(5, 20)
            f["drop_burst_remaining"] += count
            if self.fault_debug:
                print(f"[FAULT] EID {eid} ({ent.entity_type}) DROP BURST next {count} packets")

        elif fault_type == "heading_noise":
            dur = self.rng.uniform(3.0, 8.0)
            deg = self.rng.choice([5.0, 8.0, 12.0])
            f["heading_noise_until"] = now_ts + dur
            f["heading_noise_deg"] = deg
            if self.fault_debug:
                print(f"[FAULT] EID {eid} ({ent.entity_type}) HEADING NOISE ±{deg:.0f}° for {dur:.1f}s")

    def apply_faults_to_msg(self, ent: Entity, msg: dict):
        """
        Apply active faults for this entity.
        Returns: (should_send: bool, out_msg: dict)
        """
        now_ts = time.time()
        eid = ent.entity_id
        f = self.faults.setdefault(eid, self._default_fault_state())

        # 1) Jam / loss of signal (suppress send)
        if now_ts < f["jam_until"]:
            self.total_packets_jammed_fault += 1
            return False, msg

        # 2) Drop burst (drop next N sends)
        if f["drop_burst_remaining"] > 0:
            f["drop_burst_remaining"] -= 1
            self.total_packets_dropped_fault += 1
            return False, msg

        # 3) Heading noise (modify outgoing heading only, not the true entity state)
        out = dict(msg)
        if now_ts < f["heading_noise_until"]:
            noise = self.rng.uniform(-f["heading_noise_deg"], f["heading_noise_deg"])
            try:
                out["heading_deg"] = wrap360(float(out.get("heading_deg", 0.0)) + noise)
                # Optional status hint for receiver panel/debugging
                out["status"] = "NOISY"
            except Exception:
                pass
        else:
            # Expired noise cleanup
            f["heading_noise_deg"] = 0.0

        return True, out

    # ---------------------------
    # Send loop
    # ---------------------------

    def send_all(self):
        self.seq += 1
        ts = datetime.now(timezone.utc).isoformat()

        # Potentially start a new random fault event
        self.maybe_inject_random_fault()

        for ent in self.entities:
            self.total_packets_attempted += 1

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

            if self.faults_enabled:
                should_send, msg = self.apply_faults_to_msg(ent, msg)
                if not should_send:
                    continue

            data = json.dumps(msg).encode("utf-8")
            self.sock.sendto(data, self.dest)
            self.total_packets_sent += 1

    def run(self):
        print(
            f"[sender] UDP -> {self.dest} @ {self.hz} Hz | entities={len(self.entities)} "
            f"| faults={'ON' if self.faults_enabled else 'OFF'} (Ctrl+C to stop)"
        )
        if self.faults_enabled:
            print(
                f"[sender] Faults: random events every ~{self.fault_check_interval:.1f}s check, "
                f"trigger_prob={self.fault_trigger_prob:.2f}, debug={'ON' if self.fault_debug else 'OFF'}"
            )

        interval = 1.0 / float(self.hz)
        last = time.perf_counter()

        try:
            while True:
                now = time.perf_counter()
                dt = now - last
                last = now

                self.step(dt)
                self.send_all()

                # Keep a fixed-ish rate without busy waiting
                time.sleep(interval)

        except KeyboardInterrupt:
            print("\n[sender] Stopped.")
            if self.faults_enabled:
                print(
                    f"[sender] Stats: attempted={self.total_packets_attempted} "
                    f"sent={self.total_packets_sent} "
                    f"jam_suppressed={self.total_packets_jammed_fault} "
                    f"drop_suppressed={self.total_packets_dropped_fault}"
                )
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

    # Fault injection controls
    parser.add_argument(
        "--faults",
        action="store_true",
        default=True,
        help="Enable random fault injection (default: enabled)",
    )
    parser.add_argument(
        "--no-faults",
        dest="faults",
        action="store_false",
        help="Disable random fault injection",
    )
    parser.add_argument(
        "--fault-prob",
        type=float,
        default=0.10,
        help="Probability of triggering a random fault on each check (default: 0.10)",
    )
    parser.add_argument(
        "--fault-check",
        type=float,
        default=1.0,
        help="Seconds between random fault checks (default: 1.0)",
    )
    parser.add_argument(
        "--fault-debug",
        action="store_true",
        default=True,
        help="Print fault events when triggered (default: enabled)",
    )
    parser.add_argument(
        "--no-fault-debug",
        dest="fault_debug",
        action="store_false",
        help="Disable fault event prints",
    )

    args = parser.parse_args()

    UdpSimSender(
        dest_ip=args.ip,
        dest_port=args.port,
        hz=max(1, args.hz),
        entities=max(1, args.entities),
        seed=args.seed,
        faults_enabled=args.faults,
        fault_check_interval=args.fault_check,
        fault_trigger_prob=args.fault_prob,
        fault_debug=args.fault_debug,
    ).run()


if __name__ == "__main__":
    main()