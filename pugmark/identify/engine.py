"""Individual animal re-identification from photos and video frames.

This is the classic wildlife mark-recapture approach used by tools such as
HotSpotter, not a face-recognition model and not a guess from body pose.

For every file we:
  1. Pull a sharp view (a still, or the sharpest frames of a clip).
  2. Describe markings with SIFT, on the full frame and on a saliency crop.
  3. Keep only matches that survive a geometric check (RANSAC affine).
  4. Call same / different / inconclusive from the inlier count.
  5. Group files that passed as the same individual.

Pose, mouth movement and "it is also a tiger" are not identity. Two tigers
share a skeleton. Identity here is the geometry of spots, stripes and scars.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, UnidentifiedImageError

from .species import classify_species

Image.MAX_IMAGE_PIXELS = 36_000_000

MAX_SIDE = 960
DIFFERENT_INLIERS = 9


class EngineError(ValueError):
    pass


@dataclass
class View:
    image: np.ndarray
    keypoints: list
    descriptors: np.ndarray | None
    sharpness: float
    tag: str


@dataclass
class Signature:
    file_id: str
    name: str
    kind: str
    views: list[View]
    digest: np.ndarray
    quality: str
    point_count: int
    preview_name: str = ""
    note: str = ""
    species: str = "Wild Individual"
    scientific_name: str = "Animalia"
    pattern_type: str = "Geometric Surface Markings"
    species_confidence: float = 85.0
    species_source: str = "unclassified"


@dataclass
class PairResult:
    a: str
    b: str
    verdict: str
    inliers: int
    good: int
    ratio: float
    reason: str
    evidence_name: str = ""
    low_quality: bool = False


def analyze(items: list[dict], out_dir: Path, media_url: str) -> dict:
    """Compare a batch of media files and write thumbs plus match sheets.

    Each item needs id, name, path, kind ("image" or "video").
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if not media_url.endswith("/"):
        media_url += "/"

    signatures: list[Signature] = []
    skipped: list[dict] = []
    for item in items:
        try:
            signature = _signature_for(item, out_dir)
        except EngineError as exc:
            skipped.append({"name": item["name"], "reason": str(exc)})
            continue
        signatures.append(signature)

    if len(signatures) < 2:
        detail = ""
        if skipped:
            detail = " " + " ".join(f"{s['name']}: {s['reason']}" for s in skipped)
        raise EngineError(
            "Need at least two readable photos or videos to compare." + detail
        )

    pairs = [_compare(a, b, out_dir) for i, a in enumerate(signatures) for b in signatures[i + 1 :]]
    rank = {"same": 0, "uncertain": 1, "different": 2}
    pairs.sort(key=lambda pair: (rank[pair.verdict], -pair.inliers, -pair.ratio))
    _attach_evidence(pairs, signatures, out_dir)
    individuals = _cluster(signatures, pairs)
    summary = _summarize(signatures, pairs, individuals)

    def url_for(name: str) -> str:
        if not name:
            return ""
        relative = Path(out_dir.name) / name
        # out_dir is MEDIA_ROOT/reports/<scan>
        parent = out_dir.parent.name
        return f"{media_url}{parent}/{out_dir.name}/{name}"

    by_id = {sig.file_id: sig for sig in signatures}
    files_out = []
    for sig in signatures:
        files_out.append(
            {
                "id": sig.file_id,
                "name": sig.name,
                "kind": sig.kind,
                "quality": sig.quality,
                "points": sig.point_count,
                "note": sig.note,
                "preview": url_for(sig.preview_name),
                "species": sig.species,
                "scientific_name": sig.scientific_name,
                "pattern_type": sig.pattern_type,
                "species_confidence": sig.species_confidence,
                "species_source": sig.species_source,
            }
        )
    file_card = {row["id"]: row for row in files_out}
    for individual in individuals:
        individual["files"] = [file_card[file_id] for file_id in individual["file_ids"]]
        primary_f = individual["files"][0] if individual["files"] else {}
        individual["species"] = primary_f.get("species", "Wild Individual")
        individual["scientific_name"] = primary_f.get("scientific_name", "")
        individual["pattern_type"] = primary_f.get("pattern_type", "")
        individual["species_confidence"] = primary_f.get("species_confidence", 85.0)
        individual["species_source"] = primary_f.get("species_source", "unclassified")

    pairs_out = []
    for pair in pairs:
        pairs_out.append(
            {
                "a": pair.a,
                "b": pair.b,
                "a_name": by_id[pair.a].name,
                "b_name": by_id[pair.b].name,
                "verdict": pair.verdict,
                "inliers": pair.inliers,
                "good": pair.good,
                "ratio": round(pair.ratio, 3),
                "reason": pair.reason,
                "evidence": url_for(pair.evidence_name),
            }
        )

    return {
        "summary": summary,
        "files": files_out,
        "pairs": pairs_out,
        "individuals": individuals,
        "skipped": skipped,
        "_signatures_by_id": by_id,
        "method": (
            "SIFT markings on each animal region, kept only when they agree "
            "under one geometric transform (RANSAC). Same family as HotSpotter, "
            "the classic wildlife re-identification matcher. Pose is not used."
        ),
    }


