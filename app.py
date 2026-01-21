from flask import Flask, render_template, request, jsonify
import os
from datetime import datetime
from ultralytics import YOLO
import firebase_admin
from dotenv import load_dotenv
load_dotenv()
from firebase_admin import credentials, firestore
import requests
from flask import redirect, url_for
import export_utils
import route_planner


app = Flask(__name__)
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER")


# ------------------ CONFIG ------------------

UPLOAD_FOLDER = "/tmp/uploads"
# Use YOLOv8 Nano for minimal memory footprint (will auto-download if not present)
MODEL_PATH = "yolov8n.pt"  # Smallest YOLO model (~6MB vs your custom model)
CLUSTER_RADIUS_METERS = 100

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ------------------ MODEL ------------------

# Load YOLO model once with explicit memory optimization
import torch
torch.set_num_threads(1)  # Limit CPU threads to reduce memory
model = YOLO(MODEL_PATH)
model.overrides['verbose'] = False  # Reduce logging overhead

# ------------------ FIREBASE ------------------

# Initialize Firebase Admin SDK (ONCE)
import json

# Initialize Firebase Admin SDK (ONCE)
firebase_cred_env = os.getenv("FIREBASE_CREDENTIALS")
if firebase_cred_env:
    # Production: Load from environment variable (JSON string)
    cred_dict = json.loads(firebase_cred_env)
    cred = credentials.Certificate(cred_dict)
else:
    # Local: Load from file
    cred = credentials.Certificate("firebase_key.json")
    
firebase_admin.initialize_app(cred)
db = firestore.client()

# ------------------ UTILITIES ------------------

def process_pothole_image(image_path, latitude=None, longitude=None, source="web"):
    print(f"[{source.upper()}] Processing image: {image_path} | Lat: {latitude} | Lon: {longitude}")
    
    # --------- YOLO inference ---------
    try:
        results = model(image_path)
        detections = len(results[0].boxes) if results and results[0].boxes is not None else 0
    except Exception as e:
        print(f"[{source.upper()}] Model inference error: {e}")
        detections = 0

    # --------- Severity logic ---------
    if detections == 0:
        severity = "None"
        status = "No Pothole Detected"
    elif detections == 1:
        severity = "Low"
        status = "Pothole Detected"
    elif detections == 2:
        severity = "Medium"
        status = "Pothole Detected"
    else:
        severity = "High"
        status = "Pothole Detected"

    # --------- Location handling ---------
    road = area = full_address = None

    if latitude and longitude:
        try:
            latitude = float(latitude)
            longitude = float(longitude)
            road, area, full_address = get_address(latitude, longitude)
        except (ValueError, TypeError) as e:
            print(f"[{source.upper()}] Location conversion error: {e}")
            latitude = longitude = None

    # --------- Save to Firestore ---------
    try:
        report = {
            "image_path": image_path,
            "filename": os.path.basename(image_path) if image_path else "No Image",
            "detections": detections,
            "severity": severity,
            "status": status,
            "latitude": latitude,
            "longitude": longitude,
            "road": road,
            "area": area,
            "full_address": full_address,
            "source": source,  # web / whatsapp
            "timestamp": datetime.now().isoformat()
        }

        db.collection("pothole_reports").add(report)
        print(f"[{source.upper()}] Report saved successfully: {report}")
        
    except Exception as e:
        print(f"[{source.upper()}] Firestore save error: {e}")

    return detections, severity, status, road, area, full_address



# 🌍 Reverse Geocoding Function
def get_address(latitude, longitude):
    try:
        url = "https://nominatim.openstreetmap.org/reverse"
        params = {
            "lat": latitude,
            "lon": longitude,
            "format": "json"
        }
        headers = {
            "User-Agent": "Pothole-Detection-System"
        }

        response = requests.get(
            url, params=params, headers=headers, timeout=5
        )
        data = response.json()

        address = data.get("address", {})

        road = address.get("road", "Unknown Road")
        area = (
            address.get("suburb")
            or address.get("neighbourhood")
            or address.get("city")
            or "Unknown Area"
        )
        full_address = data.get("display_name", "Address not found")

        return road, area, full_address

    except Exception as e:
        print("Reverse geocoding error:", e)
        return "Unknown Road", "Unknown Area", "Address not found"

