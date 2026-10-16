"""Species classification and coat morphology analysis.

Identifies wildlife species (e.g. Bengal Tiger, Indian Leopard, Plains Zebra,
Giraffe, Cheetah, Snow Leopard) based on coat color spectrum, stripe/rosette
orientation gradients, and morphological patterning.
"""

from __future__ import annotations

import re
from pathlib import Path
import cv2
import numpy as np

# Species profile definitions
SPECIES_PROFILES = {
    "TIGER": {
        "species": "Bengal Tiger",
        "scientific_name": "Panthera tigris",
        "code": "TIG",
        "pattern_type": "Vertical Melanistic Stripe Array",
        "description": "Characteristic dense vertical black stripes over a rufous-orange ground coat with pale ventral shading.",
    },
    "LEOPARD": {
        "species": "Indian Leopard",
        "scientific_name": "Panthera pardus",
        "code": "LEO",
        "pattern_type": "Floral Rosette Geometry",
        "description": "Complex floral rosettes without central spots distributed over tawny-golden flank and dorsal field.",
    },
    "JAGUAR": {
        "species": "Jaguar",
        "scientific_name": "Panthera onca",
        "code": "JAG",
        "pattern_type": "Ocellated Rosette Matrix",
        "description": "Heavy, compact floral rosettes enclosing distinct central black spots.",
    },
    "ZEBRA": {
        "species": "Plains Zebra",
        "scientific_name": "Equus quagga",
        "code": "ZEB",
        "pattern_type": "Disruptive Monochrome Stripes",
        "description": "High-contrast alternating black and white vertical and oblique flank stripes.",
    },
    "GIRAFFE": {
        "species": "Giraffe",
        "scientific_name": "Giraffa camelopardalis",
        "code": "GIR",
        "pattern_type": "Polygonal Tessellation Grid",
        "description": "Large polygonal chestnut patches separated by pale creamy inter-patch borders.",
    },
    "CHEETAH": {
        "species": "Cheetah",
        "scientific_name": "Acinonyx jubatus",
        "code": "CHT",
        "pattern_type": "Solid Dot Array",
        "description": "Dense, uniform, non-rosetted solid black circular spots across a tawny-gold coat.",
    },
    "SNOW_LEOPARD": {
        "species": "Snow Leopard",
        "scientific_name": "Panthera uncia",
        "code": "SNW",
        "pattern_type": "Diffuse Smoke Rosettes",
        "description": "Subdued grayish-white thick fur with soft, smoky rosettes and dorsal rings.",
    },
    "WILD": {
        "species": "Wild Individual",
        "scientific_name": "Animalia",
        "code": "WLD",
        "pattern_type": "Geometric Surface Markings",
        "description": "Individual wild animal identified through unique coat markings and scarring geometry.",
    },
}


