"""Dungeon Quest: a compact top-down arcade game built with Pygame."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import math
from pathlib import Path
import random

import pygame


WIDTH = 960
HEIGHT = 640
TILE_SIZE = 40
COLS = WIDTH // TILE_SIZE
ROWS = HEIGHT // TILE_SIZE
FPS = 60

PLAYER_SIZE = 30
ENEMY_SIZE = 30
FIREBALL_SIZE = 12
START_CELL = (1, 1)
GOAL_CELL = (COLS - 2, ROWS - 2)

ASSET_DIR = Path(__file__).resolve().parent / "assets"


@dataclass
class Player:
    x: float
    y: float
    hp: float = 10.0
    speed: float = 220.0
    direction: str = "right"

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(round(self.x), round(self.y), PLAYER_SIZE, PLAYER_SIZE)


@dataclass
class Enemy:
    x: float
    y: float
    hp: int = 3
    speed: float = 65.0

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(round(self.x), round(self.y), ENEMY_SIZE, ENEMY_SIZE)


@dataclass
class Fireball:
    x: float
    y: float
    dx: float
    dy: float

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(round(self.x), round(self.y), FIREBALL_SIZE, FIREBALL_SIZE)


@dataclass
class MovingWall:
    x: float
    y: float
    axis: str
    speed: float

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(round(self.x), round(self.y), TILE_SIZE, TILE_SIZE)


def has_path(world: list[list[int]]) -> bool:
    """Return whether the generated map connects the start cell to the goal."""
    queue = deque([START_CELL])
    visited = {START_CELL}

    while queue:
        x, y = queue.popleft()
        if (x, y) == GOAL_CELL:
            return True

        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if (
                0 <= nx < COLS
                and 0 <= ny < ROWS
                and world[ny][nx] == 0
                and (nx, ny) not in visited
            ):
                visited.add((nx, ny))
                queue.append((nx, ny))

    return False


def generate_maze(level: int, rng: random.Random | None = None) -> list[list[int]]:
    """Create a random, increasingly dense map with a guaranteed valid route."""
    rng = rng or random.Random()
    wall_probability = min(0.28, 0.08 + (0.04 * level))

    for _ in range(200):
        world = []
        for y in range(ROWS):
            row = []
            for x in range(COLS):
                is_boundary = x in (0, COLS - 1) or y in (0, ROWS - 1)
                row.append(1 if is_boundary or rng.random() < wall_probability else 0)
            world.append(row)

        start_x, start_y = START_CELL
        goal_x, goal_y = GOAL_CELL
        world[start_y][start_x] = 0
        world[goal_y][goal_x] = 0

        if has_path(world):
            return world

    # Extremely unlikely fallback: return an open arena bounded by walls.
    return [
        [1 if x in (0, COLS - 1) or y in (0, ROWS - 1) else 0 for x in range(COLS)]
        for y in range(ROWS)
    ]


def cell_position(cell: tuple[int, int], size: int) -> tuple[float, float]:
    """Center an entity of ``size`` pixels inside a grid cell."""
    col, row = cell
    offset = (TILE_SIZE - size) / 2
    return col * TILE_SIZE + offset, row * TILE_SIZE + offset


def open_cells(world: list[list[int]]) -> list[tuple[int, int]]:
    """Return valid spawn cells away from the player and final goal."""
    return [
        (x, y)
        for y in range(1, ROWS - 1)
        for x in range(1, COLS - 1)
        if world[y][x] == 0
        and (x, y) not in (START_CELL, GOAL_CELL)
        and abs(x - START_CELL[0]) + abs(y - START_CELL[1]) >= 5
    ]


class Game:
    """Own the game state, rendering, input handling, and update loop."""

    def __init__(self, seed: int | None = None) -> None:
        pygame.init()
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption("Dungeon Quest")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("Arial", 22)
        self.title_font = pygame.font.SysFont("Arial", 44, bold=True)
        self.rng = random.Random(seed)

        self.images = {
            "player": self._load_image("player.png", (PLAYER_SIZE, PLAYER_SIZE)),
            "enemy": self._load_image("enemy.png", (ENEMY_SIZE, ENEMY_SIZE)),
            "wall": self._load_image("wall.png", (TILE_SIZE, TILE_SIZE)),
            "floor": self._load_image("floor.jpg", (TILE_SIZE, TILE_SIZE)),
            "goal": self._load_image("goal.png", (TILE_SIZE, TILE_SIZE)),
            "fireball": self._load_image("fireball.png", (FIREBALL_SIZE, FIREBALL_SIZE)),
        }

        self.running = True
        self.new_game()

    @staticmethod
    def _load_image(filename: str, size: tuple[int, int]) -> pygame.Surface:
        try:
            image = pygame.image.load(ASSET_DIR / filename).convert_alpha()
            return pygame.transform.smoothscale(image, size)
        except (FileNotFoundError, pygame.error):
            fallback = pygame.Surface(size)
            fallback.fill((255, 0, 255))
            return fallback

    def new_game(self) -> None:
        """Reset all progress and start from level one."""
        self.level = 1
        start_x, start_y = cell_position(START_CELL, PLAYER_SIZE)
        self.player = Player(start_x, start_y)
        self.state = "playing"
        self._setup_level()

    def _setup_level(self) -> None:
        self.world = generate_maze(self.level, self.rng)
        start_x, start_y = cell_position(START_CELL, PLAYER_SIZE)
        self.player.x, self.player.y = start_x, start_y
        self.goal_rect = pygame.Rect(
            GOAL_CELL[0] * TILE_SIZE,
            GOAL_CELL[1] * TILE_SIZE,
            TILE_SIZE,
            TILE_SIZE,
        )
        self.fireballs: list[Fireball] = []
        self.enemies = self._spawn_enemies(self.level)
        self.moving_walls = self._spawn_moving_walls() if self.level == 3 else []

    def _spawn_enemies(self, level: int) -> list[Enemy]:
        candidates = open_cells(self.world)
        count = min(level * 4, len(candidates))
        enemies = []
        for cell in self.rng.sample(candidates, count):
            x, y = cell_position(cell, ENEMY_SIZE)
            enemies.append(Enemy(x, y))
        return enemies

    def _spawn_moving_walls(self) -> list[MovingWall]:
        candidates = open_cells(self.world)
        count = min(8, len(candidates))
        walls = []
        for cell in self.rng.sample(candidates, count):
            x, y = cell_position(cell, TILE_SIZE)
            walls.append(
                MovingWall(
                    x=x,
                    y=y,
                    axis=self.rng.choice(("horizontal", "vertical")),
                    speed=self.rng.choice((-110.0, 110.0)),
                )
            )
        return walls

    def _rect_hits_wall(self, rect: pygame.Rect) -> bool:
        if not pygame.Rect(0, 0, WIDTH, HEIGHT).contains(rect):
            return True

        left = rect.left // TILE_SIZE
        right = (rect.right - 1) // TILE_SIZE
        top = rect.top // TILE_SIZE
        bottom = (rect.bottom - 1) // TILE_SIZE

        return any(
            self.world[row][col] == 1
            for row in range(top, bottom + 1)
            for col in range(left, right + 1)
        )

    def _move_player(self, dx: float, dy: float) -> None:
        next_rect = self.player.rect.move(round(dx), 0)
        if not self._rect_hits_wall(next_rect):
            self.player.x += dx

        next_rect = self.player.rect.move(0, round(dy))
        if not self._rect_hits_wall(next_rect):
            self.player.y += dy

    def _shoot(self) -> None:
        direction = {
            "right": (1, 0),
            "left": (-1, 0),
            "up": (0, -1),
            "down": (0, 1),
        }[self.player.direction]
        speed = 480.0
        player_rect = self.player.rect
        self.fireballs.append(
            Fireball(
                player_rect.centerx - FIREBALL_SIZE / 2,
                player_rect.centery - FIREBALL_SIZE / 2,
                direction[0] * speed,
                direction[1] * speed,
            )
        )

    def _handle_events(self) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.running = False
                elif event.key == pygame.K_r:
                    self.new_game()
                elif event.key == pygame.K_SPACE and self.state == "playing":
                    self._shoot()

    def _handle_movement(self, dt: float) -> None:
        keys = pygame.key.get_pressed()
        horizontal = int(keys[pygame.K_RIGHT]) - int(keys[pygame.K_LEFT])
        vertical = int(keys[pygame.K_DOWN]) - int(keys[pygame.K_UP])

        if horizontal == 0 and vertical == 0:
            return

        if horizontal:
            self.player.direction = "right" if horizontal > 0 else "left"
        if vertical:
            self.player.direction = "down" if vertical > 0 else "up"

        magnitude = math.hypot(horizontal, vertical)
        distance = self.player.speed * dt
        self._move_player(
            horizontal / magnitude * distance,
            vertical / magnitude * distance,
        )

    def _update_enemies(self, dt: float) -> None:
        for enemy in self.enemies:
            dx = self.player.x - enemy.x
            dy = self.player.y - enemy.y
            distance = math.hypot(dx, dy)
            if distance:
                step_x = enemy.speed * dt * dx / distance
                step_y = enemy.speed * dt * dy / distance

                next_rect = enemy.rect.move(round(step_x), 0)
                if not self._rect_hits_wall(next_rect):
                    enemy.x += step_x

                next_rect = enemy.rect.move(0, round(step_y))
                if not self._rect_hits_wall(next_rect):
                    enemy.y += step_y

            if enemy.rect.colliderect(self.player.rect):
                self.player.hp -= 3.0 * dt

    def _update_fireballs(self, dt: float) -> None:
        active_fireballs = []
        for fireball in self.fireballs:
            fireball.x += fireball.dx * dt
            fireball.y += fireball.dy * dt

            if self._rect_hits_wall(fireball.rect):
                continue

            hit_enemy = next(
                (enemy for enemy in self.enemies if fireball.rect.colliderect(enemy.rect)),
                None,
            )
            if hit_enemy is not None:
                hit_enemy.hp -= 1
                continue

            active_fireballs.append(fireball)

        self.fireballs = active_fireballs
        self.enemies = [enemy for enemy in self.enemies if enemy.hp > 0]

    def _update_moving_walls(self, dt: float) -> None:
        for wall in self.moving_walls:
            if wall.axis == "horizontal":
                wall.x += wall.speed * dt
                if wall.x < TILE_SIZE or wall.x > WIDTH - (2 * TILE_SIZE):
                    wall.x = max(TILE_SIZE, min(wall.x, WIDTH - (2 * TILE_SIZE)))
                    wall.speed *= -1
            else:
                wall.y += wall.speed * dt
                if wall.y < TILE_SIZE or wall.y > HEIGHT - (2 * TILE_SIZE):
                    wall.y = max(TILE_SIZE, min(wall.y, HEIGHT - (2 * TILE_SIZE)))
                    wall.speed *= -1

            if wall.rect.colliderect(self.player.rect):
                self.player.hp -= 5.0 * dt

    def update(self, dt: float) -> None:
        self._handle_movement(dt)
        self._update_enemies(dt)
        self._update_fireballs(dt)
        self._update_moving_walls(dt)

        if self.player.hp <= 0:
            self.player.hp = 0
            self.state = "game_over"
            return

        if self.player.rect.colliderect(self.goal_rect):
            self.level += 1
            if self.level > 3:
                self.state = "won"
            else:
                self._setup_level()

    def _draw_map(self) -> None:
        for row, tiles in enumerate(self.world):
            for col, tile in enumerate(tiles):
                image = self.images["wall"] if tile else self.images["floor"]
                self.screen.blit(image, (col * TILE_SIZE, row * TILE_SIZE))

    def _draw_overlay(self, title: str, color: tuple[int, int, int]) -> None:
        shade = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 190))
        self.screen.blit(shade, (0, 0))

        title_surface = self.title_font.render(title, True, color)
        instruction = self.font.render("Press R to restart or Esc to quit", True, (255, 255, 255))
        self.screen.blit(title_surface, title_surface.get_rect(center=(WIDTH / 2, HEIGHT / 2 - 30)))
        self.screen.blit(instruction, instruction.get_rect(center=(WIDTH / 2, HEIGHT / 2 + 30)))

    def draw(self) -> None:
        self._draw_map()
        self.screen.blit(self.images["goal"], self.goal_rect)

        for wall in self.moving_walls:
            self.screen.blit(self.images["wall"], wall.rect)
        for enemy in self.enemies:
            self.screen.blit(self.images["enemy"], enemy.rect)
        for fireball in self.fireballs:
            self.screen.blit(self.images["fireball"], fireball.rect)

        self.screen.blit(self.images["player"], self.player.rect)
        hud_background = pygame.Surface((225, 45), pygame.SRCALPHA)
        hud_background.fill((0, 0, 0, 175))
        self.screen.blit(hud_background, (10, 8))
        ui = self.font.render(
            f"LEVEL {self.level}/3     HP {math.ceil(self.player.hp)}",
            True,
            (255, 255, 255),
        )
        self.screen.blit(ui, (20, 18))

        if self.state == "game_over":
            self._draw_overlay("GAME OVER", (255, 80, 80))
        elif self.state == "won":
            self._draw_overlay("YOU WIN!", (90, 255, 130))

    def run(self) -> None:
        while self.running:
            dt = min(self.clock.tick(FPS) / 1000.0, 0.05)
            self._handle_events()
            if self.state == "playing":
                self.update(dt)
            self.draw()
            pygame.display.flip()

        pygame.quit()


def main() -> int:
    Game().run()
    return 0