import math

def haversine_distance(lat1, lon1, lat2, lon2):
    """
    Returns distance in meters between two GPS points
    """
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

def cluster_potholes(reports):
    clusters = []
    visited = set()

    for i, report in enumerate(reports):
        # Skip non-potholes
        if report.get("severity") == "None":
            continue

        # Safely read coordinates
        lat_raw = report.get("latitude")
        lon_raw = report.get("longitude")

        try:
            lat1 = float(lat_raw)
            lon1 = float(lon_raw)
        except (TypeError, ValueError):
            continue

        if i in visited:
            continue

        cluster_id = f"{round(lat1,5)}_{round(lon1,5)}"

        cluster = {
            "id": cluster_id,
            "center_lat": lat1,
            "center_lon": lon1,
            "reports": [report],
            "max_severity": report.get("severity")
        }


        visited.add(i)

        for j, other in enumerate(reports):
            if j in visited:
                continue

            if other.get("severity") == "None":
                continue

            lat2_raw = other.get("latitude")
            lon2_raw = other.get("longitude")

            try:
                lat2 = float(lat2_raw)
                lon2 = float(lon2_raw)
            except (TypeError, ValueError):
                continue

            distance = haversine_distance(lat1, lon1, lat2, lon2)

            if distance <= CLUSTER_RADIUS_METERS:
                cluster["reports"].append(other)
                visited.add(j)

                # Escalate cluster severity
                if other.get("severity") == "High":
                    cluster["max_severity"] = "High"
                elif (
                    other.get("severity") == "Medium"
                    and cluster["max_severity"] != "High"
                ):
                    cluster["max_severity"] = "Medium"

        clusters.append(cluster)

    return clusters





# ------------------ ROUTES ------------------

@app.route("/")
def home():
    return render_template("index.html")


@app.route("/admin")
def admin_dashboard():
    print("[ADMIN] Fetching dashboard data...")
    try:
        reports_ref = (
            db.collection("pothole_reports")
            .order_by("timestamp", direction=firestore.Query.DESCENDING)
        )

        reports = []

        summary = {
            "total": 0,
            "high": 0,
            "medium": 0,
            "low": 0,
            "none": 0
        }

        # 1️⃣ Load reports
        for doc in reports_ref.stream():
            data = doc.to_dict()
            data["id"] = doc.id
            # Ensure filename exists for display
            if "filename" not in data:
                if data.get("image_path"):
                    try:
                        data["filename"] = os.path.basename(data["image_path"])
                    except Exception:
                        data["filename"] = "Invalid Path"
                else:
                    data["filename"] = "No Image"
            
            reports.append(data)

            summary["total"] += 1

            if data.get("severity") == "High":
                summary["high"] += 1
            elif data.get("severity") == "Medium":
                summary["medium"] += 1
            elif data.get("severity") == "Low":
                summary["low"] += 1
            else:
                summary["none"] += 1

        # 2️⃣ Build clusters
        clusters = cluster_potholes(reports)

        # 3️⃣ Enhance clusters (Names & Bounds)
        from collections import Counter
        
        for c in clusters:
            doc = db.collection("cluster_status").document(c["id"]).get()
            if doc.exists:
                c["status"] = doc.to_dict().get("status", "Open")
            else:
                c["status"] = "Open"
            
            # --- Name Generation ---
            report_list = c["reports"]
            areas = [r.get("area") for r in report_list if r.get("area") and r.get("area") != "Unknown Area"]
            roads = [r.get("road") for r in report_list if r.get("road") and r.get("road") != "Unknown Road"]
            
            dom_area = Counter(areas).most_common(1)[0][0] if areas else "Unknown Area"
            dom_road = Counter(roads).most_common(1)[0][0] if roads else "Unknown Road"
            
            if dom_road == "Unknown Road" and dom_area == "Unknown Area":
                c["friendly_name"] = f"Cluster #{c['id'].split('_')[0]}"
            else:
                c["friendly_name"] = f"{dom_area} – {dom_road}"
            
            # --- Bounds Calculation ---
            lats = [float(r["latitude"]) for r in report_list if r.get("latitude")]
            lons = [float(r["longitude"]) for r in report_list if r.get("longitude")]
            
            if lats and lons:
                c["bounds"] = [
                    [min(lats), min(lons)],
                    [max(lats), max(lons)]
                ]
            else:
                c["bounds"] = [[c["center_lat"], c["center_lon"]], [c["center_lat"], c["center_lon"]]]

        # 4️⃣ Render admin dashboard
        print(f"[ADMIN] Loaded {len(reports)} reports.")
        return render_template(
            "admin.html",
            reports=reports,
            summary=summary,
            clusters=clusters
        )
    except Exception as e:
        print(f"[ADMIN] Error viewing dashboard: {e}")
        return f"Admin Dashboard Error: {e}", 500

