// Enhanced Route Planner JavaScript with proper routing and animations

let map;
let potholeMarkers = [];
let badSegmentLayers = [];
let routeLayers = [];
let startMarker = null;
let endMarker = null;
let clickMode = 'none';

// Custom marker icons
const customIcons = {
    start: L.divIcon({
        html: `<svg width="32" height="32" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <circle cx="12" cy="12" r="10" fill="#10b981" stroke="white" stroke-width="2"/>
            <circle cx="12" cy="12" r="4" fill="white"/>
        </svg>`,
        className: 'custom-marker',
        iconSize: [32, 32],
        iconAnchor: [16, 16]
    }),
    end: L.divIcon({
        html: `<svg width="32" height="32" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" fill="#ef4444" stroke="white" stroke-width="2"/>
        </svg>`,
        className: 'custom-marker',
        iconSize: [32, 32],
        iconAnchor: [16, 32]
    })
};

// Initialize on page load
document.addEventListener('DOMContentLoaded', function () {
    initializeMap();
    loadPotholeMarkers();
    setupEventListeners();
    addStylesForMarkers();
});

function addStylesForMarkers() {
    const style = document.createElement('style');
    style.textContent = `
        .custom-marker {
            background: none;
            border: none;
        }
        .custom-marker svg {
            filter: drop-shadow(0 2px 4px rgba(0,0,0,0.3));
        }
        .pothole-marker {
            border-radius: 50%;
            border: 2px solid white;
            box-shadow: 0 2px 8px rgba(0,0,0,0.3);
        }
    `;
    document.head.appendChild(style);
}

function initializeMap() {
    // Initialize map
    map = L.map('map').setView([12.9716, 77.5946], 12);

    // Add OpenStreetMap tiles
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenStreetMap contributors',
        maxZoom: 19
    }).addTo(map);

    // Add click handler
    map.on('click', function (e) {
        if (clickMode === 'start') {
            setStartPoint(e.latlng.lat, e.latlng.lng);
        } else if (clickMode === 'end') {
            setEndPoint(e.latlng.lat, e.latlng.lng);
        }
    });
}

async function loadPotholeMarkers() {
    try {
        const response = await fetch('/api/potholes/locations');
        const data = await response.json();

        // Clear existing markers
        potholeMarkers.forEach(marker => map.removeLayer(marker));
        potholeMarkers = [];

        // Add pothole markers with animation
        data.potholes.forEach((pothole, index) => {
            setTimeout(() => {
                const color = getSeverityColor(pothole.severity);

                const marker = L.circleMarker([pothole.lat, pothole.lon], {
                    radius: 8,
                    fillColor: color,
                    color: '#fff',
                    weight: 2,
                    opacity: 1,
                    fillOpacity: 0.8,
                    className: 'pothole-marker'
                }).addTo(map);

                // Enhanced popup
                const popupContent = `
                    <div class="popup-title">
                        ${getSeverityIcon(pothole.severity)} ${pothole.road}
                    </div>
                    <div class="popup-info"><strong>Severity:</strong> ${pothole.severity}</div>
                    <div class="popup-info"><strong>Area:</strong> ${pothole.area}</div>
                    <div class="popup-info"><strong>Detections:</strong> ${pothole.detections}</div>
                `;
                marker.bindPopup(popupContent);

                potholeMarkers.push(marker);
            }, index * 20); // Staggered animation
        });

        console.log(`Loaded ${data.potholes.length} pothole markers`);

    } catch (error) {
        console.error('Error loading potholes:', error);
    }
}

function getSeverityColor(severity) {
    const colors = {
        'High': '#ef4444',
        'Medium': '#f59e0b',
        'Low': '#3b82f6'
    };
    return colors[severity] || '#6b7280';
}

function getSeverityIcon(severity) {
    const icons = {
        'High': '🔴',
        'Medium': '🟠',
        'Low': '🔵'
    };
    return icons[severity] || '⚪';
}

function setupEventListeners() {
    document.getElementById('plan-route-btn').addEventListener('click', planRoute);
    document.getElementById('clear-btn').addEventListener('click', clearAll);

    const startInput = document.getElementById('start-input');
    const endInput = document.getElementById('end-input');

    startInput.addEventListener('focus', () => {
        clickMode = 'start';
        startInput.placeholder = '📍 Click on map or type address...';
    });

    startInput.addEventListener('blur', () => {
        if (clickMode === 'start') clickMode = 'none';
        startInput.placeholder = 'Enter address or click on map';
    });

    endInput.addEventListener('focus', () => {
        clickMode = 'end';
        endInput.placeholder = '📍 Click on map or type address...';
    });

    endInput.addEventListener('blur', () => {
        if (clickMode === 'end') clickMode = 'none';
        endInput.placeholder = 'Enter address or click on map';
    });
}

function setStartPoint(lat, lon) {
    if (startMarker) {
        map.removeLayer(startMarker);
    }

    startMarker = L.marker([lat, lon], {
        icon: customIcons.start
    }).addTo(map);

    startMarker.bindPopup('<div class="popup-title">🟢 Start Point</div>').openPopup();
    document.getElementById('start-input').value = `${lat.toFixed(5)}, ${lon.toFixed(5)}`;
    clickMode = 'none';
}

