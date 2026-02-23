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

    # Window and layout
    W, H = 1075, 600
    RADAR_W = 760
    PANEL_W = W - RADAR_W
    HUD_HEIGHT = 100  # top strip for radar HUD

    screen = pygame.display.set_mode((W, H))
    pygame.display.set_caption("PORTS Tactical Receiver (UDP + Pygame)")
    clock = pygame.time.Clock()

    font = pygame.font.SysFont("Courier", 18)
    small = pygame.font.SysFont("Courier", 14)
    tiny = pygame.font.SysFont("Courier", 13)

    # Radar coordinate/world area matches sender's world dimensions
    WORLD_W, WORLD_H = 800, 600

    def world_to_radar(x, y):
        """
        Map sender world coords (0..800, 0..600) into left radar pane.
        """
        rx = int((x / WORLD_W) * (RADAR_W - 1))
        ry = int((y / WORLD_H) * (H - 1))
        return rx, ry

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
    mode = "LIVE"

    # Stale detection
    stale_seconds = 2.0

    # Packet stats
    msg_count_total = 0
    msg_count_window = 0
    msg_rate = 0.0
    msg_rate_timer = time.time()

    max_seq_seen = None
    seq_drop_est = 0

    def is_stale(track: TrackState, now_ts: float) -> bool:
        if track.last_rx_time <= 0:
            return True
        return (now_ts - track.last_rx_time) > stale_seconds

    def process_message(msg: dict, rx_time: float):
        nonlocal msg_count_total, msg_count_window, max_seq_seen, seq_drop_est

        if msg.get("msg_type") != "EntityState":
            return

        msg_count_total += 1
        msg_count_window += 1

        try:
            seq = int(msg.get("seq"))
            if max_seq_seen is None:
                max_seq_seen = seq
            elif seq > max_seq_seen:
                gap = seq - max_seq_seen
                if gap > 1:
                    seq_drop_est += (gap - 1)
                max_seq_seen = seq
        except Exception:
            pass

        eid = msg.get("entity_id", None)
        if eid is None:
            return

        if eid not in tracks:
            tracks[eid] = TrackState(history_len=25)

        tracks[eid].update_from_msg(msg, rx_time)

    while True:
        # --- input ---
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
                elif event.key == pygame.K_r:
                    if recorder.enabled:
                        recorder.stop()
                    else:
                        recorder.start(capture_path)
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

        # --- ingest ---
        if mode == "LIVE":
            msgs = rx.poll_messages()
            for msg in msgs:
                recorder.write(msg)
                process_message(msg, rx_time=now)
        else:
            msgs = replayer.poll()
            for msg in msgs:
                process_message(msg, rx_time=now)

        # Update msg/sec
        rate_now = time.time()
        dt_rate = rate_now - msg_rate_timer
        if dt_rate >= 1.0:
            msg_rate = msg_count_window / dt_rate
            msg_count_window = 0
            msg_rate_timer = rate_now

        stale_count = sum(1 for tr in tracks.values() if is_stale(tr, now))

        # --- render ---
        screen.fill((5, 10, 30))

        # Radar pane background
        pygame.draw.rect(screen, (5, 10, 30), (0, 0, RADAR_W, H))

        # Radar rings (fit inside usable radar area below the HUD)
        radar_left = 0
        radar_top = HUD_HEIGHT
        radar_right = RADAR_W
        radar_bottom = H

        radar_cx = (radar_left + radar_right) // 2
        radar_cy = (radar_top + radar_bottom) // 2
        center = (radar_cx, radar_cy)

        usable_w = radar_right - radar_left
        usable_h = radar_bottom - radar_top

        max_r = max_r = (usable_w // 2) - 12 # min(usable_w // 2, usable_h // 2) - 12
        ring_step = 60  # try 70 or 80

        for r in range(ring_step, max_r + 1, ring_step):
            pygame.draw.circle(screen, (30, 40, 70), center, r, 1)

        # Crosshair (only across usable radar region)
        pygame.draw.line(screen, (25, 35, 60), (radar_cx, radar_top), (radar_cx, radar_bottom), 1)
        pygame.draw.line(screen, (25, 35, 60), (radar_left, radar_cy), (radar_right, radar_cy), 1)

        # Draw tracks on radar pane
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

            # Trail (map world history to radar pane)
            if show_history and len(tr.history) > 1:
                hist = list(tr.history)
                for i, pos in enumerate(hist):
                    px, py = world_to_radar(pos[0], pos[1])
                    alpha = int((i / max(1, len(hist) - 1)) * 140)
                    scale = alpha / 140.0 if 140.0 > 0 else 1.0
                    c = (
                        int(trail_base[0] * scale),
                        int(trail_base[1] * scale),
                        int(trail_base[2] * scale),
                    )
                    if py >= HUD_HEIGHT:
                        pygame.draw.circle(screen, c, (px, py), 2)

            # Map current world pos to radar pane
            rx_x, rx_y = world_to_radar(tr.x, tr.y)

            # Keep symbols out of radar HUD strip
            if rx_y < HUD_HEIGHT:
                rx_y = HUD_HEIGHT

            # Dot
            pygame.draw.circle(screen, dot_color, (rx_x, rx_y), 6)

            # Heading vector
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

            # Label
            if show_labels:
                label = f"{tr.entity_id}"
                if stale:
                    label += " (stale)"
                lx = rx_x + 8
                ly = rx_y - 10
                if ly < HUD_HEIGHT:
                    ly = HUD_HEIGHT
                lx = max(10, min(lx, RADAR_W - 140))
                ly = max(HUD_HEIGHT, min(ly, H - 20))
                screen.blit(small.render(label, True, (220, 220, 220)), (lx, ly))

        # Radar HUD strip (draw after tracks so it always stays readable)
        pygame.draw.rect(screen, (5, 10, 30), (0, 0, RADAR_W, HUD_HEIGHT))

        # Radar HUD text
        hud1 = f"MODE: {mode}   PORT: {listen_port}   ENTITIES: {len(tracks)}   STALE: {stale_count}"
        rec = "ON" if recorder.enabled else "OFF"
        seq_text = "-" if max_seq_seen is None else str(max_seq_seen)
        hud2 = f"MSG/S: {msg_rate:5.1f}   TOTAL: {msg_count_total}   SEQ: {seq_text}   DROP: {seq_drop_est}"
        hud3 = f"[H] Trail  [V] Vector  [L] Labels   [R] Record({rec})  [P] Replay"

        screen.blit(font.render(hud1, True, (200, 200, 200)), (20, 20))
        screen.blit(font.render(hud2, True, (170, 170, 170)), (20, 45))
        screen.blit(font.render(hud3, True, (100, 100, 100)), (20, 70))

        if mode == "REPLAY" and not replayer.enabled:
            screen.blit(
                font.render("REPLAY DONE (press P to return to LIVE)", True, (180, 180, 180)),
                (20, 95),
            )

        # --- Right-side entity panel ---
        panel_x = RADAR_W
        pygame.draw.rect(screen, (18, 22, 38), (panel_x, 0, PANEL_W, H))
        pygame.draw.line(screen, (60, 70, 100), (panel_x, 0), (panel_x, H), 2)

        # Panel title
        screen.blit(font.render("ENTITY LIST", True, (220, 220, 220)), (panel_x + 12, 12))

        # Column headers (monospace, aligned to row formatting)
        y0 = 42
        header_text = f"{'ID':<6}{'TYPE':<7}{'X,Y':<9}{'HDG':<5}{'SPD':<4}"
        screen.blit(tiny.render(header_text, True, (180, 180, 180)), (panel_x + 22, y0))

        # Rows
        row_y = y0 + 22
        row_h = 22

        sorted_ids = sorted(tracks.keys())
        max_rows = (H - row_y - 70) // row_h  # leave room for footer/help
        visible_ids = sorted_ids[:max_rows]

        for i, eid in enumerate(visible_ids):
            tr = tracks[eid]
            stale = is_stale(tr, now)

            # alternating row background
            if i % 2 == 0:
                pygame.draw.rect(screen, (22, 27, 45), (panel_x + 6, row_y - 2, PANEL_W - 12, row_h))

            txt_color = (255, 120, 120) if stale else (200, 230, 200)

            # tiny status dot
            dot_c = (255, 80, 80) if stale else (0, 220, 120)
            pygame.draw.circle(screen, dot_c, (panel_x + 14, row_y + 8), 4)

            # text columns
            row_text = (
                f"{tr.entity_id:<6}"          # e.g. '1001  '
                f"{str(tr.entity_type)[:6]:<7}"  # e.g. 'SUB    '
                f"{int(tr.x):>3},{int(tr.y):<3}  "
                f"{int(tr.heading):03d}  "
                f"{tr.speed:>3.1f}"
            )

            screen.blit(tiny.render(row_text, True, txt_color), (panel_x + 22, row_y))

            row_y += row_h

        # Panel footer / details
        footer_y = H - 78
        pygame.draw.line(screen, (60, 70, 100), (panel_x + 8, footer_y - 8), (W - 8, footer_y - 8), 1)
        screen.blit(tiny.render(f"Tracks shown: {len(visible_ids)}/{len(sorted_ids)}", True, (180, 180, 180)), (panel_x + 10, footer_y))
        screen.blit(tiny.render("Red row = stale", True, (180, 180, 180)), (panel_x + 10, footer_y + 18))
        screen.blit(tiny.render("World: 800x600 mapped to radar pane", True, (140, 140, 160)), (panel_x + 10, footer_y + 36))

        pygame.display.flip()
        clock.tick(60)


if __name__ == "__main__":
    main()