@app.route("/whatsapp", methods=["POST"])
def whatsapp_webhook():
    print("[WHATSAPP] Webhook received")
    
    from_number = request.form.get("From")
    media_url = request.form.get("MediaUrl0")
    latitude = request.form.get("Latitude")
    longitude = request.form.get("Longitude")
    
    print(f"[WHATSAPP] From: {from_number}, Media: {bool(media_url)}, Lat: {latitude}, Lon: {longitude}")
    
    if not from_number:
        return "Invalid request", 400

    # Reference to pending report
    doc_ref = db.collection("pending_reports").document(from_number)
    doc = doc_ref.get()
    
    pending_data = doc.to_dict() if doc.exists else {}
    print(f"[WHATSAPP] Pending Data before update: {pending_data}")
    
    # Update pending data with new info
    if media_url:
        print(f"[WHATSAPP] Downloading image from {media_url}")
        # Download image immediately
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"uploads/whatsapp_{timestamp}.jpg"
        
        try:
            response = requests.get(
                media_url,
                auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
            )
            if response.status_code == 200:
                with open(filename, "wb") as f:
                    f.write(response.content)
                pending_data["image_path"] = filename
                print(f"[WHATSAPP] Image saved to {filename}")
            else:
                 print(f"[WHATSAPP] Failed to download image: {response.status_code}")
                 return "Failed to download image", 400
        except Exception as e:
            print(f"Error downloading image: {e}")
            return "Server error downloading image", 500

    if latitude and longitude:
        pending_data["latitude"] = latitude
        pending_data["longitude"] = longitude

    # Check if we have both pieces of information
    has_image = "image_path" in pending_data
    has_location = "latitude" in pending_data and "longitude" in pending_data
    
    print(f"[WHATSAPP] State - Has Image: {has_image}, Has Location: {has_location}")

    if has_image and has_location:
        print("[WHATSAPP] Processing complete report...")
        # PROCESS REPORT
        detections, severity, status, road, area, full_address = process_pothole_image(
            image_path=pending_data["image_path"],
            latitude=pending_data["latitude"],
            longitude=pending_data["longitude"],
            source="whatsapp"
        )
        
        # CLEAR PENDING STATE
        doc_ref.delete()
        print("[WHATSAPP] Report processed and pending state cleared.")
        
        return (
            f"✅ Report received!\n"
            f"📍 Location: {road or 'Unknown Road'}, {area or 'Unknown Area'}\n"
            f"⚠ Severity: {severity}\n"
            f"📊 Detections: {detections}\n",
            200
        )
    
    # Save partial state back to Firestore
    doc_ref.set(pending_data)
    print("[WHATSAPP] Partial state saved.")
    
    if has_image and not has_location:
         return "📷 Image received! Please share location to complete report.", 200
         
    if has_location and not has_image:
         return "📍 Location received! Please send the pothole image.", 200

    return "Message received.", 200



@app.route("/admin/cluster/update", methods=["POST"])
def update_cluster_status():
    cluster_id = request.form.get("cluster_id")
    status = request.form.get("status")

    if status not in ["Open", "In Progress", "Fixed"]:
        return "Invalid status", 400

    db.collection("cluster_status").document(cluster_id).set({
        "status": status,
        "updated_at": datetime.now().isoformat()
    })

    return redirect(url_for("admin_dashboard"))




