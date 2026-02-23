import socket
import json
import pygame
import math
import time
from collections import deque


def wrap360(deg: float) -> float:
    return deg % 360.0


class UdpReceiver:
    def __init__(self, listen_ip="0.0.0.0", listen_port=30001):
        self.addr = (listen_ip, listen_port)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(self.addr)
        self.sock.setblocking(False)  # non-blocking for pygame loop

    def poll_messages(self, max_per_frame=200):
        """
        Non-blocking receive; returns list of decoded JSON dicts.
        """
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
                # ignore malformed packets for demo
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

    def update_from_msg(self, msg: dict):
        self.entity_id = msg.get("entity_id", self.entity_id)
        self.entity_type = msg.get("entity_type", self.entity_type)

        self.x = float(msg.get("x", self.x))
        self.y = float(msg.get("y", self.y))
        self.heading = wrap360(float(msg.get("heading_deg", self.heading)))
        self.speed = float(msg.get("speed", self.speed))
        self.status = str(msg.get("status", self.status))
        self.seq = int(msg.get("seq", self.seq))

        self.last_rx_time = time.time()
        self.history.append((int(self.x), int(self.y)))


def main():
    pygame.init()
    W, H = 800, 600
    screen = pygame.display.set_mode((W, H))
    pygame.display.set_caption("PORTS Tactical Receiver (UDP + Pygame)")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("Courier", 18)
    small = pygame.font.SysFont("Courier", 14)

    # UDP receiver
    listen_port = 30001
    rx = UdpReceiver(listen_port=listen_port)

    # Tracks by entity_id
    tracks = {}  # entity_id -> TrackState

    # Visual toggles
    show_history = True
    show_heading = True
    show_labels = True

    # Stale detection
    stale_seconds = 2.0

    def is_stale(track: TrackState, now: float) -> bool:
        if track.last_rx_time <= 0:
            return True
        return (now - track.last_rx_time) > stale_seconds

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

        # --- receive UDP ---
        msgs = rx.poll_messages()
        for msg in msgs:
            if msg.get("msg_type") != "EntityState":
                continue

            eid = msg.get("entity_id", None)
            if eid is None:
                continue

            if eid not in tracks:
                tracks[eid] = TrackState(history_len=25)

            tracks[eid].update_from_msg(msg)

        now = time.time()

        # --- render ---
        screen.fill((5, 10, 30))

        # Radar rings
        center = (W // 2, H // 2)
        for r in range(100, 600, 100):
            pygame.draw.circle(screen, (30, 40, 70), center, r, 1)

        # Draw tracks (sorted for stable rendering order)
        for eid in sorted(tracks.keys()):
            tr = tracks[eid]
            stale = is_stale(tr, now)

            # Color choices
            if stale:
                dot_color = (255, 60, 60)     # red stale
                vec_color = (255, 210, 0)     # amber vector
                trail_base = (255, 80, 80)    # reddish trail
            else:
                dot_color = (0, 255, 0)       # green ok
                vec_color = (255, 255, 0)     # yellow vector
                trail_base = (0, 255, 0)      # green trail

            # Trail
            if show_history and len(tr.history) > 1:
                hist = list(tr.history)
                # Make older points dimmer; cap brightness
                for i, pos in enumerate(hist):
                    alpha = int((i / max(1, len(hist) - 1)) * 140)  # cap 140
                    # Pygame doesn't support per-draw alpha on RGB tuples directly;
                    # approximate by scaling color intensity.
                    scale = alpha / 140.0 if 140.0 > 0 else 1.0
                    c = (int(trail_base[0] * scale), int(trail_base[1] * scale), int(trail_base[2] * scale))
                    pygame.draw.circle(screen, c, pos, 2)

            # Current dot
            pygame.draw.circle(screen, dot_color, (int(tr.x), int(tr.y)), 6)

            # Heading vector
            if show_heading:
                rad = math.radians(tr.heading)
                vx = math.sin(rad) * 16
                vy = -math.cos(rad) * 16
                pygame.draw.line(
                    screen,
                    vec_color,
                    (int(tr.x), int(tr.y)),
                    (int(tr.x + vx), int(tr.y + vy)),
                    2,
                )

            # Label
            if show_labels:
                label = f"{tr.entity_id}"
                if stale:
                    label += " (stale)"
                screen.blit(small.render(label, True, (220, 220, 220)), (int(tr.x) + 8, int(tr.y) - 10))

        # HUD / Overlay
        hud1 = f"PORT: {listen_port}   ENTITIES: {len(tracks)}"
        hud2 = "[H] Trail  [V] Vector  [L] Labels"
        screen.blit(font.render(hud1, True, (200, 200, 200)), (20, 20))
        screen.blit(font.render(hud2, True, (100, 100, 100)), (20, 45))

        pygame.display.flip()
        clock.tick(60)


if __name__ == "__main__":
    main()