function setEndPoint(lat, lon) {
    if (endMarker) {
        map.removeLayer(endMarker);
    }

    endMarker = L.marker([lat, lon], {
        icon: customIcons.end
    }).addTo(map);

    endMarker.bindPopup('<div class="popup-title">🔴 End Point</div>').openPopup();
    document.getElementById('end-input').value = `${lat.toFixed(5)}, ${lon.toFixed(5)}`;
    clickMode = 'none';
}

async function planRoute() {
    const startInput = document.getElementById('start-input').value.trim();
    const endInput = document.getElementById('end-input').value.trim();

    if (!startInput || !endInput) {
        alert('Please enter both start and end locations');
        return;
    }

    showLoading(true);

    let start = parseInput(startInput);
    let end = parseInput(endInput);

    try {
        const response = await fetch('/api/route/plan', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ start, end })
        });

        const result = await response.json();

        if (result.error) {
            alert(`Error: ${result.error}`);
            return;
        }

        // Display routes with animation
        await displayRoute(result);

        // Calculate and display health score
        calculateHealthScore(result);

        // Show results
        displayResults(result);

    } catch (error) {
        console.error('Routing error:', error);
        alert('Failed to calculate route. Please try again.');
    } finally {
        showLoading(false);
    }
}

function parseInput(input) {
    const coordPattern = /^(-?\d+\.?\d*),\s*(-?\d+\.?\d*)$/;
    const match = input.match(coordPattern);

    if (match) {
        return [parseFloat(match[1]), parseFloat(match[2])];
    } else {
        return input;
    }
}

async function displayRoute(result) {
    // Clear previous routes
    routeLayers.forEach(layer => map.removeLayer(layer));
    routeLayers = [];

    badSegmentLayers.forEach(layer => map.removeLayer(layer));
    badSegmentLayers = [];

    // Draw original route with animation
    if (result.original_route && result.original_route.coordinates) {
        const coords = result.original_route.coordinates.map(c => [c[1], c[0]]);

        const originalRoute = L.polyline(coords, {
            color: '#3b82f6',
            weight: 6,
            opacity: 0.8,
            lineJoin: 'round',
            lineCap: 'round',
            dashArray: null
        }).addTo(map);

        // Animate route drawing
        animatePolyline(originalRoute, 1000);

        routeLayers.push(originalRoute);

        // Fit map to route
        map.fitBounds(originalRoute.getBounds(), { padding: [50, 50] });
    }

    // Draw alternative route if available
    if (result.alternative_route && result.alternative_route.coordinates) {
        await new Promise(resolve => setTimeout(resolve, 500)); // Delay for effect

        const coords = result.alternative_route.coordinates.map(c => [c[1], c[0]]);

        const altRoute = L.polyline(coords, {
            color: '#10b981',
            weight: 6,
            opacity: 0.8,
            lineJoin: 'round',
            lineCap: 'round',
            dashArray: '10, 10'
        }).addTo(map);

        animatePolyline(altRoute, 1000);

        routeLayers.push(altRoute);
    }

    // Highlight bad segments with animation
    if (result.bad_segments_detected && result.bad_segments_detected.length > 0) {
        result.bad_segments_detected.forEach((segment, index) => {
            setTimeout(() => {
                // Draw pulsing circle for bad segment
                const circle = L.circle([segment.center_lat, segment.center_lon], {
                    color: '#ef4444',
                    fillColor: '#ef4444',
                    fillOpacity: 0.2,
                    radius: 100,
                    weight: 3,
                    className: 'bad-segment-circle'
                }).addTo(map);

                circle.bindPopup(`
                    <div class="popup-title">⚠️ Bad Road Segment</div>
                    <div class="popup-info"><strong>Road:</strong> ${segment.road_name}</div>
                    <div class="popup-info"><strong>Potholes:</strong> ${segment.pothole_count}</div>
                    <div class="popup-info"><strong>Severity:</strong> ${segment.max_severity}</div>
                `);

                badSegmentLayers.push(circle);
            }, index * 200);
        });
    }
}

function animatePolyline(polyline, duration) {
    const coordinates = polyline.getLatLngs();
    const steps = 50;
    const stepDuration = duration / steps;
    let currentStep = 0;

    // Start with empty coordinates
    polyline.setLatLngs([]);

    const interval = setInterval(() => {
        currentStep++;
        const progress = currentStep / steps;
        const visiblePoints = Math.floor(coordinates.length * progress);

        polyline.setLatLngs(coordinates.slice(0, visiblePoints));

        if (currentStep >= steps) {
            polyline.setLatLngs(coordinates);
            clearInterval(interval);
        }
    }, stepDuration);
}

