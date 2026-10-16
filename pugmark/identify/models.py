import uuid

from django.db import models


class Scan(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    status = models.CharField(max_length=16, default="running")
    error = models.TextField(blank=True)
    result = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.created_at:%Y-%m-%d %H:%M} · {self.status}"


class ScanAsset(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    scan = models.ForeignKey(Scan, related_name="assets", on_delete=models.CASCADE)
    original_name = models.CharField(max_length=180)
    stored_path = models.CharField(max_length=400)
    kind = models.CharField(max_length=16)

    def __str__(self) -> str:
        return self.original_name
