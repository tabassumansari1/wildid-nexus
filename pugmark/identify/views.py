import logging
import re
from pathlib import Path

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from .engine import EngineError, analyze
from .models import Scan, ScanAsset

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


@require_POST
def create_scan(request):
    wants_json = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    uploads = request.FILES.getlist("files")
    error = _validate(uploads)
    if error:
        return _fail(request, wants_json, error)

    scan = Scan.objects.create(status="running")
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


def _fail(request, wants_json, message: str, status: int = 400):
    if wants_json:
        return JsonResponse({"ok": False, "error": message}, status=status)
    return render(request, "connect.html", {"error": message}, status=status)


_SAFE = re.compile(r"[^A-Za-z0-9._ -]+")


def _safe_name(name: str) -> str:
    base = Path(name or "").name.replace("\x00", "")
    cleaned = _SAFE.sub("", base).strip(" .")
    return (cleaned or "upload")[:160]