def _signature_for(item: dict, out_dir: Path) -> Signature:
    kind = item["kind"]
    path = Path(item["path"])
    if kind == "video":
        frames = _video_frames(path)
        views = []
        for sharp, _index, at, image in frames:
            tag = f"{at:.1f}s" if at is not None else "frame"
            views.append(_describe(image, tag))
        note = f"{len(views)} sharp frames sampled"
    else:
        image = _load_image(path)
        if image is None:
            raise EngineError("Could not read this image.")
        full = _describe(image, "full")
        crop = _animal_crop(image)
        views = [full]
        if crop is not None:
            views.append(_describe(crop, "animal region"))
        note = f"{len(views[0].keypoints)} marking points"

    if not views or all(v.descriptors is None or len(v.keypoints) < 8 for v in views):
        raise EngineError("No stable markings found. Try a closer, sharper view of the coat.")

    best = max(views, key=lambda v: len(v.keypoints))
    quality = "good"
    if best.sharpness < 18 or len(best.keypoints) < 40:
        quality = "weak"
        note = "Soft or sparse detail — treat a mismatch as inconclusive"

    preview = views[0].image
    preview_name = f"{item['id']}-preview.jpg"
    _write_jpeg(preview, out_dir / preview_name, max_side=720)

    species_res = classify_species(preview, item["name"])

    return Signature(
        file_id=str(item["id"]),
        name=item["name"],
        kind=kind,
        views=views,
        digest=_dhash(views[0].image),
        quality=quality,
        point_count=len(best.keypoints),
        preview_name=preview_name,
        note=note,
        species=species_res.get("species", "Wild Individual"),
        scientific_name=species_res.get("scientific_name", "Animalia"),
        pattern_type=species_res.get("pattern_type", "Geometric Surface Markings"),
        species_confidence=species_res.get("confidence", 85.0),
        species_source=species_res.get("classification_source", "unclassified"),
    )


def _compare(a: Signature, b: Signature, out_dir: Path) -> PairResult:
    best = None
    best_views = None
    for va in a.views:
        for vb in b.views:
            matched = _match(va, vb)
            rank = (matched["inliers"], matched["ratio"])
            if best is None or rank > (best["inliers"], best["ratio"]):
                best = matched
                best_views = (va, vb)
    assert best is not None and best_views is not None
    low = a.quality == "weak" or b.quality == "weak"
    verdict = _verdict(best["inliers"], best["ratio"], low)
    reason = _reason(verdict, best["inliers"], best["good"], best["ratio"], low, a, b)
    pair = PairResult(
        a=a.file_id,
        b=b.file_id,
        verdict=verdict,
        inliers=best["inliers"],
        good=best["good"],
        ratio=best["ratio"],
        reason=reason,
        low_quality=low,
    )
    pair._views = best_views  # type: ignore[attr-defined]
    pair._matched = best  # type: ignore[attr-defined]
    return pair


