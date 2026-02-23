import socket
import json
import pygame
import math
import time
from collections import deque
from dataclasses import dataclass


def wrap360(deg: float) -> float:
    return deg % 360.0


class UdpReceiver:
    def __init__(self, listen_ip="0.0.0.0", listen_port=30001):
        self.addr = (listen_ip, listen_port)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(self.addr)
        self.sock.setblocking(False)

    def poll_messages(self, max_per_frame=200):
        msgs = []
        for _ in range(max_per_frame):
            try:
                data, _ = self.sock.recvfrom(8192)
            except BlockingIOError:
                break
            try:
                msg = json.loads(data.decode("utf-8", errors="replace"))
                msgs.append(msg)
            except Exception:
                pass
        return msgs


class TrackState:
    def __init__(self, history_len=25):
        self.entity_id = None
        self.entity_type = ""
        self.x = 0.0
        self.y = 0.0
        self.heading = 0.0
        self.speed = 0.0
        self.status = "NO_DATA"
        self.seq = 0
        self.last_rx_time = 0.0
        self.history = deque(maxlen=history_len)

    def update_from_msg(self, msg: dict, rx_time: float):
        self.entity_id = msg.get("entity_id", self.entity_id)
        self.entity_type = msg.get("entity_type", self.entity_type)

        self.x = float(msg.get("x", self.x))
        self.y = float(msg.get("y", self.y))
        self.heading = wrap360(float(msg.get("heading_deg", self.heading)))
        self.speed = float(msg.get("speed", self.speed))
        self.status = str(msg.get("status", self.status))
        self.seq = int(msg.get("seq", self.seq))

        self.last_rx_time = rx_time
        self.history.append((int(self.x), int(self.y)))


@dataclass
class ReplayItem:
    t: float
    msg: dict


class Recorder:
    def __init__(self):
        self.enabled = False
        self.file = None

    def start(self, path: str):
        self.file = open(path, "w", encoding="utf-8")
        self.enabled = True

    def stop(self):
        self.enabled = False
        if self.file:
            self.file.close()
        self.file = None

    def write(self, msg: dict):
        """
        JSON Lines format. Adds _rx_time so replay can preserve timing.
        Writes a line per message and flushes immediately (fine for demo rates).
        """
        if not self.enabled or not self.file:
            return
        out = dict(msg)
        out["_rx_time"] = time.time()
        self.file.write(json.dumps(out) + "\n")
        self.file.flush()


class Replayer:
    def __init__(self):
        self.enabled = False
        self.items = []
        self.index = 0
        self.replay_start_wall = None

    def load(self, path: str):
        self.items.clear()
        self.index = 0
        self.enabled = False
        self.replay_start_wall = None

        with open(path, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]

        parsed = []
        for line in lines:
            try:
                msg = json.loads(line)
                rx_t = float(msg.get("_rx_time", 0.0))
                msg.pop("_rx_time", None)
                parsed.append((rx_t, msg))
            except Exception:
                continue

        if not parsed:
            return False

        t0 = parsed[0][0]
        for rx_t, msg in parsed:
            self.items.append(ReplayItem(t=rx_t - t0, msg=msg))

        return True

    def start(self):
        if not self.items:
            return
        self.enabled = True
        self.index = 0
        self.replay_start_wall = time.time()

    def stop(self):
        self.enabled = False

    def poll(self, max_per_frame=200):
        if not self.enabled or not self.items:
            return []

        now = time.time()
        elapsed = now - self.replay_start_wall
        out = []

        while self.index < len(self.items) and len(out) < max_per_frame:
            item = self.items[self.index]
            if item.t <= elapsed:
                out.append(item.msg)
                self.index += 1
            else:
                break

        if self.index >= len(self.items):
            self.stop()

        return out


