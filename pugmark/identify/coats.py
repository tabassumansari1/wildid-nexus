"""Synthetic coat cards used as a built-in demo.

The spots come from a fixed seed, so two renders with the same seed are the
same individual under a new photo (shift, brightness, background). A different
seed is a different animal. They are reference cards, not photographs.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np


def render_coat(
    seed: int,
    bg_seed: int = 0,
    angle: float = 0.0,
    bright: int = 0,
    shift: tuple[int, int] = (0, 0),
    scale: float = 1.0,
) -> np.ndarray:
    rng = np.random.default_rng(bg_seed)
    canvas = np.zeros((760, 980, 3), np.uint8)
    noise = rng.integers(28, 90, (76, 98, 3), dtype=np.uint8)
    noise = cv2.resize(noise, (980, 760), interpolation=cv2.INTER_LINEAR)
    canvas[:] = noise
    canvas[:, :, 1] = np.clip(canvas[:, :, 1].astype(np.int16) + 28, 0, 255).astype(np.uint8)

    body = np.zeros_like(canvas)
    center = (490 + shift[0], 400 + shift[1])
    axes = (int(310 * scale), int(168 * scale))
    coat = (176, 142, 86)
    cv2.ellipse(body, center, axes, 0, 0, 360, coat, -1)
    # Ear. Drawn from the same geometry every time so it is part of the animal,
    # not a random mark.
    ear = (center[0] - int(250 * scale), center[1] - int(150 * scale))
    cv2.ellipse(body, ear, (int(42 * scale), int(70 * scale)), -28, 0, 360, coat, -1)

    prng = np.random.default_rng(seed)
    for _ in range(18):
        cx = int(prng.integers(250, 760))
        cy = int(prng.integers(270, 540))
        ax = int(prng.integers(16, 52))
        ay = int(prng.integers(8, 22))
        ang = int(prng.integers(0, 180))
        color = (
            int(prng.integers(18, 48)),
            int(prng.integers(16, 40)),
            int(prng.integers(12, 32)),
        )
        cv2.ellipse(body, (cx, cy), (ax, ay), ang, 0, 360, color, -1)
    for _ in range(6):
        points = []
        x = int(prng.integers(230, 380))
        y = int(prng.integers(280, 500))
        for step in range(6):
            points.append([x + step * 42 + int(prng.integers(-6, 6)), y + int(prng.integers(-26, 26))])
        cv2.polylines(body, [np.array(points, np.int32)], False, (28, 22, 16), 4, cv2.LINE_AA)

    mask = body.any(axis=2)
    canvas[mask] = body[mask]
    canvas = np.clip(canvas.astype(np.int16) + int(bright), 0, 255).astype(np.uint8)
    if angle:
        matrix = cv2.getRotationMatrix2D((490, 390), angle, 1.0)
        canvas = cv2.warpAffine(canvas, matrix, (980, 760), borderMode=cv2.BORDER_REFLECT)
    return canvas


def save_demo_set(folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    cards = {
        "coat-a-morning.jpg": render_coat(1, bg_seed=10),
        "coat-a-later.jpg": render_coat(1, bg_seed=99, angle=7, bright=25, shift=(30, -20), scale=0.92),
        "coat-b.jpg": render_coat(7, bg_seed=11),
    }
    for name, image in cards.items():
        cv2.imwrite(str(folder / name), image)