def _verdict(inliers: int, ratio: float, low: bool) -> str:
    # Ratio matters more than raw count. A smooth body outline can produce a
    # handful of geometrically consistent points across two different coats.
    confident = inliers >= 18 and ratio >= 0.42
    many = inliers >= 48 and ratio >= 0.32
    if confident or many:
        if low and inliers < 40 and ratio < 0.55:
            return "uncertain"
        return "same"
    if low:
        return "uncertain"
    if inliers <= DIFFERENT_INLIERS:
        return "different"
    return "uncertain"


def _reason(verdict: str, inliers: int, good: int, ratio: float, low: bool, a: Signature, b: Signature) -> str:
    a_sp = a.species or "Wild Individual"
    b_sp = b.species or "Wild Individual"

    if verdict == "same":
        where = ""
        if a.kind == "video" or b.kind == "video":
            where = " Video clips contributed their sharpest stable frames."
        return (
            f"Geometric match supported: Both sightings are consistent with the same {a_sp}. "
            f"{inliers} coat landmarks survived RANSAC out of {good} candidates "
            f"({ratio:.0%} inlier ratio). This is evidence of individual identity, not proof; "
            f"review the aligned points before relying on the result." + where
        )

    if (
        a_sp != b_sp
        and a_sp != "Wild Individual"
        and b_sp != "Wild Individual"
        and a.species_confidence >= 80
        and b.species_confidence >= 80
    ):
        return (
            f"Species estimates differ: {a.name} is estimated as {a_sp}, "
            f"whereas {b.name} is estimated as {b_sp}. "
            f"Only {inliers} correspondences survived geometric verification out of {good} candidates. "
            f"These results support different individuals; confirm the species estimates independently."
        )

    if verdict == "different":
        species_context = (
            f"Both sightings are estimated as {a_sp}, but "
            if a_sp != "Wild Individual"
            else ""
        )
        return (
            f"Pattern geometry differs: {species_context}the coat markings do not align. "
            f"Only {inliers} correspondences survived geometric consensus out of {good} candidates "
            f"(a match needs at least 18 inliers with a sufficient ratio). This supports different individuals, "
            f"but is not proof."
        )

    if low:
        return (
            f"Inconclusive Evidence: At least one view of this {a_sp} is soft, low-resolution, or occluded. "
            f"Only {inliers} points were detected. A mismatch here would be a guess, so the system refuses to "
            f"force a decision to avoid false positive error."
        )

    return (
        f"Intermediate Correspondence: {inliers} landmarks line up ({good} candidates). "
        f"This does not reach the identity threshold (at least 18 inliers and a sufficient ratio) "
        f"for individual identity. Capture a clearer flank or facial angle to verify."
    )


def _attach_evidence(pairs: list[PairResult], signatures: list[Signature], out_dir: Path) -> None:
    by_id = {sig.file_id: sig for sig in signatures}
    interesting = [p for p in pairs if p.verdict in {"same", "uncertain"} and p.inliers >= 6]
    if not interesting:
        different = [p for p in pairs if p.verdict == "different"]
        if different:
            interesting = [max(different, key=lambda p: p.inliers)]

    for pair in interesting:
        views = getattr(pair, "_views", None)
        matched = getattr(pair, "_matched", None)
        if not views or not matched:
            continue
        left, right = views
        sig_a = by_id.get(pair.a)
        sig_b = by_id.get(pair.b)
        name = f"pair-{pair.a}-{pair.b}.jpg"
        canvas = _render_evidence_canvas(pair, left, right, matched, sig_a, sig_b)
        if canvas is not None:
            _write_jpeg(canvas, out_dir / name, max_side=1400)
            pair.evidence_name = name