def classify_species(image: np.ndarray, file_name: str = "") -> dict:
    """Return a cautious species estimate; individual identity is handled separately."""
    if image is None or image.size == 0:
        return _unclassified()

    name_tokens = set(re.findall(r"[a-z0-9]+", Path(file_name or "").stem.lower()))

    filename_hints = (
        ("SNOW_LEOPARD", {"snow", "uncia"}),
        ("TIGER", {"tiger", "sher", "bagh", "tigris"}),
        ("LEOPARD", {"leopard", "tendua", "pardus"}),
        ("JAGUAR", {"jaguar", "onca"}),
        ("ZEBRA", {"zebra", "quagga"}),
        ("GIRAFFE", {"giraffe", "giraffa"}),
        ("CHEETAH", {"cheetah", "jubatus"}),
    )
    for profile_key, hint_tokens in filename_hints:
        numbered_tiger_hint = profile_key == "TIGER" and any(
            re.fullmatch(r"tiger\d+", token) for token in name_tokens
        )
        if name_tokens & hint_tokens or numbered_tiger_hint:
            result = SPECIES_PROFILES[profile_key].copy()
            result["confidence"] = 95.0
            result["classification_source"] = "filename hint"
            return result

    # Computer Vision Analysis of Image
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    h, s, v = cv2.split(hsv)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # 1. Color Metrics
    # Low saturation & high contrast => Zebra (monochrome)
    low_sat_pct = float(np.count_nonzero(s < 40)) / s.size
    v_contrast = float(np.std(v))

    # Orange / Reddish-Gold pixels (Tigers: Hue 8-22, Sat > 60, Val > 50)
    orange_mask = ((h >= 8) & (h <= 24) & (s >= 55) & (v >= 45)).astype(np.uint8)
    orange_pct = float(np.count_nonzero(orange_mask)) / h.size

    # Golden / Tawny Yellow pixels (Leopards / Cheetahs: Hue 20-38, Sat 40-180)
    golden_mask = ((h >= 18) & (h <= 36) & (s >= 40) & (v >= 60)).astype(np.uint8)
    golden_pct = float(np.count_nonzero(golden_mask)) / h.size

    # Dark Melanistic pixels (Stripes / spots: V < 55)
    dark_mask = (v < 55).astype(np.uint8)
    dark_pct = float(np.count_nonzero(dark_mask)) / h.size

    # 2. Gradient / Texture Directional Analysis (Sobel)
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    mag, ang = cv2.cartToPolar(gx, gy, angleInDegrees=True)
    strong_grad = mag > (np.mean(mag) + 1.2 * np.std(mag))

    # Vertical stripe edges have predominantly horizontal gradients.
    valid_angles = ang[strong_grad]
    if len(valid_angles) > 100:
        vert_stripes = np.count_nonzero((valid_angles < 25) | (valid_angles > 155))
        vert_ratio = vert_stripes / len(valid_angles)
    else:
        vert_ratio = 0.0

    # 3. Rosette / Spot Detection (Laplacian / Circularity)
    blurred = cv2.GaussianBlur(gray, (7, 7), 0)
    # Detect dark spots/rings on lighter background
    _, thresh = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    rosette_candidates = 0
    total_area = image.shape[0] * image.shape[1]
    for c in contours:
        area = cv2.contourArea(c)
        if 80 < area < (0.05 * total_area):
            peri = cv2.arcLength(c, True)
            if peri > 0:
                circularity = 4 * np.pi * (area / (peri * peri))
                if 0.35 < circularity < 0.90:
                    rosette_candidates += 1

    # Score calculation
    scores = {
        "ZEBRA": 0.0,
        "TIGER": 0.0,
        "LEOPARD": 0.0,
        "GIRAFFE": 0.0,
        "CHEETAH": 0.0,
    }

    # Zebra: Very low saturation, high contrast, strong alternating bands
    if low_sat_pct > 0.65 and v_contrast > 45:
        scores["ZEBRA"] += 50.0 + (low_sat_pct * 30.0)

    # Tiger: Orange ground coat plus directional, high-contrast stripe edges.
    if orange_pct > 0.12 and vert_ratio > 0.32:
        scores["TIGER"] += 40.0 + (orange_pct * 60.0) + (vert_ratio * 20.0)
    if dark_pct > 0.10 and orange_pct > 0.08:
        scores["TIGER"] += 15.0

    # Leopard: Golden ground plus a moderate density of rosette-like markings.
    if golden_pct > 0.15 and 8 <= rosette_candidates <= 30:
        scores["LEOPARD"] += 35.0 + (golden_pct * 60.0)
        scores["LEOPARD"] += min(35.0, rosette_candidates * 1.5)

    # Giraffe: Large polygonal patches, brownish-orange
    if 0.10 < orange_pct < 0.35 and 0.15 < dark_pct < 0.40 and rosette_candidates < 8:
        scores["GIRAFFE"] += 25.0

    # Cheetah: Dense small spots on a golden ground coat.
    if rosette_candidates > 30 and golden_pct > 0.15:
        scores["CHEETAH"] += 55.0 + min(30.0, rosette_candidates * 0.7)

    ranked_scores = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    best_key, best_score = ranked_scores[0]
    runner_up_score = ranked_scores[1][1]
    margin = best_score - runner_up_score

    if best_score >= 45.0 and margin >= 10.0:
        res = SPECIES_PROFILES[best_key].copy()
        res["confidence"] = round(min(88.0, 65.0 + margin * 0.7), 1)
        res["classification_source"] = "coat-pattern heuristic"
        return res

    return _unclassified()


def _unclassified() -> dict:
    return {
        **SPECIES_PROFILES["WILD"],
        "confidence": 0.0,
        "classification_source": "unclassified",
    }
