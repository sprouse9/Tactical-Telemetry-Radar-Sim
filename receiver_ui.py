import pygame
import math
from collections import deque

# =========================
# Helpers
# =========================
def wrap360(deg: float) -> float:
    """Normalize an angle to [0, 360)."""
    return deg % 360.0


# =========================
# The Engine (Math & State)
# =========================
class SimEngine:
    def __init__(self, w=800, h=600, margin=50):
        self.w, self.h = w, h
        self.margin = margin

        # Start near center
        self.x, self.y = w / 2.0, h / 2.0

        # Convention: 0° = up (north), 90° = right (east)
        self.heading = 0.0  # always stored as [0,360)
        self.speed = 1.5

        self.history = deque(maxlen=50)
        self.sensor_failure = False

    def turn(self, delta_deg: float):
        self.heading = wrap360(self.heading + delta_deg)

    def update(self):
        # 1) Store history for breadcrumbs (for visual track)
        self.history.append((int(self.x), int(self.y)))

        # 2) Kinematics
        # 0° = up. Screen y grows downward, hence the minus on y term.
        rad = math.radians(self.heading)
        self.x += math.sin(rad) * self.speed
        self.y -= math.cos(rad) * self.speed

        # 3) Reflection logic against a "margin box"
        left = self.margin
        right = self.w - self.margin
        top = self.margin
        bottom = self.h - self.margin

        # Bounce on top/bottom (invert Y velocity)
        if self.y <= top or self.y >= bottom:
            # Mirror heading across the horizontal axis:
            # heading' = 180 - heading  (then normalize)
            self.heading = wrap360(180.0 - self.heading)

            # Nudge inside to avoid sticky wall
            self.y = top + 1 if self.y <= top else bottom - 1

        # Bounce on left/right (invert X velocity)
        if self.x <= left or self.x >= right:
            # Mirror heading across the vertical axis:
            # heading' = 360 - heading (then normalize)
            self.heading = wrap360(360.0 - self.heading)

            # Nudge inside to avoid sticky wall
            self.x = left + 1 if self.x <= left else right - 1


# =========================
# The App
# =========================
def main():
    pygame.init()
    W, H = 800, 600
    screen = pygame.display.set_mode((W, H))
    pygame.display.set_caption("PORTS Simulator Prototype")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("Courier", 18)

    engine = SimEngine(W, H, margin=50)

    # You asked: keep arrow keys, or leave direction control to the background app?
    #
    # Best for a demo: KEEP them as "Instructor Overrides".
    # Later, when you add UDP, you can disable these and let the sender drive heading.
    instructor_controls_enabled = True

    while True:
        # --- Inputs ---
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_f:
                    engine.sensor_failure = not engine.sensor_failure

                if instructor_controls_enabled:
                    if event.key == pygame.K_LEFT:
                        engine.turn(-15.0)
                    if event.key == pygame.K_RIGHT:
                        engine.turn(+15.0)

        # --- Update ---
        engine.update()

        # --- Render ---
        screen.fill((5, 10, 30))  # Tactical dark blue

        # Radar rings
        center = (W // 2, H // 2)
        for r in range(100, 600, 100):
            pygame.draw.circle(screen, (30, 40, 70), center, r, 1)

        # Optional: Draw the "margin box" boundary (debug/feel)
        margin = engine.margin
        pygame.draw.rect(screen, (25, 35, 60), (margin, margin, W - 2 * margin, H - 2 * margin), 1)

        if not engine.sensor_failure:
            # Breadcrumbs (history)
            if len(engine.history) > 1:
                for i, pos in enumerate(engine.history):
                    alpha = int((i / max(1, len(engine.history) - 1)) * 255)
                    pygame.draw.circle(screen, (0, alpha, 0), pos, 2)

            # Current contact
            pygame.draw.circle(screen, (0, 255, 0), (int(engine.x), int(engine.y)), 6)

            # Heading vector
            rad = math.radians(engine.heading)
            vx = math.sin(rad) * 20
            vy = -math.cos(rad) * 20
            pygame.draw.line(
                screen,
                (255, 255, 0),
                (int(engine.x), int(engine.y)),
                (int(engine.x + vx), int(engine.y + vy)),
                2,
            )

        # UI overlays
        status = "SYSTEM: OK" if not engine.sensor_failure else "SYSTEM: SENSOR FAULT"
        color = (0, 255, 0) if not engine.sensor_failure else (255, 50, 50)

        screen.blit(font.render(status, True, color), (20, 20))
        screen.blit(font.render(f"CRS: {int(engine.heading)}°", True, (200, 200, 200)), (20, 45))

        if instructor_controls_enabled:
            help_text = "[F] Toggle Fault | [Arrows] Instructor Heading Override"
        else:
            help_text = "[F] Toggle Fault | Heading controlled externally (e.g., UDP sender)"
        screen.blit(font.render(help_text, True, (100, 100, 100)), (20, 570))

        pygame.display.flip()
        clock.tick(60)


if __name__ == "__main__":
    main()