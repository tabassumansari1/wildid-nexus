from django.contrib import admin

from .models import Scan, ScanAsset

admin.site.site_header = "Pugmark"
admin.site.site_title = "Pugmark"
admin.site.index_title = "Field scans"


class ScanAssetInline(admin.TabularInline):
    model = ScanAsset
    extra = 0


@admin.register(Scan)
class ScanAdmin(admin.ModelAdmin):
    list_display = ("id", "status", "created_at")
    inlines = [ScanAssetInline]
