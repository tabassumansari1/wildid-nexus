"""Animal registry and persistent individual cross-scan tracking.

Matches incoming sightings against previously cataloged animals in the database.
If an animal already exists: returns its sighting history (when and where it was seen).
If an animal is new: assigns a persistent custom ID (e.g. TIG-001, LEO-002) and logs it.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
import numpy as np

from django.conf import settings
from django.utils import timezone

from .models import Individual, Sighting
from .species import classify_species

logger = logging.getLogger(__name__)


def process_scan_individuals(
    scan,
    analysis_result: dict,
    signatures_by_id: dict,
    scan_location: str = "Station 1 - Waterhole",
) -> None:
    """Check each individual in the scan against the database catalog."""
    if not scan_location:
        scan_location = "Station 1 - Waterhole"

    individuals = analysis_result.get("individuals", [])
    files_by_id = {f["id"]: f for f in analysis_result.get("files", [])}

    for ind in individuals:
        file_ids = ind.get("file_ids", [])
        if not file_ids:
            continue

        # Get the best signature for this individual
        primary_file_id = file_ids[0]
        primary_sig = signatures_by_id.get(primary_file_id)
        primary_file_info = files_by_id.get(primary_file_id, {})

        # Determine species for this individual from the best view
        sample_img = None
        if primary_sig and primary_sig.views:
            sample_img = primary_sig.views[0].image
        species_info = classify_species(sample_img, primary_file_info.get("name", ""))

        # Check against existing registered individuals in the database
        match_record = _find_existing_match(primary_sig, species_info["code"])

        if match_record:
            # Animal already exists in database!
            existing_ind, inliers, conf = match_record
            existing_ind.sighting_count += 1
            existing_ind.last_location = scan_location
            existing_ind.last_seen = timezone.now()
            existing_ind.save(update_fields=["sighting_count", "last_location", "last_seen"])

            # Create sighting record
            Sighting.objects.create(
                individual=existing_ind,
                scan=scan,
                image_path=primary_file_info.get("preview", ""),
                preview_url=primary_file_info.get("preview", ""),
                location=scan_location,
                confidence=conf,
                is_repeat=True,
                notes=f"Identified with {inliers} matching geometric landmark inliers.",
            )

            first_seen_str = existing_ind.first_seen.strftime("%d %b %Y, %I:%M %p")
            last_seen_str = existing_ind.last_seen.strftime("%d %b %Y, %I:%M %p")

            ind["database_status"] = "ALREADY_EXISTS"
            ind["database_id"] = existing_ind.custom_id
            ind["species"] = existing_ind.species
            ind["scientific_name"] = existing_ind.scientific_name
            ind["pattern_type"] = existing_ind.pattern_type or species_info["pattern_type"]
            ind["sighting_count"] = existing_ind.sighting_count
            ind["first_seen"] = first_seen_str
            ind["first_location"] = existing_ind.first_location
            ind["last_seen"] = last_seen_str
            ind["last_location"] = existing_ind.last_location
            ind["history_note"] = (
                f"Already cataloged! Previously spotted at {existing_ind.first_location} "
                f"on {first_seen_str}. Total lifetime sightings: {existing_ind.sighting_count}."
            )
        else:
            # New individual animal discovered!
            new_id = _generate_next_id(species_info["code"])
            cache_path = _save_feature_cache(primary_sig, new_id)

            new_ind = Individual.objects.create(
                custom_id=new_id,
                species=species_info["species"],
                scientific_name=species_info["scientific_name"],
                name=f"{species_info['species']} ({new_id})",
                pattern_type=species_info["pattern_type"],
                primary_image_path=primary_file_info.get("preview", ""),
                primary_preview_url=primary_file_info.get("preview", ""),
                first_location=scan_location,
                last_location=scan_location,
                sighting_count=1,
                feature_cache_path=str(cache_path) if cache_path else "",
                signature_data={
                    "point_count": primary_sig.point_count if primary_sig else 0,
                    "species": species_info["species"],
                    "digest": primary_sig.digest.tolist() if primary_sig is not None else [],
                },
                notes=f"First discovered during scan {scan.id if scan else 'batch'} at {scan_location}.",
            )

            Sighting.objects.create(
                individual=new_ind,
                scan=scan,
                image_path=primary_file_info.get("preview", ""),
                preview_url=primary_file_info.get("preview", ""),
                location=scan_location,
                confidence=100.0,
                is_repeat=False,
                notes="Initial registration sighting.",
            )

            now_str = timezone.now().strftime("%d %b %Y, %I:%M %p")
            ind["database_status"] = "NEW_ANIMAL"
            ind["database_id"] = new_id
            ind["species"] = species_info["species"]
            ind["scientific_name"] = species_info["scientific_name"]
            ind["pattern_type"] = species_info["pattern_type"]
            ind["sighting_count"] = 1
            ind["first_seen"] = now_str
            ind["first_location"] = scan_location
            ind["last_seen"] = now_str
            ind["last_location"] = scan_location
            ind["history_note"] = f"Newly registered individual! Assigned persistent ID {new_id}."


def _find_existing_match(sig, species_code: str):
    """Compare a new signature against all registered animals in database."""
    if sig is None or not sig.views:
        return None

    # Import locally to avoid circular dependencies
    from .engine import _match, _verdict

    individuals = Individual.objects.all()
    best_candidate = None
    best_inliers = 0
    best_conf = 0.0

    for ind in individuals:
        cache_path = ind.feature_cache_path
        if not cache_path or not Path(cache_path).exists():
            continue

        try:
            # Load stored descriptors
            stored = np.load(cache_path)
            stored_desc = stored.get("descriptors")
            stored_pts = stored.get("keypoints")  # Nx2 float32
            if stored_desc is None or stored_pts is None or len(stored_pts) < 8:
                continue

            import cv2
            kps = [cv2.KeyPoint(float(pt[0]), float(pt[1]), 1.0) for pt in stored_pts]
            from .engine import View
            ref_view = View(
                image=np.zeros((10, 10, 3), dtype=np.uint8),
                keypoints=kps,
                descriptors=stored_desc,
                sharpness=50.0,
                tag="ref",
            )

            # Compare against each view of the new signature
            for view in sig.views:
                match_res = _match(view, ref_view)
                inliers = match_res["inliers"]
                ratio = match_res["ratio"]

                # Strong threshold for inter-scan database identity
                if (inliers >= 18 and ratio >= 0.38) or (inliers >= 35 and ratio >= 0.28):
                    if inliers > best_inliers:
                        best_inliers = inliers
                        best_conf = min(99.0, round(60.0 + (inliers * 0.8), 1))
                        best_candidate = (ind, inliers, best_conf)

        except Exception as exc:
            logger.warning("Error reading feature cache for %s: %s", ind.custom_id, exc)

    return best_candidate


def _generate_next_id(prefix: str) -> str:
    """Generate sequential ID, e.g. TIG-001, TIG-002, LEO-001."""
    existing = Individual.objects.filter(custom_id__startswith=f"{prefix}-").values_list("custom_id", flat=True)
    max_num = 0
    for cid in existing:
        try:
            parts = cid.split("-")
            if len(parts) >= 2 and parts[1].isdigit():
                max_num = max(max_num, int(parts[1]))
        except (ValueError, IndexError):
            pass
    return f"{prefix}-{max_num + 1:03d}"


def _save_feature_cache(sig, custom_id: str) -> Path | None:
    """Save descriptor features into .npz for fast cross-scan comparison."""
    if sig is None or not sig.views:
        return None

    try:
        best_view = max(sig.views, key=lambda v: len(v.keypoints) if v.descriptors is not None else 0)
        if best_view.descriptors is None or len(best_view.keypoints) < 8:
            return None

        cache_dir = Path(settings.MEDIA_ROOT) / "features"
        cache_dir.mkdir(parents=True, exist_ok=True)
        out_file = cache_dir / f"{custom_id}.npz"

        pts = np.float32([kp.pt for kp in best_view.keypoints])
        np.savez_compressed(out_file, keypoints=pts, descriptors=best_view.descriptors)
        return out_file
    except Exception as exc:
        logger.warning("Failed to save feature cache for %s: %s", custom_id, exc)
        return None
