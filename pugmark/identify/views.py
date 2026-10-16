import logging
import re
from pathlib import Path

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from .engine import EngineError, analyze
from .models import Individual, Scan, ScanAsset, Sighting
from .registry import process_scan_individuals

logger = logging.getLogger(__name__)

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
VIDEO_EXT = {".mp4", ".mov", ".m4v", ".avi", ".webm", ".mkv"}
MAX_FILES = 12
MAX_FILE_BYTES = 40 * 1024 * 1024
MAX_TOTAL_BYTES = 160 * 1024 * 1024


@require_GET
def home(request):
    return render(request, "home.html")


@require_GET
def connect(request):
    return render(request, "connect.html")


@require_GET
def report(request, scan_id):
    scan = get_object_or_404(Scan, id=scan_id)
    return render(request, "report.html", {"scan": scan, "result": scan.result or {}})


@require_GET
def animal_catalog(request):
    individuals = Individual.objects.all().prefetch_related("sightings")
    return render(request, "catalog.html", {"individuals": individuals})


@require_GET
def animal_detail(request, custom_id):
    individual = get_object_or_404(Individual, custom_id=custom_id)
    sightings = individual.sightings.all().order_by("-sighted_at")
    return render(request, "animal_detail.html", {"individual": individual, "sightings": sightings})


@require_POST
def create_scan(request):
    wants_json = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    uploads = request.FILES.getlist("files")
    error = _validate(uploads)
    if error:
        return _fail(request, wants_json, error)

    location = request.POST.get("location", "").strip() or "Station 1 - Waterhole"
    scan = Scan.objects.create(status="running", location=location)
    upload_dir = Path(settings.MEDIA_ROOT) / "uploads" / str(scan.id)
    upload_dir.mkdir(parents=True, exist_ok=True)
    items = []
    try:
        for upload in uploads:
            asset, path, kind = _store(scan, upload, upload_dir)
            items.append(
                {
                    "id": asset.id.hex[:12],
                    "name": asset.original_name,
                    "path": str(path),
                    "kind": kind,
                }
            )
        out_dir = Path(settings.MEDIA_ROOT) / "reports" / str(scan.id)
        result = analyze(items, out_dir, settings.MEDIA_URL)
        signatures_by_id = result.pop("_signatures_by_id", {})
        process_scan_individuals(scan, result, signatures_by_id, scan_location=location)
    except EngineError as exc:
        return _finish_error(request, wants_json, scan, str(exc))
    except Exception as exc:
        logger.exception("Pugmark scan failed")
        message = "The matcher could not finish this set."
        if settings.DEBUG:
            message = f"{message} ({exc})"
        return _finish_error(request, wants_json, scan, message)

    scan.status = "done"
    scan.result = result
    scan.save(update_fields=["status", "result"])
    report_url = reverse("report", args=[scan.id])
    if wants_json:
        return JsonResponse({"ok": True, "report_url": report_url})
    return redirect(report_url)


def _validate(uploads) -> str:
    if len(uploads) < 2:
        return "Add at least two photos or videos."
    if len(uploads) > MAX_FILES:
        return f"Up to {MAX_FILES} files at a time."
    total = 0
    for upload in uploads:
        ext = Path(upload.name).suffix.lower()
        if ext not in IMAGE_EXT and ext not in VIDEO_EXT:
            return f"{_safe_name(upload.name)} is not a photo or video Pugmark can read."
        if upload.size > MAX_FILE_BYTES:
            return f"{_safe_name(upload.name)} is larger than 40 MB."
        total += upload.size
    if total > MAX_TOTAL_BYTES:
        return "That set is larger than 160 MB. Split it into a smaller batch."
    return ""


def _store(scan: Scan, upload, upload_dir: Path):
    original = _safe_name(upload.name)
    ext = Path(original).suffix.lower()
    kind = "video" if ext in VIDEO_EXT else "image"
    asset = ScanAsset.objects.create(
        scan=scan,
        original_name=original,
        stored_path="",
        kind=kind,
    )
    path = upload_dir / f"{asset.id.hex}{ext}"
    written = 0
    with path.open("wb") as handle:
        for chunk in upload.chunks():
            written += len(chunk)
            if written > MAX_FILE_BYTES:
                path.unlink(missing_ok=True)
                raise EngineError(f"{original} is larger than 40 MB.")
            handle.write(chunk)
    asset.stored_path = str(path)
    asset.save(update_fields=["stored_path"])
    return asset, path, kind


def _finish_error(request, wants_json, scan: Scan, message: str):
    scan.status = "error"
    scan.error = message
    scan.save(update_fields=["status", "error"])
    if wants_json:
        return JsonResponse(
            {"ok": False, "error": message, "report_url": reverse("report", args=[scan.id])},
            status=422,
        )
    return redirect("report", scan.id)


def _fail(request, wants_json, message, status: int = 400):
    if wants_json:
        return JsonResponse({"ok": False, "error": message}, status=status)
    return render(request, "connect.html", {"error": message}, status=status)


_SAFE = re.compile(r"[^A-Za-z0-9._ -]+")


def _safe_name(name: str) -> str:
    base = Path(name or "").name.replace("\x00", "")
    cleaned = _SAFE.sub("", base).strip(" .")
    return (cleaned or "upload")[:160]


@require_GET
def verification_queue(request):
    """List all sightings that need human review."""
    pending = Sighting.objects.filter(
        verification_status="pending"
    ).select_related('individual').order_by('confidence')
    
    return render(request, "verify_queue.html", {"pending": pending})


@require_GET
def verify_sighting(request, sighting_id):
    """Detailed view for a single sighting to be verified."""
    sighting = get_object_or_404(Sighting, id=sighting_id)
    individual = sighting.individual
    
    # Find the best historical sighting for comparison
    comparison = Sighting.objects.filter(
        individual=individual
    ).exclude(id=sighting.id).order_by('-confidence').first()
    
    return render(request, "verify_sighting.html", {
        "sighting": sighting,
        "individual": individual,
        "comparison": comparison,
    })


@require_POST
def submit_verification(request):
    """Process a human verification decision."""
    sighting_id = request.POST.get("sighting_id")
    decision = request.POST.get("decision") # 'confirm', 'reject', 'split'
    reviewer = request.POST.get("reviewer", "Anonymous Expert")
    notes = request.POST.get("notes", "")
    
    sighting = get_object_or_404(Sighting, id=sighting_id)
    
    if decision == "confirm":
        sighting.verification_status = "confirmed"
    elif decision == "reject":
        sighting.verification_status = "rejected"
    elif decision == "split":
        # Create a new identity
        from .registry import _generate_next_id
        
        species_code = sighting.individual.species[:3].upper() if sighting.individual.species else "WLD"
        new_id = _generate_next_id(species_code)
        
        new_ind = Individual.objects.create(
            custom_id=new_id,
            species=sighting.individual.species,
            scientific_name=sighting.individual.scientific_name,
            name=f"{sighting.individual.species} ({new_id})",
            first_location=sighting.location,
            last_location=sighting.location,
            sighting_count=1,
        )
        sighting.individual = new_ind
        sighting.verification_status = "confirmed"
        sighting.notes = f"Split from original identity by human reviewer."

    sighting.reviewed_by = reviewer
    sighting.review_notes = notes
    sighting.save()
    
    return redirect("verification_queue")