@app.route("/upload", methods=["POST"])
def upload():
    # --------- File validation ---------
    if "image" not in request.files:
        return "No file part"

    file = request.files["image"]

    if file.filename == "":
        return "No selected file"

    # --------- Save file ---------
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp}_{file.filename}"
    file_path = os.path.join(UPLOAD_FOLDER, filename)
    file.save(file_path)

    # --------- Location from browser ---------
    latitude = request.form.get("latitude")
    longitude = request.form.get("longitude")

    # --------- Shared processing logic ---------
    detections, severity, status, road, area, full_address = process_pothole_image(
        image_path=file_path,
        latitude=latitude,
        longitude=longitude,
        source="web"
    )

    # --------- Result page ---------
    return render_template(
        "result.html",
        filename=filename,
        detections=detections,
        severity=severity,
        status=status,
        road=road,
        area=area,
        full_address=full_address
    )


# ------------------ NEW ROUTES: EXPORT & ROUTING ------------------

@app.route("/api/export/potholes")
def export_potholes():
    """Export pothole data in various formats"""
    format_type = request.args.get("format", "json").lower()
    
    # Fetch all reports from Firestore
    reports_ref = db.collection("pothole_reports")
    reports = []
    
    for doc in reports_ref.stream():
        data = doc.to_dict()
        data["id"] = doc.id
        reports.append(data)
    
    # Ensure exports directory exists
    os.makedirs("exports", exist_ok=True)
    
    try:
        if format_type == "json":
            filepath = export_utils.export_to_json(reports)
            
            with open(filepath, 'r') as f:
                data = f.read()
            
            return data, 200, {'Content-Type': 'application/json'}
        
        elif format_type == "csv":
            filepath = export_utils.export_to_csv(reports)
            
            with open(filepath, 'r', encoding='utf-8') as f:
                data = f.read()
            
            return data, 200, {
                'Content-Type': 'text/csv',
                'Content-Disposition': f'attachment; filename="{os.path.basename(filepath)}"'
            }
        
        elif format_type == "osm":
            filepath = export_utils.export_to_osm_xml(reports)
            
            with open(filepath, 'r', encoding='utf-8') as f:
                data = f.read()
            
            return data, 200, {
                'Content-Type': 'application/xml',
                'Content-Disposition': f'attachment; filename="{os.path.basename(filepath)}"'
            }
        
        else:
            return jsonify({"error": "Invalid format. Use json, csv, or osm"}), 400
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/bad-segments")
def get_bad_segments():
    """Get list of road segments with pothole series"""
    
    # Fetch all reports
    reports_ref = db.collection("pothole_reports")
    reports = []
    
    for doc in reports_ref.stream():
        data = doc.to_dict()
        data["id"] = doc.id
        reports.append(data)
    
    # Detect series
    segments = export_utils.detect_pothole_series(reports)
    
    # Update Firestore with bad segments
    export_utils.update_bad_segments_in_firestore(db, segments)
    
    # Get statistics
    stats = export_utils.get_export_statistics(reports, segments)
    
    return jsonify({
        "bad_segments": segments,
        "statistics": stats,
        "total_segments": len(segments)
    })


@app.route("/api/bad-segments/refresh", methods=["POST"])
def refresh_bad_segments():
    """Manually refresh bad segments detection"""
    
    # Fetch all reports
    reports_ref = db.collection("pothole_reports")
    reports = []
    
    for doc in reports_ref.stream():
        data = doc.to_dict()
        data["id"] = doc.id
        reports.append(data)
    
    # Detect series
    segments = export_utils.detect_pothole_series(reports)
    
    # Update Firestore
    count = export_utils.update_bad_segments_in_firestore(db, segments)
    
    return jsonify({
        "message": f"Refreshed {count} bad road segments",
        "segments_count": count
    })


@app.route("/route-planner")
def route_planner_page():
    """Route planning interface"""
    return render_template("route_planner.html")