def _render_evidence_canvas(
    pair: PairResult,
    left: View,
    right: View,
    matched: dict,
    sig_a: Signature | None,
    sig_b: Signature | None,
) -> np.ndarray:
    target_h = 520
    h_l, w_l = left.image.shape[:2]
    h_r, w_r = right.image.shape[:2]

    scale_l = target_h / max(1, h_l)
    scale_r = target_h / max(1, h_r)

    img_l = cv2.resize(left.image, (max(1, int(w_l * scale_l)), target_h), interpolation=cv2.INTER_AREA)
    img_r = cv2.resize(right.image, (max(1, int(w_r * scale_r)), target_h), interpolation=cv2.INTER_AREA)

    wl, wr = img_l.shape[1], img_r.shape[1]
    gap = 40
    header_h = 65
    footer_h = 45
    canvas_w = wl + wr + gap
    canvas_h = target_h + header_h + footer_h

    canvas = np.zeros((canvas_h, canvas_w, 3), dtype=np.uint8)
    canvas[:] = (18, 25, 21)

    canvas[header_h : header_h + target_h, :wl] = img_l
    canvas[header_h : header_h + target_h, wl + gap : canvas_w] = img_r

    # Middle vertical separator
    cx = wl + gap // 2
    cv2.line(canvas, (cx, header_h), (cx, header_h + target_h), (40, 60, 48), 1, cv2.LINE_AA)

    font = cv2.FONT_HERSHEY_SIMPLEX

    if pair.verdict == "same":
        cv2.rectangle(canvas, (0, 0), (canvas_w, header_h), (25, 55, 35), -1)
        cv2.putText(canvas, "WILD-ID NEXUS: GEOMETRIC MATCH SUPPORTS SAME INDIVIDUAL", (20, 26), font, 0.62, (100, 245, 160), 2, cv2.LINE_AA)
        cv2.putText(canvas, f"RANSAC inliers: {pair.inliers}/{pair.good} ({pair.ratio:.0%})", (20, 50), font, 0.46, (200, 240, 210), 1, cv2.LINE_AA)

        chosen = matched.get("draw") or []
        if chosen:
            # _match only returns points that survived its RANSAC geometry check.
            for m in chosen:
                pt_l = (int(left.keypoints[m.queryIdx].pt[0] * scale_l), int(left.keypoints[m.queryIdx].pt[1] * scale_l) + header_h)
                pt_r = (int(right.keypoints[m.trainIdx].pt[0] * scale_r) + wl + gap, int(right.keypoints[m.trainIdx].pt[1] * scale_r) + header_h)
                cv2.line(canvas, pt_l, pt_r, (46, 204, 113), 2, cv2.LINE_AA)
                cv2.circle(canvas, pt_l, 6, (34, 197, 94), 2, cv2.LINE_AA)
                cv2.circle(canvas, pt_l, 2, (0, 255, 255), -1, cv2.LINE_AA)
                cv2.circle(canvas, pt_r, 6, (34, 197, 94), 2, cv2.LINE_AA)
                cv2.circle(canvas, pt_r, 2, (0, 255, 255), -1, cv2.LINE_AA)

        name_a = sig_a.name if sig_a else "File A"
        name_b = sig_b.name if sig_b else "File B"
        cv2.putText(canvas, f"Sighting A: {name_a}", (15, header_h + target_h + 28), font, 0.48, (180, 220, 190), 1, cv2.LINE_AA)
        cv2.putText(canvas, f"Sighting B: {name_b}", (wl + gap + 15, header_h + target_h + 28), font, 0.48, (180, 220, 190), 1, cv2.LINE_AA)

    elif pair.verdict == "different":
        cv2.rectangle(canvas, (0, 0), (canvas_w, header_h), (35, 25, 45), -1)
        cv2.putText(canvas, "WILD-ID NEXUS: GEOMETRIC MISMATCH (DIFFERENT INDIVIDUALS)", (20, 26), font, 0.62, (130, 150, 255), 2, cv2.LINE_AA)
        cv2.putText(canvas, f"Pattern Divergence: Only {pair.inliers} incidental correspondences ({pair.good} evaluated - threshold >= 18)", (20, 50), font, 0.46, (210, 210, 240), 1, cv2.LINE_AA)

        # Highlight landmark points on each independently - DO NOT connect with crossing lines!
        for kp in left.keypoints[:25]:
            pt = (int(kp.pt[0] * scale_l), int(kp.pt[1] * scale_l) + header_h)
            cv2.circle(canvas, pt, 5, (240, 200, 0), 2, cv2.LINE_AA)
            cv2.circle(canvas, pt, 1, (255, 255, 255), -1, cv2.LINE_AA)

        for kp in right.keypoints[:25]:
            pt = (int(kp.pt[0] * scale_r) + wl + gap, int(kp.pt[1] * scale_r) + header_h)
            cv2.circle(canvas, pt, 5, (0, 140, 255), 2, cv2.LINE_AA)
            cv2.circle(canvas, pt, 1, (255, 255, 255), -1, cv2.LINE_AA)

        cy = header_h + target_h // 2
        cv2.circle(canvas, (cx, cy), 18, (45, 30, 80), -1)
        cv2.circle(canvas, (cx, cy), 18, (140, 140, 250), 2, cv2.LINE_AA)
        cv2.putText(canvas, "!=", (cx - 9, cy + 6), font, 0.6, (210, 210, 255), 2, cv2.LINE_AA)

        name_a = sig_a.name if sig_a else "File A"
        name_b = sig_b.name if sig_b else "File B"
        cv2.putText(canvas, f"Sighting A: {name_a} (Pattern Topology 1)", (15, header_h + target_h + 28), font, 0.48, (200, 200, 200), 1, cv2.LINE_AA)
        cv2.putText(canvas, f"Sighting B: {name_b} (Pattern Topology 2)", (wl + gap + 15, header_h + target_h + 28), font, 0.48, (200, 200, 200), 1, cv2.LINE_AA)

    else:
        cv2.rectangle(canvas, (0, 0), (canvas_w, header_h), (40, 40, 30), -1)
        cv2.putText(canvas, "WILD-ID NEXUS: INCONCLUSIVE (INSUFFICIENT RESOLUTION / ANGLE)", (20, 26), font, 0.62, (100, 220, 240), 2, cv2.LINE_AA)
        cv2.putText(canvas, f"Indeterminate: {pair.inliers} points found. Refuses to guess to prevent false identification.", (20, 50), font, 0.46, (220, 230, 230), 1, cv2.LINE_AA)
        name_a = sig_a.name if sig_a else "File A"
        name_b = sig_b.name if sig_b else "File B"
        cv2.putText(canvas, f"Sighting A: {name_a}", (15, header_h + target_h + 28), font, 0.48, (200, 200, 200), 1, cv2.LINE_AA)
        cv2.putText(canvas, f"Sighting B: {name_b}", (wl + gap + 15, header_h + target_h + 28), font, 0.48, (200, 200, 200), 1, cv2.LINE_AA)

    return canvas


