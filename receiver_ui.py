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

    def poll_messages(self, max_per_frame=50):
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
    def __init__(self):
        self.entity_id = None
        self.entity_type = ""
        self.x = 400.0
        self.y = 300.0
        self.heading = 0.0
        self.speed = 0.0
        self.status = "NO_DATA"
        self.seq = 0
        self.last_rx_time = 0.0
        self.history = deque(maxlen=30)  # short, subtle tail

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

    # UDP receiver
    listen_port = 30001
    rx = UdpReceiver(listen_port=listen_port)
    track = TrackState()

    # Visual toggles
    show_history = True
    show_heading = True

    # "Stale" detection
    stale_seconds = 2.0

    while True:
        # --- inputs ---
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_h:
                    show_history = not show_history
                if event.key == pygame.K_v:
                    show_heading = not show_heading

        # --- receive UDP ---
        msgs = rx.poll_messages()
        for msg in msgs:
            if msg.get("msg_type") == "EntityState":
                track.update_from_msg(msg)

        # --- determine link state ---
        now = time.time()
        age = now - track.last_rx_time if track.last_rx_time > 0 else 9999
        link_ok = age <= stale_seconds

        # --- render ---
        screen.fill((5, 10, 30))

        # Radar rings
        center = (W // 2, H // 2)
        for r in range(100, 600, 100):
            pygame.draw.circle(screen, (30, 40, 70), center, r, 1)

        # Draw history tail
        if show_history and len(track.history) > 1 and link_ok:
            hist_list = list(track.history)
            for i, pos in enumerate(hist_list):
                # dim older points; cap brightness
                alpha = int((i / max(1, len(hist_list) - 1)) * 160)
                pygame.draw.circle(screen, (0, alpha, 0), pos, 2)

        # Draw current contact + heading
        if link_ok and track.entity_id is not None:
            pygame.draw.circle(screen, (0, 255, 0), (int(track.x), int(track.y)), 6)

            if show_heading:
                rad = math.radians(track.heading)
                vx = math.sin(rad) * 16
                vy = -math.cos(rad) * 16
                pygame.draw.line(
                    screen,
                    (255, 255, 0),
                    (int(track.x), int(track.y)),
                    (int(track.x + vx), int(track.y + vy)),
                    2,
                )
        else:
            # show last known position in red if stale
            if track.entity_id is not None:
                pygame.draw.circle(screen, (255, 60, 60), (int(track.x), int(track.y)), 6)

        # UI overlay
        status_text = "LINK: OK" if link_ok else f"LINK: STALE ({age:0.1f}s)"
        status_color = (0, 255, 0) if link_ok else (255, 60, 60)
        screen.blit(font.render(status_text, True, status_color), (20, 20))

        info = f"PORT: {listen_port}  ID: {track.entity_id}  SEQ: {track.seq}"
        screen.blit(font.render(info, True, (200, 200, 200)), (20, 45))

        crs = f"CRS: {int(track.heading)}°  SPD: {track.speed:0.1f}"
        screen.blit(font.render(crs, True, (200, 200, 200)), (20, 70))

        help_text = "[H] Toggle Trail  [V] Toggle Vector"
        screen.blit(font.render(help_text, True, (100, 100, 100)), (20, 570))

        pygame.display.flip()
        clock.tick(60)


if __name__ == "__main__":
    main()