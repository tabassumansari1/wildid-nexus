from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("connect/", views.connect, name="connect"),
    path("scans/", views.create_scan, name="create_scan"),
    path("report/<uuid:scan_id>/", views.report, name="report"),
    path("animals/", views.animal_catalog, name="animal_catalog"),
    path("animals/<str:custom_id>/", views.animal_detail, name="animal_detail"),
]
