import logging
from typing import Any, Dict, List
from django.utils import timezone
from .models import Scan, Sighting, Individual
from .geo import calculate_displacement

logger = logging.getLogger(__name__)

class ReportGenerator:
    """
    Generates structured analysis reports for wildlife re-identification scans.
    Adheres to Goal G of the Engineering Directive.
    """
    
    @staticmethod
    def generate_scan_report(scan_id: str) -> Dict[str, Any]:
        try:
            scan = Scan.objects.get(id=scan_id)
            assets = scan.assets.all()
            sightings = Sighting.objects.filter(scan=scan).select_related('individual')
            
            # 1. Basic Analysis Info
            report = {
                "analysis_id": str(scan.id),
                "date": scan.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                "status": scan.status,
                "total_files": assets.count(),
                "processed_observations": len(sightings),
                "observations": []
            }
            
            # 2. Process each sighting for detailed reporting
            for sighting in sightings:
                ind = sighting.individual
                
                # Calculate displacement if there is a previous sighting for this animal
                displacement_info = {"distance": "N/A", "speed": "N/A", "elapsed": "N/A"}
                prev_sighting = Sighting.objects.filter(
                    individual=ind
                ).exclude(id=sighting.id).order_by('-sighted_at').first()
                
                if prev_sighting and sighting.latitude and prev_sighting.latitude:
                    geo_res = calculate_displacement(
                        (float(prev_sighting.latitude), float(prev_sighting.longitude)),
                        (float(sighting.latitude), float(sighting.longitude)),
                        prev_sighting.sighted_at,
                        sighting.sighted_at
                    )
                    displacement_info = {
                        "distance": f"{geo_res['distance']} km" if geo_res['distance'] else "N/A",
                        "speed": f"{geo_res['speed']} km/h" if geo_res['speed'] else "N/A",
                        "elapsed": f"{geo_res['elapsed_hours']} hours" if geo_res['elapsed_hours'] else "N/A"
                    }

                obs_detail = {
                    "animal_id": ind.custom_id,
                    "species": ind.species,
                    "scientific_name": ind.scientific_name,
                    "confidence": f"{sighting.confidence}%",
                    "confidence_band": sighting.confidence_band,
                    "verification": sighting.verification_status,
                    "location": sighting.location,
                    "timestamp": sighting.sighted_at.strftime("%Y-%m-%d %H:%M"),
                    "displacement": displacement_info,
                    "notes": sighting.notes
                }
                report["observations"].append(obs_detail)

            # 3. Summary Metrics
            report["summary"] = {
                "new_individuals": Individual.objects.filter(
                    sightings__scan=scan, 
                    first_seen__gte=scan.created_at
                ).count(),
                "matches_found": Individual.objects.filter(
                    sightings__scan=scan
                ).exclude(first_seen__gte=scan.created_at).count(),
                "needs_review": Sighting.objects.filter(
                    scan=scan, 
                    verification_status="pending"
                ).count()
            }
            
            return report
            
        except Scan.DoesNotExist:
            logger.error(f"Scan {scan_id} not found for report generation")
            return {"error": "Scan not found"}
        except Exception as e:
            logger.exception(f"Unexpected error generating report for {scan_id}: {e}")
            return {"error": str(e)}