def main():
    pygame.init()
    W, H = 800, 600
    screen = pygame.display.set_mode((W, H))
    pygame.display.set_caption("PORTS Tactical Receiver (UDP + Pygame)")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("Courier", 18)
    small = pygame.font.SysFont("Courier", 14)

    listen_port = 30001
    rx = UdpReceiver(listen_port=listen_port)

    tracks = {}  # entity_id -> TrackState

    # Visual toggles
    show_history = True
    show_heading = True
    show_labels = True

    # Record / replay
    recorder = Recorder()
    replayer = Replayer()
    capture_path = "capture.jsonl"
    mode = "LIVE"  # LIVE or REPLAY

    # Stale detection
    stale_seconds = 2.0

    # HUD safety region (top strip)
    HUD_HEIGHT = 95

    def is_stale(track: TrackState, now: float) -> bool:
        if track.last_rx_time <= 0:
            return True
        return (now - track.last_rx_time) > stale_seconds

    def process_message(msg: dict, rx_time: float):
        if msg.get("msg_type") != "EntityState":
            return
        eid = msg.get("entity_id", None)
        if eid is None:
            return
        if eid not in tracks:
            tracks[eid] = TrackState(history_len=25)
        tracks[eid].update_from_msg(msg, rx_time)

    while True:
        # --- inputs ---
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_h:
                    show_history = not show_history
                elif event.key == pygame.K_v:
                    show_heading = not show_heading
                elif event.key == pygame.K_l:
                    show_labels = not show_labels

                # Record toggle
                elif event.key == pygame.K_r:
                    if recorder.enabled:
                        recorder.stop()
                    else:
                        recorder.start(capture_path)

                # Replay toggle
                elif event.key == pygame.K_p:
                    if mode == "REPLAY":
                        replayer.stop()
                        mode = "LIVE"
                    else:
                        ok = replayer.load(capture_path)
                        if ok:
                            tracks.clear()
                            replayer.start()
                            mode = "REPLAY"

        now = time.time()

        # --- ingest messages ---
        if mode == "LIVE":
            msgs = rx.poll_messages()
            for msg in msgs:
                recorder.write(msg)
                process_message(msg, rx_time=now)
        else:
            msgs = replayer.poll()
            for msg in msgs:
                process_message(msg, rx_time=now)

        # --- render ---
        screen.fill((5, 10, 30))

        # Radar rings
        center = (W // 2, H // 2)
        for r in range(100, 600, 100):
            pygame.draw.circle(screen, (30, 40, 70), center, r, 1)

        # Draw tracks
        for eid in sorted(tracks.keys()):
            tr = tracks[eid]
            stale = is_stale(tr, now)

            if stale:
                dot_color = (255, 60, 60)
                vec_color = (255, 210, 0)
                trail_base = (255, 80, 80)
            else:
                dot_color = (0, 255, 0)
                vec_color = (255, 255, 0)
                trail_base = (0, 255, 0)

            # Trail
            if show_history and len(tr.history) > 1:
                hist = list(tr.history)
                for i, pos in enumerate(hist):
                    alpha = int((i / max(1, len(hist) - 1)) * 140)
                    scale = alpha / 140.0 if 140.0 > 0 else 1.0
                    c = (
                        int(trail_base[0] * scale),
                        int(trail_base[1] * scale),
                        int(trail_base[2] * scale),
                    )
                    pygame.draw.circle(screen, c, pos, 2)

            # Render position (do not let symbols draw in HUD strip)
            rx_x = int(tr.x)
            rx_y = int(tr.y)
            if rx_y < HUD_HEIGHT:
                rx_y = HUD_HEIGHT

            # Dot
            pygame.draw.circle(screen, dot_color, (rx_x, rx_y), 6)

            # Vector
            if show_heading:
                rad = math.radians(tr.heading)
                vx = math.sin(rad) * 16
                vy = -math.cos(rad) * 16
                pygame.draw.line(
                    screen,
                    vec_color,
                    (rx_x, rx_y),
                    (int(rx_x + vx), int(rx_y + vy)),
                    2,
                )

            # Label (also clamp away from HUD strip)
            if show_labels:
                label = f"{tr.entity_id}"
                if stale:
                    label += " (stale)"

                lx = rx_x + 8
                ly = rx_y - 10
                if ly < HUD_HEIGHT:
                    ly = HUD_HEIGHT

                # Keep label on screen horizontally a bit
                lx = max(10, min(lx, W - 120))
                ly = max(HUD_HEIGHT, min(ly, H - 20))

                screen.blit(small.render(label, True, (220, 220, 220)), (lx, ly))

        # HUD background strip (guarantees readability even during replay of old captures)
        pygame.draw.rect(screen, (5, 10, 30), (0, 0, W, HUD_HEIGHT))

        # HUD
        hud1 = f"MODE: {mode}   PORT: {listen_port}   ENTITIES: {len(tracks)}"
        rec = "ON" if recorder.enabled else "OFF"
        hud2 = f"[H] Trail  [V] Vector  [L] Labels   [R] Record({rec})  [P] Replay"
        screen.blit(font.render(hud1, True, (200, 200, 200)), (20, 20))
        screen.blit(font.render(hud2, True, (100, 100, 100)), (20, 45))

        if mode == "REPLAY" and not replayer.enabled:
            screen.blit(font.render("REPLAY DONE (press P to return to LIVE)", True, (180, 180, 180)), (20, 70))

        pygame.display.flip()
        clock.tick(60)


if __name__ == "__main__":
    main()