from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path

import pygame


WIDTH = 480
HEIGHT = 760
FPS = 60
ROOT = Path(__file__).resolve().parents[2]

BLACK = (3, 4, 8)
INK = (10, 13, 20)
WHITE = (242, 242, 235)
MUTED = (165, 169, 180)
GOLD = (255, 204, 74)
AMBER = (248, 151, 54)
RED = (238, 75, 68)
CYAN = (101, 215, 230)

TOP_LINE_Y = 12
PLAY_TOP = 0
PLAY_BOTTOM = 636
LINE_HEIGHT = 3

BIRD_X = 118
BIRD_RADIUS = 22
GRAVITY = 0.47
FLAP_STRENGTH = -8.35
MAX_FALL_SPEED = 10.5

GATE_WIDTH = 82
GATE_GAP = 174
GATE_SPACING = 225
BASE_GATE_SPEED = 3.25

SAVE_PATH = Path.home() / ".flapper_bird_score.json"


class Scene(Enum):
    TITLE = auto()
    HOW_TO_PLAY = auto()
    PLAYING = auto()
    PAUSED = auto()
    GAME_OVER = auto()


@dataclass
class FontBook:
    title: pygame.font.Font
    big: pygame.font.Font
    medium: pygame.font.Font
    small: pygame.font.Font
    tiny: pygame.font.Font


@dataclass
class Assets:
    background: pygame.Surface
    base: pygame.Surface
    pipes: tuple[pygame.Surface, pygame.Surface]
    birds: list[pygame.Surface]
    digits: dict[str, pygame.Surface]
    message: pygame.Surface
    game_over: pygame.Surface
    sounds: dict[str, pygame.mixer.Sound]


@dataclass
class Bird:
    y: float = 420
    velocity: float = 0
    wing_phase: float = 0
    squash: float = 1

    @property
    def center(self) -> tuple[int, int]:
        return BIRD_X, round(self.y)

    @property
    def hitbox(self) -> pygame.Rect:
        return pygame.Rect(BIRD_X - 20, round(self.y) - 15, 40, 30)

    def flap(self) -> None:
        self.velocity = FLAP_STRENGTH
        self.squash = 1.18

    def update(self) -> None:
        self.velocity = min(MAX_FALL_SPEED, self.velocity + GRAVITY)
        self.y += self.velocity
        self.wing_phase += 0.42
        self.squash += (1 - self.squash) * 0.18

    def draw(self, surface: pygame.Surface, frames: list[pygame.Surface]) -> None:
        x, y = self.center
        lean = max(-28, min(42, self.velocity * 4.4))
        frame = frames[int(self.wing_phase / 5) % len(frames)]
        if self.squash != 1:
            frame = pygame.transform.smoothscale(
                frame,
                (round(frame.get_width() * self.squash), round(frame.get_height() / self.squash)),
            )
        rotated = pygame.transform.rotate(frame, -lean)
        surface.blit(rotated, rotated.get_rect(center=(x, y)))