@app.route("/api/route/plan", methods=["POST"])
def plan_route():
    """Calculate route with pothole avoidance"""
    data = request.get_json()
    
    start = data.get("start")  # Can be address or [lat, lon]
    end = data.get("end")      # Can be address or [lat, lon]
    
    if not start or not end:
        return jsonify({"error": "Start and end locations required"}), 400
    
    # Convert addresses to coordinates if needed
    if isinstance(start, str):
        start_coords = route_planner.geocode_address(start)
        if not start_coords:
            return jsonify({"error": f"Could not geocode start address: {start}"}), 400
    else:
        start_coords = tuple(start)  # [lat, lon]
    
    if isinstance(end, str):
        end_coords = route_planner.geocode_address(end)
        if not end_coords:
            return jsonify({"error": f"Could not geocode end address: {end}"}), 400
    else:
        end_coords = tuple(end)  # [lat, lon]
    
    # Fetch bad segments from Firestore
    bad_segments_ref = db.collection("bad_road_segments")
    bad_segments = []
    
    for doc in bad_segments_ref.stream():
        seg_data = doc.to_dict()
        bad_segments.append(seg_data)
    
    # If no bad segments in DB, detect them now
    if not bad_segments:
        reports_ref = db.collection("pothole_reports")
        reports = []
        
        for doc in reports_ref.stream():
            data = doc.to_dict()
            data["id"] = doc.id
            reports.append(data)
        
        bad_segments = export_utils.detect_pothole_series(reports)
        export_utils.update_bad_segments_in_firestore(db, bad_segments)
    
    # Plan route
    result = route_planner.plan_route_with_avoidance(
        start_coords, end_coords, bad_segments
    )
    
    return jsonify(result)


@app.route("/api/potholes/locations")
def get_pothole_locations():
    """Get all pothole locations for map display"""
    reports_ref = db.collection("pothole_reports")
    potholes = []
    
    for doc in reports_ref.stream():
        data = doc.to_dict()
        
        # Only include reports with valid GPS and actual potholes
        if (data.get("latitude") and data.get("longitude") and 
            data.get("severity") != "None"):
            
            try:
                potholes.append({
                    "id": doc.id,
                    "lat": float(data["latitude"]),
                    "lon": float(data["longitude"]),
                    "severity": data.get("severity", "Unknown"),
                    "road": data.get("road", "Unknown Road"),
                    "area": data.get("area", "Unknown Area"),
                    "detections": data.get("detections", 0),
                    "timestamp": data.get("timestamp", "")
                })
            except (ValueError, TypeError):
                continue
    
    return jsonify({
        "potholes": potholes,
        "total": len(potholes)
    })


@app.route("/api/admin/add-pothole", methods=["POST"])
def admin_add_pothole():
    """Manually add a pothole report from the admin dashboard"""
    try:
        data = request.get_json()
        
        latitude = data.get("latitude")
        longitude = data.get("longitude")
        severity = data.get("severity")
        notes = data.get("notes", "")
        
        if not latitude or not longitude or not severity:
            return jsonify({"success": False, "error": "Missing required fields"}), 400
            
        # Get address from coordinates
        road, area, full_address = get_address(latitude, longitude)
        
        # Override road if provided manually and not just "Unknown"
        if data.get("road") and data.get("road").strip():
            road = data.get("road").strip()
            
        report = {
            "image_path": None, # No image for manual map adds
            "detections": 1 if severity == "Low" else 2 if severity == "Medium" else 3,
            "severity": severity,
            "status": "Pothole Detected",
            "latitude": float(latitude),
            "longitude": float(longitude),
            "road": road,
            "area": area,
            "full_address": full_address,
            "notes": notes,
            "source": "admin_manual",
            "timestamp": datetime.now().isoformat()
        }
        
        # Save to database
        db.collection("pothole_reports").add(report)
        
        # Also trigger a refresh of bad segments since we added a pothole
        # This can be async in a real app, but we'll do it here for correctness
        all_reports_stream = db.collection("pothole_reports").stream()
        all_reports_data = [d.to_dict() for d in all_reports_stream]
        new_segments = export_utils.detect_pothole_series(all_reports_data)
        export_utils.update_bad_segments_in_firestore(db, new_segments)
        
        return jsonify({"success": True, "message": "Pothole added successfully!"})
        
    except Exception as e:
        print(f"Error adding pothole: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# ------------------ MAIN ------------------

if __name__ == "__main__":
    app.run(debug=True)