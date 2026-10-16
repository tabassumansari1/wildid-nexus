from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("connect/", views.connect, name="connect"),
    path("scans/", views.create_scan, name="create_scan"),
    path("report/<uuid:scan_id>/", views.report, name="report"),
]
