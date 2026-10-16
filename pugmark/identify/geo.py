import math
import logging
from typing import Tuple, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

def haversine_distance(coord1: Tuple[float, float], coord2: Tuple[float, float]) -> float:
    """
    Calculate the great circle distance between two points 
    on the earth (specified in decimal degrees).
    Returns distance in kilometers.
    """
    # Radius of earth in kilometers.
    R = 6371.0

    lat1, lon1 = map(math.radians, coord1)
    lat2, lon2 = map(math.radians, coord2)

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = math.sin(dlat / 2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c

def calculate_displacement(
    start_coord: Optional[Tuple[float, float]], 
    end_coord: Optional[Tuple[float, float]], 
    start_time: datetime, 
    end_time: datetime
) -> dict:
    """
    Calculates straight-line distance and average displacement speed.
    """
    if not start_coord or not end_coord:
        return {"distance": None, "speed": None, "elapsed_hours": None}

    distance = haversine_distance(start_coord, end_coord)
    
    # Calculate time difference in hours
    delta = end_time - start_time
    elapsed_hours = delta.total_seconds() / 3600.0
    
    speed = None
    if elapsed_hours > 0:
        speed = distance / elapsed_hours

    return {
        "distance": round(distance, 2), 
        "speed": round(speed, 2) if speed else None, 
        "elapsed_hours": round(elapsed_hours, 2)
    }