def _cluster(signatures: list[Signature], pairs: list[PairResult]) -> list[dict]:
    parent = {sig.file_id: sig.file_id for sig in signatures}
    pair_verdicts = {frozenset((pair.a, pair.b)): pair.verdict for pair in pairs}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x: str, y: str) -> None:
        rx, ry = find(x), find(y)
        if rx != ry:
            parent[ry] = rx

    for pair in pairs:
        if pair.verdict != "same":
            continue
        left_root, right_root = find(pair.a), find(pair.b)
        if left_root == right_root:
            continue
        left_members = [file_id for file_id in parent if find(file_id) == left_root]
        right_members = [file_id for file_id in parent if find(file_id) == right_root]
        if all(
            pair_verdicts.get(frozenset((left, right))) == "same"
            for left in left_members
            for right in right_members
        ):
            union(left_root, right_root)

    groups: dict[str, list[str]] = {}
    for sig in signatures:
        groups.setdefault(find(sig.file_id), []).append(sig.file_id)

    # Largest groups first, then stable by first member order.
    ordered = sorted(groups.values(), key=lambda members: (-len(members), members[0]))
    letters = "ABCDEFGHJKLMNPQRSTUVWXYZ"
    individuals = []
    pair_index = {(p.a, p.b): p for p in pairs}
    for index, members in enumerate(ordered):
        label = letters[index] if index < len(letters) else str(index + 1)
        matching_pairs = 0
        for i, left in enumerate(members):
            for right in members[i + 1 :]:
                pair = pair_index.get((left, right)) or pair_index.get((right, left))
                if pair is not None and pair.verdict == "same":
                    matching_pairs += 1
        alone = len(members) == 1
        individuals.append(
            {
                "id": label,
                "title": f"Individual {label}",
                "file_ids": members,
                "matching_pairs": matching_pairs,
                "alone": alone,
            }
        )
    return individuals


