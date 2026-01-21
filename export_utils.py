"""
Export utilities for pothole data - supports JSON, CSV, and OSM XML formats
Includes series detection algorithm for identifying consecutive potholes
"""

import json
import csv
from datetime import datetime
from typing import List, Dict, Tuple
import math
from firebase_admin import firestore


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


def export_to_json(reports: List[Dict], filepath: str = None) -> str:
    """Export pothole reports to JSON format"""
    if filepath is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = f"exports/potholes_{timestamp}.json"
    
    export_data = {
        "export_date": datetime.now().isoformat(),
        "total_reports": len(reports),
        "reports": reports
    }
    
    with open(filepath, 'w') as f:
        json.dump(export_data, f, indent=2)
    
    return filepath


def export_to_csv(reports: List[Dict], filepath: str = None) -> str:
    """Export pothole reports to CSV format"""
    if filepath is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = f"exports/potholes_{timestamp}.csv"
    
    if not reports:
        return filepath
    
    fieldnames = [
        'timestamp', 'latitude', 'longitude', 'severity', 
        'detections', 'road', 'area', 'full_address', 'source'
    ]
    
    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        
        for report in reports:
            # Only write rows with valid GPS coordinates
            if report.get('latitude') and report.get('longitude'):
                writer.writerow(report)
    
    return filepath


def export_to_osm_xml(reports: List[Dict], filepath: str = None) -> str:
    """Export pothole reports to OSM XML format"""
    if filepath is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = f"exports/potholes_{timestamp}.osm"
    
    # OSM XML header
    xml_lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<osm version="0.6" generator="Pothole Detection System">',
    ]
    
    node_id = -1  # Negative IDs for new nodes (OSM convention)
    
    for report in reports:
        lat = report.get('latitude')
        lon = report.get('longitude')
        
        # Skip reports without GPS coordinates or non-pothole detections
        if not lat or not lon or report.get('severity') == 'None':
            continue
        
        try:
            lat = float(lat)
            lon = float(lon)
        except (ValueError, TypeError):
            continue
        
        severity = report.get('severity', 'Unknown').lower()
        timestamp = report.get('timestamp', datetime.now().isoformat())
        road = report.get('road', 'Unknown Road')
        detections = report.get('detections', 0)
        
        # Create OSM node
        xml_lines.append(f'  <node id="{node_id}" lat="{lat}" lon="{lon}" version="1">')
        xml_lines.append(f'    <tag k="highway" v="road_damage"/>')
        xml_lines.append(f'    <tag k="pothole" v="yes"/>')
        xml_lines.append(f'    <tag k="severity" v="{severity}"/>')
        xml_lines.append(f'    <tag k="detections" v="{detections}"/>')
        xml_lines.append(f'    <tag k="timestamp" v="{timestamp}"/>')
        xml_lines.append(f'    <tag k="road" v="{road}"/>')
        xml_lines.append(f'  </node>')
        
        node_id -= 1
    
    xml_lines.append('</osm>')
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write('\n'.join(xml_lines))
    
    return filepath


def detect_pothole_series(reports: List[Dict], 
                          distance_threshold: float = 200, 
                          min_potholes: int = 3) -> List[Dict]:
    """
    Detect series of potholes on the same road segment
    
    Args:
        reports: List of pothole reports with GPS and road info
        distance_threshold: Maximum distance (meters) between consecutive potholes
        min_potholes: Minimum number of potholes to constitute a series
    
    Returns:
        List of road segments with pothole series
    """
    # Filter valid pothole reports (exclude "None" severity and missing GPS)
    valid_reports = []
    for report in reports:
        if report.get('severity') == 'None':
            continue
        
        lat = report.get('latitude')
        lon = report.get('longitude')
        
        if not lat or not lon:
            continue
        
        try:
            lat = float(lat)
            lon = float(lon)
            report['lat_float'] = lat
            report['lon_float'] = lon
            valid_reports.append(report)
        except (ValueError, TypeError):
            continue
    
    # Group by road name
    road_groups = {}
    for report in valid_reports:
        road = report.get('road', 'Unknown Road')
        if road not in road_groups:
            road_groups[road] = []
        road_groups[road].append(report)
    
    # Detect series within each road group
    series_segments = []
    
    for road_name, road_reports in road_groups.items():
        if len(road_reports) < min_potholes:
            continue
        
        # Sort by latitude (approximation for road order)
        road_reports.sort(key=lambda r: (r['lat_float'], r['lon_float']))
        
        # Find consecutive potholes within threshold distance
        current_series = [road_reports[0]]
        
        for i in range(1, len(road_reports)):
            prev_report = current_series[-1]
            curr_report = road_reports[i]
            
            distance = haversine_distance(
                prev_report['lat_float'], prev_report['lon_float'],
                curr_report['lat_float'], curr_report['lon_float']
            )
            
            if distance <= distance_threshold:
                # Add to current series
                current_series.append(curr_report)
            else:
                # Check if current series qualifies
                if len(current_series) >= min_potholes:
                    series_segments.append(create_segment(current_series, road_name))
                
                # Start new series
                current_series = [curr_report]
        
        # Check final series
        if len(current_series) >= min_potholes:
            series_segments.append(create_segment(current_series, road_name))
    
    return series_segments