function calculateHealthScore(result) {
    let score = 100;

    // Deduct points for potholes
    if (result.bad_segments_detected && result.bad_segments_detected.length > 0) {
        result.bad_segments_detected.forEach(segment => {
            const deduction = segment.pothole_count * (
                segment.max_severity === 'High' ? 5 :
                    segment.max_severity === 'Medium' ? 3 : 1
            );
            score -= deduction;
        });
    }

    score = Math.max(0, Math.min(100, score));

    // Show health score with animation
    const scoreContainer = document.getElementById('health-score-container');
    scoreContainer.classList.remove('hidden');

    // Animate score ring
    const scoreRing = document.getElementById('score-ring-progress');
    const circumference = 2 * Math.PI * 50; // radius = 50
    const offset = circumference - (score / 100) * circumference;

    setTimeout(() => {
        scoreRing.style.strokeDashoffset = offset;
    }, 100);

    // Animate counter
    animateValue('health-score', 0, score, 1000);

    // Update description
    const description = document.getElementById('health-description');
    if (score >= 80) {
        description.textContent = '✅ Excellent road condition';
        description.style.color = '#10b981';
    } else if (score >= 60) {
        description.textContent = '⚠️ Moderate road condition';
        description.style.color = '#f59e0b';
    } else {
        description.textContent = '❌ Poor road condition';
        description.style.color = '#ef4444';
    }
}

function animateValue(id, start, end, duration) {
    const element = document.getElementById(id);
    const range = end - start;
    const increment = range / (duration / 16);
    let current = start;

    const timer = setInterval(() => {
        current += increment;
        if ((increment > 0 && current >= end) || (increment < 0 && current <= end)) {
            current = end;
            clearInterval(timer);
        }
        element.textContent = Math.round(current);
    }, 16);
}

function displayResults(result) {
    const resultsSection = document.getElementById('results-section');
    const routeInfo = document.getElementById('route-info');
    const recommendation = document.getElementById('recommendation');

    // Build original route card
    let html = `
        <div class="route-card original" style="animation: slideIn 0.4s ease-out">
            <h3>🔵 Original Route</h3>
            <p><strong>Distance:</strong> ${result.original_route.distance_km.toFixed(2)} km</p>
            <p><strong>Duration:</strong> ${Math.round(result.original_route.duration_minutes)} min</p>
        </div>
    `;

    // Add alternative route if available
    if (result.alternative_route) {
        html += `
            <div class="route-card alternative" style="animation: slideIn 0.4s ease-out 0.2s; animation-fill-mode: backwards;">
                <h3>🟢 Safe Alternative Route</h3>
                <p><strong>Distance:</strong> ${result.alternative_route.distance_km.toFixed(2)} km</p>
                <p><strong>Duration:</strong> ${Math.round(result.alternative_route.duration_minutes)} min</p>
            </div>
        `;
    }

    routeInfo.innerHTML = html;

    // Show potholes avoided counter
    if (result.bad_segments_detected && result.bad_segments_detected.length > 0) {
        const totalPotholes = result.bad_segments_detected.reduce(
            (sum, seg) => sum + seg.pothole_count, 0
        );

        const avoidedContainer = document.getElementById('potholes-avoided');
        avoidedContainer.classList.remove('hidden');
        animateValue('avoided-count', 0, totalPotholes, 1000);

        // Show badge if alternative route chosen
        if (result.alternative_route) {
            const badgeCard = document.getElementById('badge-achievement');
            badgeCard.classList.remove('hidden');
        }
    }

    // Show recommendation
    if (result.recommendation) {
        const rec = result.recommendation;
        const severityClass = rec.severity || 'safe';

        let recommendationHtml = `
            <div class="recommendation-box ${severityClass}">
                <h3>💡 Recommendation</h3>
                <p>${rec.message}</p>
            `;

        if (rec.affected_roads && rec.affected_roads.length > 0) {
            recommendationHtml += `
                <p style="margin-top: 10px;"><strong>Affected roads:</strong></p>
                <ul style="padding-left: 20px; margin-top: 8px;">
            `;
            rec.affected_roads.forEach(road => {
                recommendationHtml += `<li style="margin: 4px 0;">${road}</li>`;
            });
            recommendationHtml += `</ul>`;
        }

        recommendationHtml += `</div>`;
        recommendation.innerHTML = recommendationHtml;
    }

    // Show results section
    resultsSection.classList.remove('hidden');
}

function clearAll() {
    // Clear markers
    if (startMarker) {
        map.removeLayer(startMarker);
        startMarker = null;
    }
    if (endMarker) {
        map.removeLayer(endMarker);
        endMarker = null;
    }

    // Clear routes
    routeLayers.forEach(layer => map.removeLayer(layer));
    routeLayers = [];

    // Clear bad segments
    badSegmentLayers.forEach(layer => map.removeLayer(layer));
    badSegmentLayers = [];

    // Clear inputs
    document.getElementById('start-input').value = '';
    document.getElementById('end-input').value = '';

    // Hide results
    document.getElementById('results-section').classList.add('hidden');
    document.getElementById('health-score-container').classList.add('hidden');
    document.getElementById('potholes-avoided').classList.add('hidden');
    document.getElementById('badge-achievement').classList.add('hidden');

    // Reset map view
    map.setView([12.9716, 77.5946], 12);
}

function showLoading(show) {
    const loading = document.getElementById('loading');
    if (show) {
        loading.classList.remove('hidden');
    } else {
        loading.classList.add('hidden');
    }
}