def _summarize(signatures: list[Signature], pairs: list[PairResult], individuals: list[dict]) -> dict:
    n = len(signatures)
    k = len(individuals)
    kinds = {p.verdict for p in pairs}
    if k == 1:
        return {
            "verdict": "same",
            "kicker": "Same animal",
            "headline": "These files are one individual.",
            "dek": "Coat geometry agrees across this set. The group below is a single animal, seen more than once.",
            "individuals": k,
            "files": n,
        }
    if k == n and kinds == {"different"}:
        noun = "animal" if n == 2 else "animals"
        return {
            "verdict": "different",
            "kicker": "Different animals",
            "headline": f"These are {n} different {noun}." if n > 2 else "These are not the same individual.",
            "dek": "Markings do not share a geometric match. Same species is not the same animal.",
            "individuals": k,
            "files": n,
        }
    if k == n and "same" not in kinds:
        return {
            "verdict": "uncertain",
            "kicker": "Inconclusive",
            "headline": "Not enough evidence to decide.",
            "dek": "Nothing here is a confident match, and a confident rejection would overclaim. Shoot the flank, face, or rump again.",
            "individuals": k,
            "files": n,
        }
    return {
        "verdict": "mixed",
        "kicker": f"{k} individuals",
        "headline": f"{n} files resolve to {k} animals.",
        "dek": (
            "Some files form a supported match. Review the uncertain comparisons "
            "before treating the remaining groups as different individuals."
            if "uncertain" in kinds
            else "Grouped files matched each other; the remaining comparisons did not pass the match threshold."
        ),
        "individuals": k,
        "files": n,
    }


def _load_image(path: Path) -> np.ndarray | None:
    try:
        with Image.open(path) as im:
            im = im.convert("RGB")
            w, h = im.size
            scale = MAX_SIDE / max(w, h)
            if scale < 1:
                im = im.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.Resampling.LANCZOS)
            rgb = np.asarray(im)
            if rgb.ndim != 3 or rgb.shape[2] != 3:
                return None
            return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    except (UnidentifiedImageError, OSError, ValueError):
        image = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if image is None:
            return None
        return _resize_max(image, MAX_SIDE)


def _video_frames(path: Path) -> list[tuple[float, int, float | None, np.ndarray]]:
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise EngineError("Could not read this video. Use MP4, MOV, AVI, MKV, or WEBM.")
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0) or 0.0
    picked: list[tuple[int, np.ndarray]] = []
    try:
        if 0 < total < 100000:
            indexes = np.linspace(0, total - 1, num=min(12, total), dtype=int)
            seen: set[int] = set()
            for index in indexes:
                index = int(index)
                if index in seen:
                    continue
                seen.add(index)
                cap.set(cv2.CAP_PROP_POS_FRAMES, index)
                ok, frame = cap.read()
                if ok and frame is not None:
                    picked.append((index, frame))
        else:
            index = 0
            while len(picked) < 12 and index < 360:
                ok, frame = cap.read()
                if not ok or frame is None:
                    break
                if index % 3 == 0:
                    picked.append((index, frame))
                index += 1
    finally:
        cap.release()
    if not picked:
        raise EngineError("This video has no readable frames.")
    scored = []
    for index, frame in picked:
        image = _resize_max(frame, 720)
        sharp = _sharpness(image)
        at = (index / fps) if fps else None
        scored.append((sharp, index, at, image))
    scored.sort(key=lambda row: row[0], reverse=True)
    keep = scored[:4]
    keep.sort(key=lambda row: row[1])
    return keep


def _describe(image: np.ndarray, tag: str) -> View:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    sift = cv2.SIFT_create(nfeatures=800, contrastThreshold=0.04, edgeThreshold=12)
    keypoints, descriptors = sift.detectAndCompute(gray, None)
    if descriptors is not None:
        descriptors = np.asarray(descriptors, dtype=np.float32)
    return View(
        image=image,
        keypoints=keypoints or [],
        descriptors=descriptors,
        sharpness=_sharpness(image),
        tag=tag,
    )