def create_segment(potholes: List[Dict], road_name: str) -> Dict:
    """Create a road segment object from a series of potholes"""
    # Calculate max severity
    severity_order = {'Low': 1, 'Medium': 2, 'High': 3}
    max_severity = max(
        potholes, 
        key=lambda p: severity_order.get(p.get('severity', 'Low'), 0)
    )['severity']
    
    # Get start and end points
    start_pothole = potholes[0]
    end_pothole = potholes[-1]
    
    # Calculate center point for segment
    avg_lat = sum(p['lat_float'] for p in potholes) / len(potholes)
    avg_lon = sum(p['lon_float'] for p in potholes) / len(potholes)
    
    segment = {
        'segment_id': f"{road_name.replace(' ', '_')}_{round(avg_lat, 5)}_{round(avg_lon, 5)}",
        'road_name': road_name,
        'start_lat': start_pothole['lat_float'],
        'start_lon': start_pothole['lon_float'],
        'end_lat': end_pothole['lat_float'],
        'end_lon': end_pothole['lon_float'],
        'center_lat': avg_lat,
        'center_lon': avg_lon,
        'pothole_count': len(potholes),
        'max_severity': max_severity,
        'area': potholes[0].get('area', 'Unknown'),
        'pothole_ids': [p.get('id', '') for p in potholes],
        'created_at': datetime.now().isoformat()
    }
    
    return segment


def update_bad_segments_in_firestore(db, segments: List[Dict]) -> int:
    """
    Update the bad_road_segments collection in Firestore
    
    Args:
        db: Firestore client
        segments: List of road segments with pothole series
    
    Returns:
        Number of segments updated
    """
    collection_ref = db.collection('bad_road_segments')
    
    # Clear existing segments
    batch = db.batch()
    for doc in collection_ref.stream():
        batch.delete(doc.reference)
    batch.commit()
    
    # Add new segments
    count = 0
    for segment in segments:
        collection_ref.document(segment['segment_id']).set(segment)
        count += 1
    
    return count


def get_export_statistics(reports: List[Dict], segments: List[Dict]) -> Dict:
    """Generate statistics about potholes and bad segments"""
    total_reports = len(reports)
    
    severity_counts = {'High': 0, 'Medium': 0, 'Low': 0, 'None': 0}
    for report in reports:
        severity = report.get('severity', 'None')
        severity_counts[severity] = severity_counts.get(severity, 0) + 1
    
    pothole_reports = total_reports - severity_counts['None']
    
    roads_with_series = len(set(seg['road_name'] for seg in segments))
    total_potholes_in_series = sum(seg['pothole_count'] for seg in segments)
    
    stats = {
        'total_reports': total_reports,
        'pothole_detections': pothole_reports,
        'no_pothole_detections': severity_counts['None'],
        'severity_breakdown': severity_counts,
        'bad_road_segments': len(segments),
        'roads_with_series': roads_with_series,
        'potholes_in_series': total_potholes_in_series,
        'isolated_potholes': pothole_reports - total_potholes_in_series
    }
    
    return stats
