import pygame
import math
from collections import deque

# --- THE ENGINE (Math & State) ---
class SimEngine:
    def __init__(self):
        self.x, self.y = 400, 300
        self.heading = 0.0
        self.speed = 1.5
        self.history = deque(maxlen=50) # Stores last 50 positions
        self.sensor_failure = False

    def update(self):
        # 1. Store history for breadcrumbs
        self.history.append((int(self.x), int(self.y)))
        
        # 2. Update Kinematics
        rad = math.radians(self.heading)
        self.x += math.sin(rad) * self.speed
        self.y -= math.cos(rad) * self.speed
        
        # Screen Wrap
        self.x %= 800
        self.y %= 600

# --- THE APP ---
def main():
    pygame.init()
    screen = pygame.display.set_mode((800, 600))
    pygame.display.set_caption("PORTS Simulator Prototype")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("Courier", 18)
    engine = SimEngine()

    while True:
        # Handle "Instructor" Inputs
        for event in pygame.event.get():
            if event.type == pygame.QUIT: return
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_f: engine.sensor_failure = not engine.sensor_failure
                if event.key == pygame.K_LEFT: engine.heading -= 15
                if event.key == pygame.K_RIGHT: engine.heading += 15

        engine.update()

        # RENDER
        screen.fill((5, 10, 30)) # Tactical Dark Blue
        
        # Draw Radar Grids
        for r in range(100, 600, 100):
            pygame.draw.circle(screen, (30, 40, 70), (400, 300), r, 1)

        if not engine.sensor_failure:
            # Draw Breadcrumbs (History)
            for i, pos in enumerate(engine.history):
                # Make older points dimmer
                alpha = int((i / len(engine.history)) * 255)
                pygame.draw.circle(screen, (0, alpha, 0), pos, 2)

            # Draw Current Contact
            pygame.draw.circle(screen, (0, 255, 0), (int(engine.x), int(engine.y)), 6)
        
        # UI Overlays
        status = "SYSTEM: OK" if not engine.sensor_failure else "SYSTEM: SENSOR FAULT"
        color = (0, 255, 0) if not engine.sensor_failure else (255, 50, 50)
        screen.blit(font.render(status, True, color), (20, 20))
        screen.blit(font.render(f"CRS: {int(engine.heading)}°", True, (200, 200, 200)), (20, 45))
        screen.blit(font.render("[F] Toggle Fault | [Arrows] Change Heading", True, (100, 100, 100)), (20, 570))

        pygame.display.flip()
        clock.tick(60)

if __name__ == "__main__":
    main()