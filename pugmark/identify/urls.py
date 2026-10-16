from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("connect/", views.connect, name="connect"),
    path("scans/", views.create_scan, name="create_scan"),
    path("report/<uuid:scan_id>/", views.report, name="report"),
    path("animals/", views.animal_catalog, name="animal_catalog"),
    path("animals/<str:custom_id>/", views.animal_detail, name="animal_detail"),
    path("verify/queue/", views.verification_queue, name="verification_queue"),
    path("verify/<uuid:sighting_id>/", views.verify_sighting, name="verify_sighting"),
    path("verify/decision/", views.submit_verification, name="submit_verification"),
]
