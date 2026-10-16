import uuid

from django.db import models


class Scan(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    status = models.CharField(max_length=16, default="running")
    location = models.CharField(max_length=200, blank=True, default="Station 1 - Waterhole")
    error = models.TextField(blank=True)
    result = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.created_at:%Y-%m-%d %H:%M} · {self.status} ({self.location})"


class ScanAsset(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    scan = models.ForeignKey(Scan, related_name="assets", on_delete=models.CASCADE)
    original_name = models.CharField(max_length=180)
    stored_path = models.CharField(max_length=400)
    kind = models.CharField(max_length=16)

    def __str__(self) -> str:
        return self.original_name


class Individual(models.Model):
    custom_id = models.CharField(max_length=32, unique=True, db_index=True)
    species = models.CharField(max_length=100, default="Wild Animal")
    scientific_name = models.CharField(max_length=100, blank=True)
    name = models.CharField(max_length=120, blank=True)
    pattern_type = models.CharField(max_length=100, blank=True)
    primary_image_path = models.CharField(max_length=400, blank=True)
    primary_preview_url = models.CharField(max_length=400, blank=True)
    first_seen = models.DateTimeField(auto_now_add=True)
    first_location = models.CharField(max_length=200, default="Station 1 - Waterhole")
    last_seen = models.DateTimeField(auto_now=True)
    last_location = models.CharField(max_length=200, default="Station 1 - Waterhole")
    sighting_count = models.IntegerField(default=1)
    signature_data = models.JSONField(null=True, blank=True)
    feature_cache_path = models.CharField(max_length=400, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-last_seen"]

    def __str__(self) -> str:
        return f"{self.custom_id} · {self.species} ({self.sighting_count} sightings)"


class Sighting(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    individual = models.ForeignKey(Individual, related_name="sightings", on_delete=models.CASCADE)
    scan = models.ForeignKey(Scan, related_name="sightings", on_delete=models.SET_NULL, null=True, blank=True)
    image_path = models.CharField(max_length=400, blank=True)
    preview_url = models.CharField(max_length=400, blank=True)
    location = models.CharField(max_length=200, default="Station 1 - Waterhole")
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    sighted_at = models.DateTimeField(auto_now_add=True)
    confidence = models.FloatField(default=100.0)
    confidence_band = models.CharField(
        max_length=16, 
        choices=[("high", "High"), ("medium", "Medium"), ("low", "Low")], 
        default="medium"
    )
    verification_status = models.CharField(
        max_length=16, 
        choices=[("pending", "Pending"), ("confirmed", "Confirmed"), ("rejected", "Rejected")], 
        default="pending"
    )
    reviewed_by = models.CharField(max_length=100, blank=True)
    review_notes = models.TextField(blank=True)
    is_repeat = models.BooleanField(default=False)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-sighted_at"]


    def __str__(self) -> str:
        return f"{self.individual.custom_id} @ {self.location} on {self.sighted_at:%Y-%m-%d %H:%M}"