def _animal_crop(image: np.ndarray) -> np.ndarray | None:
    """Center-biased spectral saliency. Falls back to no crop when unsure."""
    try:
        saliency = cv2.saliency.StaticSaliencySpectralResidual_create()
        ok, sal_map = saliency.computeSaliency(image)
    except cv2.error:
        return None
    if not ok or sal_map is None:
        return None
    sal_map = sal_map.astype(np.float32)
    height, width = sal_map.shape[:2]
    ys = np.linspace(-1, 1, height, dtype=np.float32)[:, None]
    xs = np.linspace(-1, 1, width, dtype=np.float32)[None, :]
    bias = np.exp(-((xs ** 2) + (ys ** 2)) / 0.85)
    weighted = sal_map * (0.40 + 0.60 * bias)
    span = float(np.ptp(weighted)) + 1e-6
    weighted = (weighted - float(weighted.min())) / span
    mask = (weighted > 0.55).astype(np.uint8) * 255
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    contour = max(contours, key=cv2.contourArea)
    x, y, w, h = cv2.boundingRect(contour)
    if w * h < 0.10 * width * height or w * h > 0.90 * width * height:
        return None
    pad_x, pad_y = int(w * 0.10), int(h * 0.10)
    x0, y0 = max(0, x - pad_x), max(0, y - pad_y)
    x1, y1 = min(width, x + w + pad_x), min(height, y + h + pad_y)
    crop = image[y0:y1, x0:x1]
    if crop.size == 0 or min(crop.shape[:2]) < 48:
        return None
    return crop


def _match(left: View, right: View) -> dict:
    empty = {"inliers": 0, "good": 0, "ratio": 0.0, "draw": None}
    da, db = left.descriptors, right.descriptors
    if da is None or db is None or len(left.keypoints) < 8 or len(right.keypoints) < 8:
        return empty
    matcher = cv2.FlannBasedMatcher(dict(algorithm=1, trees=5), dict(checks=40))
    try:
        knn = matcher.knnMatch(da, db, k=2)
    except cv2.error:
        return empty
    good = []
    for pair in knn:
        if len(pair) < 2:
            continue
        primary, secondary = pair
        if primary.distance < 0.75 * secondary.distance:
            good.append(primary)
    inliers = 0
    draw = None
    if len(good) >= 8:
        src = np.float32([left.keypoints[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
        dst = np.float32([right.keypoints[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
        cv2.setRNGSeed(42)
        _affine, mask = cv2.estimateAffinePartial2D(
            src,
            dst,
            method=cv2.RANSAC,
            ransacReprojThreshold=6.0,
            maxIters=2000,
            confidence=0.99,
        )
        if mask is not None:
            flat = mask.reshape(-1).astype(bool)
            inliers = int(flat.sum())
            chosen = [m for m, keep in zip(good, flat) if keep]
            chosen.sort(key=lambda m: m.distance)
            draw = chosen[:40]
    ratio = inliers / len(good) if good else 0.0
    return {"inliers": inliers, "good": len(good), "ratio": float(ratio), "draw": draw}


def _dhash(image: np.ndarray, hash_size: int = 8) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    small = cv2.resize(gray, (hash_size + 1, hash_size), interpolation=cv2.INTER_AREA)
    return (small[:, 1:] > small[:, :-1]).flatten()


def _sharpness(image: np.ndarray) -> float:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def _resize_max(image: np.ndarray, max_side: int) -> np.ndarray:
    height, width = image.shape[:2]
    scale = max_side / max(height, width)
    if scale >= 1:
        return image
    return cv2.resize(image, (max(1, int(width * scale)), max(1, int(height * scale))), interpolation=cv2.INTER_AREA)


def _write_jpeg(image: np.ndarray, path: Path, max_side: int = 960) -> None:
    image = _resize_max(image, max_side)
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), image, [int(cv2.IMWRITE_JPEG_QUALITY), 82])
