"""
Route planning engine with pothole avoidance logic
Integrates with OpenRouteService API for routing calculations
"""

import requests
import os
from typing import Dict, List, Tuple, Optional
from dotenv import load_dotenv
import math

load_dotenv()

# OpenRouteService API configuration
ORS_API_KEY = os.getenv("ORS_API_KEY", "")
ORS_BASE_URL = "https://api.openrouteservice.org/v2"


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance in meters between two GPS points"""
    R = 6371000  # Earth radius in meters
    
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    
    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2)
        * math.sin(d_lambda / 2) ** 2
    )
    
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    
    return R * c


def geocode_address(address: str) -> Optional[Tuple[float, float]]:
    """
    Convert address to GPS coordinates using Nominatim
    
    Args:
        address: Address string
    
    Returns:
        Tuple of (latitude, longitude) or None if not found
    """
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": address,
        "format": "json",
        "limit": 1
    }
    headers = {
        "User-Agent": "Pothole-Detection-System-Routing"
    }
    
    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        data = response.json()
        
        if data and len(data) > 0:
            return float(data[0]["lat"]), float(data[0]["lon"])
        
        return None
    except Exception as e:
        print(f"Geocoding error: {e}")
        return None


def get_route_osrm(start_coords: Tuple[float, float], 
                   end_coords: Tuple[float, float],
                   avoid_points: List[Tuple[float, float]] = None) -> Optional[Dict]:
    """
    Get route from OSRM public API (no API key required)
    
    Args:
        start_coords: (latitude, longitude) of start point
        end_coords: (latitude, longitude) of end point
        avoid_points: List of points to avoid (for alternative routing)
    
    Returns:
        Route data dict with real road geometry
    """
    # OSRM public instance
    base_url = "http://router.project-osrm.org/route/v1/driving"
    
    # OSRM uses lon,lat format
    coordinates = f"{start_coords[1]},{start_coords[0]};{end_coords[1]},{end_coords[0]}"
    
    # Request full geometry and steps
    params = {
        "overview": "full",  # Get full route geometry
        "geometries": "geojson",  # GeoJSON format for coordinates
        "steps": "true",  # Get turn-by-turn instructions
        "annotations": "true"  # Get detailed route info
    }
    
    url = f"{base_url}/{coordinates}"
    
    try:
        response = requests.get(url, params=params, timeout=15)
        
        if response.status_code == 200:
            data = response.json()
            
            if data.get("code") == "Ok" and data.get("routes"):
                route = data["routes"][0]
                
                # Convert to our format
                return {
                    "routes": [{
                        "summary": {
                            "distance": route["distance"],  # meters
                            "duration": route["duration"]   # seconds
                        },
                        "geometry": {
                            "coordinates": route["geometry"]["coordinates"]  # [lon, lat] pairs
                        }
                    }]
                }
        
        print(f"OSRM API error: {response.status_code}")
        return None
        
    except Exception as e:
        print(f"OSRM routing error: {e}")
        return None


def get_route_ors(start_coords: Tuple[float, float], 
                  end_coords: Tuple[float, float],
                  avoid_points: List[Tuple[float, float]] = None) -> Optional[Dict]:
    """
    Get route - tries OSRM first (free, no API key), falls back to ORS if key available
    
    Args:
        start_coords: (latitude, longitude) of start point
        end_coords: (latitude, longitude) of end point
        avoid_points: List of points to avoid (for alternative routing)
    
    Returns:
        Route data dict or None if routing fails
    """
    # Try OSRM first (free, real road routing)
    if not avoid_points:  # OSRM doesn't support avoid areas easily
        osrm_route = get_route_osrm(start_coords, end_coords)
        if osrm_route:
            return osrm_route
    
    # If avoiding points or OSRM failed, try ORS if we have API key
    if ORS_API_KEY and avoid_points:
        url = f"{ORS_BASE_URL}/directions/driving-car"
        
        headers = {
            "Authorization": ORS_API_KEY,
            "Content-Type": "application/json"
        }
        
        # ORS uses [lon, lat] format
        coordinates = [
            [start_coords[1], start_coords[0]],
            [end_coords[1], end_coords[0]]
        ]
        
        body = {
            "coordinates": coordinates
        }
        
        # Add avoid areas
        if avoid_points:
            avoid_polygons = []
            for lat, lon in avoid_points:
                # Create 150m radius avoidance zone
                avoid_polygons.append({
                    "type": "Polygon",
                    "coordinates": [[
                        [lon - 0.0015, lat - 0.0015],
                        [lon + 0.0015, lat - 0.0015],
                        [lon + 0.0015, lat + 0.0015],
                        [lon - 0.0015, lat + 0.0015],
                        [lon - 0.0015, lat - 0.0015]
                    ]]
                })
            
            if avoid_polygons:
                body["options"] = {
                    "avoid_polygons": avoid_polygons[0]
                }
        
        try:
            response = requests.post(url, json=body, headers=headers, timeout=15)
            
            if response.status_code == 200:
                return response.json()
            else:
                print(f"ORS API error: {response.status_code}")
        
        except Exception as e:
            print(f"ORS routing error: {e}")
    
    # If all else fails, use OSRM without avoidance
    return get_route_osrm(start_coords, end_coords)


def check_route_intersects_bad_segments(route_coords: List[List[float]], 
                                        bad_segments: List[Dict],
                                        threshold_meters: float = 50) -> List[Dict]:
    """
    Check if route passes through bad road segments
    
    Args:
        route_coords: List of [lon, lat] coordinates along route
        bad_segments: List of bad road segment dicts
        threshold_meters: Distance threshold to consider intersection
    
    Returns:
        List of bad segments that the route passes through
    """
    intersected_segments = []
    
    for segment in bad_segments:
        segment_center = (segment['center_lat'], segment['center_lon'])
        
        # Check if any route point is close to segment
        for coord in route_coords:
            lon, lat = coord
            distance = haversine_distance(lat, lon, segment_center[0], segment_center[1])
            
            if distance <= threshold_meters:
                intersected_segments.append(segment)
                break  # No need to check more points for this segment
    
    return intersected_segments


def plan_route_with_avoidance(start_coords: Tuple[float, float],
                               end_coords: Tuple[float, float],
                               bad_segments: List[Dict]) -> Dict:
    """
    Plan route and provide alternative if it passes through bad segments
    
    Args:
        start_coords: (latitude, longitude) of start
        end_coords: (latitude, longitude) of end
        bad_segments: List of road segments to avoid
    
    Returns:
        Dict containing original route, alternative route (if needed), and analysis
    """
    # Get original route
    original_route = get_route_ors(start_coords, end_coords)
    
    if not original_route or "routes" not in original_route:
        return {
            "error": "Could not calculate route",
            "original_route": None,
            "alternative_route": None,
            "bad_segments_detected": []
        }
    
    original_route_data = original_route["routes"][0]
    route_coords = original_route_data["geometry"]["coordinates"]
    
    # Check for bad segments
    intersected_segments = check_route_intersects_bad_segments(
        route_coords, bad_segments
    )
    
    result = {
        "start_coords": start_coords,
        "end_coords": end_coords,
        "original_route": {
            "distance_km": original_route_data["summary"]["distance"] / 1000,
            "duration_minutes": original_route_data["summary"]["duration"] / 60,
            "coordinates": route_coords
        },
        "bad_segments_detected": intersected_segments,
        "alternative_route": None,
        "recommendation": None
    }
    
    # If bad segments detected, try to find alternative
    if intersected_segments:
        # Get avoid points (centers of bad segments)
        avoid_points = [
            (seg['center_lat'], seg['center_lon']) 
            for seg in intersected_segments
        ]
        
        # Get alternative route
        alt_route = get_route_ors(start_coords, end_coords, avoid_points)
        
        if alt_route and "routes" in alt_route:
            alt_route_data = alt_route["routes"][0]
            
            result["alternative_route"] = {
                "distance_km": alt_route_data["summary"]["distance"] / 1000,
                "duration_minutes": alt_route_data["summary"]["duration"] / 60,
                "coordinates": alt_route_data["geometry"]["coordinates"]
            }
            
            # Calculate differences
            distance_diff = (result["alternative_route"]["distance_km"] - 
                           result["original_route"]["distance_km"])
            time_diff = (result["alternative_route"]["duration_minutes"] - 
                        result["original_route"]["duration_minutes"])
            
            # Generate recommendation
            result["recommendation"] = generate_recommendation(
                intersected_segments, distance_diff, time_diff
            )
    else:
        result["recommendation"] = {
            "message": "✅ Route is clear! No pothole series detected along this route.",
            "severity": "safe"
        }
    
    return result


def generate_recommendation(bad_segments: List[Dict], 
                           distance_diff_km: float,
                           time_diff_min: float) -> Dict:
    """Generate user-friendly route recommendation"""
    
    # Count potholes and get worst severity
    total_potholes = sum(seg['pothole_count'] for seg in bad_segments)
    severities = [seg['max_severity'] for seg in bad_segments]
    worst_severity = 'High' if 'High' in severities else 'Medium' if 'Medium' in severities else 'Low'
    
    # List affected roads
    roads = list(set(seg['road_name'] for seg in bad_segments))
    
    if len(roads) == 1:
        roads_text = f"{roads[0]} has"
    elif len(roads) == 2:
        roads_text = f"{roads[0]} and {roads[1]} have"
    else:
        roads_text = f"{len(roads)} roads have"
    
    # Build message
    message_parts = [
        f"⚠️ Warning: {roads_text} a series of {total_potholes} potholes ({worst_severity} severity)."
    ]
    
    if distance_diff_km > 0:
        message_parts.append(
            f"Alternative route adds {distance_diff_km:.1f} km "
            f"and ~{time_diff_min:.0f} minutes but avoids damaged sections."
        )
        
        if distance_diff_km < 2 and worst_severity == 'High':
            message_parts.append("💡 Recommended: Take the alternative route for smoother travel.")
            severity = "recommended"
        elif distance_diff_km < 5:
            message_parts.append("💡 Consider the alternative route to avoid road damage.")
            severity = "consider"
        else:
            message_parts.append("⚖️ Significant detour required. Proceed with caution on original route.")
            severity = "caution"
    else:
        message_parts.append("Alternative route could not avoid all bad segments.")
        severity = "caution"
    
    return {
        "message": " ".join(message_parts),
        "severity": severity,
        "affected_roads": roads,
        "total_potholes": total_potholes,
        "worst_severity": worst_severity,
        "detour_distance_km": distance_diff_km,
        "detour_time_min": time_diff_min
    }


def format_route_summary(route_result: Dict) -> str:
    """Format route result as human-readable text"""
    if route_result.get("error"):
        return f"Error: {route_result['error']}"
    
    lines = []
    lines.append("=" * 60)
    lines.append("ROUTE PLANNING RESULT")
    lines.append("=" * 60)
    
    # Original route
    orig = route_result["original_route"]
    lines.append("\n📍 Original Route:")
    lines.append(f"   Distance: {orig['distance_km']:.2f} km")
    lines.append(f"   Duration: {orig['duration_minutes']:.0f} minutes")
    
    # Bad segments
    if route_result["bad_segments_detected"]:
        lines.append(f"\n⚠️ Pothole Series Detected: {len(route_result['bad_segments_detected'])} segments")
        for seg in route_result["bad_segments_detected"]:
            lines.append(f"   • {seg['road_name']}: {seg['pothole_count']} potholes ({seg['max_severity']} severity)")
    
    # Alternative route
    if route_result["alternative_route"]:
        alt = route_result["alternative_route"]
        lines.append("\n🔀 Alternative Route:")
        lines.append(f"   Distance: {alt['distance_km']:.2f} km")
        lines.append(f"   Duration: {alt['duration_minutes']:.0f} minutes")
    
    # Recommendation
    if route_result["recommendation"]:
        lines.append(f"\n{route_result['recommendation']['message']}")
    
    lines.append("\n" + "=" * 60)
    
    return "\n".join(lines)