@dataclass
class Gate:
    x: float
    gap_y: int
    scored: bool = False

    @property
    def top_rect(self) -> pygame.Rect:
        return pygame.Rect(
            round(self.x),
            PLAY_TOP + LINE_HEIGHT,
            GATE_WIDTH,
            self.gap_y - GATE_GAP // 2 - PLAY_TOP,
        )

    @property
    def bottom_rect(self) -> pygame.Rect:
        y = self.gap_y + GATE_GAP // 2
        return pygame.Rect(round(self.x), y, GATE_WIDTH, PLAY_BOTTOM - y)

    def update(self, speed: float) -> None:
        self.x -= speed

    def offscreen(self) -> bool:
        return self.x + GATE_WIDTH < -8

    def passed(self) -> bool:
        return self.x + GATE_WIDTH < BIRD_X

    def collides(self, bird: Bird) -> bool:
        hitbox = bird.hitbox
        return hitbox.colliderect(self.top_rect) or hitbox.colliderect(self.bottom_rect)

    def draw(self, surface: pygame.Surface, pipe_top: pygame.Surface, pipe_bottom: pygame.Surface) -> None:
        top_rect = pipe_top.get_rect(midbottom=(round(self.x + GATE_WIDTH / 2), self.gap_y - GATE_GAP // 2))
        bottom_rect = pipe_bottom.get_rect(midtop=(round(self.x + GATE_WIDTH / 2), self.gap_y + GATE_GAP // 2))
        surface.blit(pipe_top, top_rect)
        surface.blit(pipe_bottom, bottom_rect)


@dataclass
class Particle:
    pos: pygame.Vector2
    velocity: pygame.Vector2
    life: float
    color: tuple[int, int, int]
    radius: float

    def update(self) -> bool:
        self.pos += self.velocity
        self.velocity.y += 0.08
        self.life -= 1
        return self.life > 0

    def draw(self, surface: pygame.Surface) -> None:
        alpha = max(0, min(255, round(255 * self.life / 36)))
        dot = pygame.Surface((16, 16), pygame.SRCALPHA)
        pygame.draw.circle(dot, (*self.color, alpha), (8, 8), max(1, round(self.radius)))
        surface.blit(dot, dot.get_rect(center=self.pos))


@dataclass
class Game:
    screen: pygame.Surface
    clock: pygame.time.Clock
    fonts: FontBook
    assets: Assets
    scene: Scene = Scene.TITLE
    bird: Bird = field(default_factory=Bird)
    gates: list[Gate] = field(default_factory=list)
    particles: list[Particle] = field(default_factory=list)
    stars: list[tuple[float, float, float]] = field(default_factory=list)
    score: int = 0
    best_score: int = 0
    shake: float = 0
    frame: int = 0
    base_scroll: float = 0

    def __post_init__(self) -> None:
        self.best_score = load_best_score()
        self.reset()
        self.scene = Scene.TITLE

    def reset(self) -> None:
        self.bird = Bird()
        self.score = 0
        self.shake = 0
        self.particles.clear()
        self.gates = [Gate(WIDTH + 80 + index * GATE_SPACING, random_gap_y()) for index in range(4)]

    def start(self) -> None:
        if self.scene in (Scene.TITLE, Scene.GAME_OVER):
            self.reset()
        self.scene = Scene.PLAYING
        self.bird.flap()
        play_sound(self.assets, "swoosh")

    def crash(self) -> None:
        if self.scene == Scene.GAME_OVER:
            return
        self.scene = Scene.GAME_OVER
        play_sound(self.assets, "hit")
        play_sound(self.assets, "die")
        self.shake = 14
        self.best_score = max(self.best_score, self.score)
        save_best_score(self.best_score)
        for _ in range(28):
            angle = random.uniform(0, math.tau)
            speed = random.uniform(1.5, 6)
            self.particles.append(
                Particle(
                    pygame.Vector2(BIRD_X, self.bird.y),
                    pygame.Vector2(math.cos(angle) * speed, math.sin(angle) * speed),
                    random.uniform(18, 36),
                    random.choice([GOLD, AMBER, RED, WHITE]),
                    random.uniform(2, 4),
                )
            )

    def handle_event(self, event: pygame.event.Event) -> bool:
        if event.type == pygame.QUIT:
            return False

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                return False
            if event.key == pygame.K_h and self.scene == Scene.TITLE:
                self.scene = Scene.HOW_TO_PLAY
                play_sound(self.assets, "swoosh")
            elif event.key in (pygame.K_h, pygame.K_r, pygame.K_BACKSPACE) and self.scene == Scene.HOW_TO_PLAY:
                self.scene = Scene.TITLE
                play_sound(self.assets, "swoosh")
            elif event.key == pygame.K_p and self.scene == Scene.PLAYING:
                self.scene = Scene.PAUSED
            elif event.key == pygame.K_p and self.scene == Scene.PAUSED:
                self.scene = Scene.PLAYING
            elif event.key == pygame.K_r:
                self.reset()
                self.scene = Scene.TITLE
            elif event.key in (pygame.K_SPACE, pygame.K_UP):
                self.start() if self.scene in (Scene.TITLE, Scene.HOW_TO_PLAY, Scene.GAME_OVER) else self.flap()

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.start() if self.scene in (Scene.TITLE, Scene.HOW_TO_PLAY, Scene.GAME_OVER) else self.flap()

        return True

    def flap(self) -> None:
        if self.scene == Scene.PLAYING:
            self.bird.flap()
            play_sound(self.assets, "wing")
            self.particles.append(
                Particle(
                    pygame.Vector2(BIRD_X - 12, self.bird.y + 10),
                    pygame.Vector2(-2.5, 1.2),
                    18,
                    WHITE,
                    3,
                )
            )

    def update(self) -> None:
        self.frame += 1
        self.particles = [particle for particle in self.particles if particle.update()]
        self.shake *= 0.82
        self.base_scroll = (self.base_scroll - BASE_GATE_SPEED) % self.assets.base.get_width()

        if self.scene != Scene.PLAYING:
            self.bird.wing_phase += 0.15
            return

        speed = BASE_GATE_SPEED + min(1.45, self.score * 0.055)
        self.bird.update()

        for gate in self.gates:
            gate.update(speed)
            if not gate.scored and gate.passed():
                gate.scored = True
                self.score += 1
                play_sound(self.assets, "point")
                self.particles.extend(score_sparks())

        if self.gates[0].offscreen():
            self.gates.pop(0)
            last_x = self.gates[-1].x if self.gates else WIDTH
            self.gates.append(Gate(last_x + GATE_SPACING, random_gap_y()))

        out_of_bounds = self.bird.y - BIRD_RADIUS < PLAY_TOP or self.bird.y + BIRD_RADIUS > PLAY_BOTTOM
        if out_of_bounds or any(gate.collides(self.bird) for gate in self.gates):
            self.crash()

    def draw(self) -> None:
        canvas = pygame.Surface((WIDTH, HEIGHT))
        self.draw_background(canvas)
        if self.scene not in (Scene.TITLE, Scene.HOW_TO_PLAY):
            for gate in self.gates:
                gate.draw(canvas, self.assets.pipes[0], self.assets.pipes[1])
        self.draw_base(canvas)
        if self.scene not in (Scene.TITLE, Scene.HOW_TO_PLAY):
            self.bird.draw(canvas, self.assets.birds)
        for particle in self.particles:
            particle.draw(canvas)
        self.draw_hud(canvas)

        offset = pygame.Vector2(0, 0)
        if self.shake > 0.4:
            offset.x = random.uniform(-self.shake, self.shake)
            offset.y = random.uniform(-self.shake, self.shake)
        self.screen.blit(canvas, offset)

    def draw_background(self, surface: pygame.Surface) -> None:
        surface.blit(self.assets.background, (0, 0))

    def draw_base(self, surface: pygame.Surface) -> None:
        base = self.assets.base
        y = PLAY_BOTTOM
        x = -round(self.base_scroll)
        while x < WIDTH:
            surface.blit(base, (x, y))
            x += base.get_width()

    def draw_hud(self, surface: pygame.Surface) -> None:
        if self.scene not in (Scene.TITLE, Scene.HOW_TO_PLAY):
            draw_number(surface, self.assets.digits, self.score, 50, scale=1.15)
        best = self.fonts.small.render(f"BEST {self.best_score}", True, MUTED)
        surface.blit(best, (WIDTH - best.get_width() - 18, 38))

        if self.scene == Scene.TITLE:
            rect = self.assets.message.get_rect(center=(WIDTH // 2, 230))
            surface.blit(self.assets.message, rect)
            self.draw_title_help(surface)
        elif self.scene == Scene.HOW_TO_PLAY:
            self.draw_how_to_play(surface)
        elif self.scene == Scene.PAUSED:
            self.draw_panel(surface, "PAUSED", "P 繼續", "R 回到標題")
        elif self.scene == Scene.GAME_OVER:
            rect = self.assets.game_over.get_rect(center=(WIDTH // 2, 205))
            surface.blit(self.assets.game_over, rect)
            self.draw_panel(surface, "", "SPACE 再來一次", f"SCORE {self.score}   BEST {self.best_score}")

    def draw_panel(self, surface: pygame.Surface, title: str, action: str, subtitle: str) -> None:
        panel = pygame.Rect(42, 92, WIDTH - 84, 142)
        pygame.draw.rect(surface, (8, 10, 18), panel, border_radius=8)
        pygame.draw.rect(surface, WHITE, panel, width=2, border_radius=8)
        draw_center(surface, self.fonts.title, title, panel.y + 42, WHITE)
        draw_center(surface, self.fonts.medium, action, panel.y + 88, GOLD)
        draw_center(surface, self.fonts.small, subtitle, panel.y + 120, MUTED)

    def draw_title_help(self, surface: pygame.Surface) -> None:
        hint = self.fonts.small.render("H 玩法說明    Space 開始", True, INK)
        pill = hint.get_rect(center=(WIDTH // 2, 498)).inflate(28, 16)
        pygame.draw.rect(surface, (238, 244, 206), pill, border_radius=8)
        pygame.draw.rect(surface, (68, 78, 88), pill, width=2, border_radius=8)
        surface.blit(hint, hint.get_rect(center=pill.center))

    def draw_how_to_play(self, surface: pygame.Surface) -> None:
        panel = pygame.Rect(34, 60, WIDTH - 68, 550)
        pygame.draw.rect(surface, (8, 12, 28), panel, border_radius=10)
        pygame.draw.rect(surface, CYAN, panel, width=3, border_radius=10)
        pygame.draw.line(surface, (255, 64, 214), (panel.x + 18, panel.y + 74), (panel.right - 18, panel.y + 74), 2)

        draw_center(surface, self.fonts.title, "玩法說明", panel.y + 42, WHITE)

        lines = [
            ("SPACE / ↑ / 滑鼠左鍵", "讓角色向上拍翅"),
            ("穿過霓虹水管缺口", "每通過一組得到 1 分"),
            ("避開水管與地板", "碰撞或飛出畫面就結束"),
            ("P 暫停  R 回標題", "Esc 離開遊戲"),
        ]
        y = panel.y + 126
        for command, detail in lines:
            command_image = self.fonts.medium.render(command, True, GOLD)
            detail_image = self.fonts.small.render(detail, True, WHITE)
            surface.blit(command_image, (panel.x + 34, y))
            surface.blit(detail_image, (panel.x + 36, y + 36))
            y += 76

        draw_center(surface, self.fonts.medium, "SPACE 開始挑戰", panel.bottom - 48, CYAN)
        draw_center(surface, self.fonts.small, "H / R 返回標題", panel.bottom - 20, MUTED)

    def run(self) -> None:
        running = True
        while running:
            for event in pygame.event.get():
                running = self.handle_event(event)
                if not running:
                    break
            self.update()
            self.draw()
            pygame.display.flip()
            self.clock.tick(FPS)


def random_gap_y() -> int:
    return random.randint(PLAY_TOP + 108, PLAY_BOTTOM - 108)


def score_sparks() -> list[Particle]:
    return [
        Particle(
            pygame.Vector2(BIRD_X + random.randrange(-8, 18), random.randrange(PLAY_TOP + 40, PLAY_BOTTOM - 40)),
            pygame.Vector2(random.uniform(-1.8, 1.2), random.uniform(-2.8, -0.4)),
            random.uniform(14, 28),
            random.choice([CYAN, WHITE, GOLD]),
            random.uniform(1.5, 3.5),
        )
        for _ in range(12)
    ]


def draw_center(
    surface: pygame.Surface,
    font: pygame.font.Font,
    text: str,
    y: int,
    color: tuple[int, int, int],
) -> None:
    image = font.render(text, True, color)
    shadow = font.render(text, True, BLACK)
    rect = image.get_rect(center=(WIDTH // 2, y))
    surface.blit(shadow, rect.move(2, 2))
    surface.blit(image, rect)


def draw_number(
    surface: pygame.Surface,
    digits: dict[str, pygame.Surface],
    number: int,
    y: int,
    scale: float = 1,
) -> None:
    images = [digits[digit] for digit in str(number)]
    width = sum(image.get_width() for image in images) + max(0, len(images) - 1) * 2
    x = round((WIDTH - width * scale) / 2)
    for image in images:
        if scale != 1:
            image = pygame.transform.scale_by(image, scale)
        surface.blit(image, (x, y))
        x += image.get_width() + 2


def load_image(path: Path, scale: float = 1) -> pygame.Surface:
    image = pygame.image.load(path).convert_alpha()
    if scale != 1:
        image = pygame.transform.scale_by(image, scale)
    return image


def load_assets() -> Assets:
    background = pygame.image.load(ROOT / "Game Objects" / "background-day.png").convert()
    background = pygame.transform.smoothscale(background, (WIDTH, HEIGHT))

    base = load_image(ROOT / "Game Objects" / "base.png")
    base = pygame.transform.smoothscale(base, (round(base.get_width() * 1.4), HEIGHT - PLAY_BOTTOM))

    pipe = load_image(ROOT / "Game Objects" / "pipe-green.png")
    pipe = pygame.transform.smoothscale(pipe, (GATE_WIDTH, round(pipe.get_height() * 1.55)))
    pipes = (pygame.transform.flip(pipe, False, True), pipe)

    bird_paths = [
        ROOT / "Game Objects" / "yellowbird-upflap.png",
        ROOT / "Game Objects" / "yellowbird-midflap.png",
        ROOT / "Game Objects" / "yellowbird-downflap.png",
        ROOT / "Game Objects" / "yellowbird-midflap.png",
    ]
    birds = [load_image(path) for path in bird_paths]

    digits = {
        str(number): load_image(ROOT / "UI" / "Numbers" / f"{number}.png", 1.2)
        for number in range(10)
    }
    message = load_image(ROOT / "UI" / "message.png", 1.35)
    game_over = load_image(ROOT / "UI" / "gameover.png", 1.45)

    return Assets(
        background=background,
        base=base,
        pipes=pipes,
        birds=birds,
        digits=digits,
        message=message,
        game_over=game_over,
        sounds=load_sounds(),
    )


def load_sounds() -> dict[str, pygame.mixer.Sound]:
    sound_dir = ROOT / "Sound Efects"
    sounds = {}
    for name in ("wing", "swoosh", "point", "hit", "die"):
        for suffix in (".ogg", ".wav"):
            path = sound_dir / f"{name}{suffix}"
            if path.exists():
                try:
                    sounds[name] = pygame.mixer.Sound(path)
                except pygame.error:
                    pass
                break
    return sounds


def play_sound(assets: Assets, name: str) -> None:
    sound = assets.sounds.get(name)
    if sound is not None:
        sound.play()


def load_best_score() -> int:
    try:
        data = json.loads(SAVE_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return 0
    return int(data.get("best_score", 0))


def save_best_score(score: int) -> None:
    try:
        SAVE_PATH.write_text(json.dumps({"best_score": score}), encoding="utf-8")
    except OSError:
        pass


def make_fonts() -> FontBook:
    family = find_readable_font()
    return FontBook(
        title=pygame.font.Font(family, 58),
        big=pygame.font.Font(family, 62),
        medium=pygame.font.Font(family, 34),
        small=pygame.font.Font(family, 25),
        tiny=pygame.font.Font(family, 18),
    )


def find_readable_font() -> str | None:
    candidates = [
        Path("/System/Library/Fonts/STHeiti Medium.ttc"),
        Path("/System/Library/Fonts/Hiragino Sans GB.ttc"),
        Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
        Path("/System/Library/Fonts/Supplemental/Songti.ttc"),
    ]
    for path in candidates:
        if path.exists():
            return str(path)
    return pygame.font.match_font(["Arial Unicode MS", "Arial"])


def main() -> None:
    pygame.init()
    try:
        pygame.mixer.init()
    except pygame.error:
        pass
    pygame.display.set_caption("Flapper Bird")
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    clock = pygame.time.Clock()
    Game(screen=screen, clock=clock, fonts=make_fonts(), assets=load_assets()).run()
    pygame.quit()
