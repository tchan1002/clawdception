"""
Media Luna Sensor Server
Flask endpoint that receives ESP32 sensor data via HTTP POST and stores in SQLite.
Run on laptop (weeks 1-4), migrate to Pi later.

Usage:
    pip install flask
    python sensor_server.py

Then ESP32 POSTs to http://<your-laptop-ip>:5000/api/sensors
"""

import sqlite3
import json
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, send_file, render_template_string

app = Flask(__name__)
DB_PATH = "media_luna.db"


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sensor_readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            temp_c REAL,
            temp_f REAL,
            ph REAL,
            tds_ppm REAL,
            source TEXT DEFAULT 'esp32',
            raw_json TEXT
        )
    """)
    # Legacy table — kept for backward compatibility
    conn.execute("""
        CREATE TABLE IF NOT EXISTS manual_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            event_type TEXT NOT NULL,
            notes TEXT
        )
    """)
    # Add data column to manual_events if it doesn't exist
    try:
        conn.execute("ALTER TABLE manual_events ADD COLUMN data TEXT DEFAULT '{}'")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # column already exists
    # New structured events table used by agent skills
    conn.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            event_type TEXT NOT NULL,
            data_json TEXT,
            source TEXT DEFAULT 'manual'
        )
    """)
    conn.commit()
    conn.close()
    print("[init] Database ready.")


# --- Serve dashboard ---
@app.route("/")
def dashboard():
    return send_file("media_luna_dashboard.html")


# --- ESP32 posts sensor data here ---
@app.route("/api/sensors", methods=["POST"])
def receive_sensors():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No JSON received"}), 400

    timestamp = datetime.now().isoformat()
    temp_c = data.get("temp_c")
    temp_f = data.get("temp_f")
    ph = data.get("ph")
    tds = data.get("tds_ppm")

    conn = get_db()
    conn.execute(
        """INSERT INTO sensor_readings (timestamp, temp_c, temp_f, ph, tds_ppm, source, raw_json)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (timestamp, temp_c, temp_f, ph, tds, "esp32", json.dumps(data)),
    )
    conn.commit()
    conn.close()

    print(f"[{timestamp}] temp={temp_f}°F  pH={ph}  TDS={tds}ppm")
    return jsonify({"status": "ok", "timestamp": timestamp}), 201


# --- Get recent readings ---
@app.route("/api/sensors", methods=["GET"])
def get_sensors():
    limit = request.args.get("limit", 50, type=int)
    hours = request.args.get("hours", None, type=int)

    conn = get_db()
    if hours:
        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
        rows = conn.execute(
            "SELECT * FROM sensor_readings WHERE timestamp > ? ORDER BY timestamp DESC LIMIT ?",
            (cutoff, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM sensor_readings ORDER BY timestamp DESC LIMIT ?", (limit,)
        ).fetchall()
    conn.close()

    return jsonify([dict(r) for r in rows])


# --- Get latest single reading ---
@app.route("/api/sensors/latest", methods=["GET"])
def get_latest():
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM sensor_readings ORDER BY timestamp DESC LIMIT 1"
    ).fetchone()
    conn.close()

    if row:
        return jsonify(dict(row))
    return jsonify({"error": "No readings yet"}), 404


# --- Manual event logging (NFC stickers, agent calls, manual observations) ---
@app.route("/api/events", methods=["POST"])
def log_event():
    data = request.get_json()
    if not data or "event_type" not in data:
        return jsonify({"error": "Need event_type"}), 400

    timestamp = data.get("timestamp", datetime.now().isoformat())
    data_payload = json.dumps(data.get("data", {}))
    notes = data.get("notes", "")

    conn = get_db()
    conn.execute(
        "INSERT INTO manual_events (timestamp, event_type, data, notes) VALUES (?, ?, ?, ?)",
        (timestamp, data["event_type"], data_payload, notes),
    )
    conn.commit()
    conn.close()

    print(f"[{timestamp}] EVENT: {data['event_type']} — {notes}")
    return jsonify({"status": "ok", "timestamp": timestamp}), 201


@app.route("/api/events", methods=["GET"])
def get_events():
    limit = request.args.get("limit", 50, type=int)
    event_type = request.args.get("type", None)
    since = request.args.get("since", None)

    conn = get_db()
    query = "SELECT * FROM manual_events WHERE 1=1"
    params = []
    if event_type:
        query += " AND event_type = ?"
        params.append(event_type)
    if since:
        query += " AND timestamp > ?"
        params.append(since)
    query += " ORDER BY timestamp DESC LIMIT ?"
    params.append(limit)

    rows = conn.execute(query, params).fetchall()
    conn.close()

    results = []
    for r in rows:
        row = dict(r)
        row["data"] = json.loads(row["data"]) if row.get("data") else {}
        results.append(row)
    return jsonify(results)


# --- Water test UI for mobile ---
@app.route("/water-test", methods=["GET"])
def water_test():
    html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Water Test — Media Luna</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            background: #0d1117;
            color: white;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
            font-size: 16px;
            padding: 20px;
            -webkit-tap-highlight-color: transparent;
        }
        h1 { font-size: 24px; margin-bottom: 24px; }
        .param-section { margin-bottom: 32px; }
        .param-label { font-size: 14px; font-weight: 600; margin-bottom: 12px; color: #8b949e; }
        .swatches { display: flex; gap: 8px; overflow-x: auto; padding-bottom: 8px; }
        .swatch {
            flex-shrink: 0;
            width: 56px;
            height: 56px;
            border-radius: 8px;
            cursor: pointer;
            transition: transform 0.2s, box-shadow 0.2s;
            border: 3px solid transparent;
        }
        .swatch.selected {
            border-color: white;
            transform: scale(1.1);
            box-shadow: 0 4px 12px rgba(255,255,255,0.3);
        }
        .swatch-label {
            font-size: 11px;
            text-align: center;
            margin-top: 4px;
            color: #8b949e;
        }
        .swatch-item { text-align: center; flex-shrink: 0; }
        textarea {
            width: 100%;
            background: #161b22;
            border: 1px solid #30363d;
            border-radius: 6px;
            color: white;
            font-size: 16px;
            padding: 12px;
            margin: 16px 0;
            resize: vertical;
            min-height: 80px;
            font-family: inherit;
        }
        textarea::placeholder { color: #6e7681; }
        button {
            width: 100%;
            background: #2ea043;
            color: white;
            border: none;
            border-radius: 6px;
            font-size: 18px;
            font-weight: 600;
            padding: 16px;
            cursor: pointer;
            transition: background 0.2s;
        }
        button:active { background: #26843b; }
        .confirmation {
            display: none;
            text-align: center;
            padding: 40px 20px;
        }
        .confirmation h2 { font-size: 20px; margin-bottom: 16px; color: #2ea043; }
        .confirmation .values {
            background: #161b22;
            border-radius: 8px;
            padding: 16px;
            margin: 20px 0;
            text-align: left;
        }
        .confirmation .values div {
            padding: 8px 0;
            border-bottom: 1px solid #30363d;
        }
        .confirmation .values div:last-child { border-bottom: none; }
        .confirmation .values span { color: #8b949e; margin-right: 8px; }
        .confirmation button { background: #238636; margin-top: 20px; }
    </style>
</head>
<body>
    <div id="form-container">
        <h1>Water Test</h1>

        <div class="param-section">
            <div class="param-label">pH</div>
            <div class="swatches" id="ph-swatches"></div>
        </div>

        <div class="param-section">
            <div class="param-label">Ammonia (ppm)</div>
            <div class="swatches" id="ammonia-swatches"></div>
        </div>

        <div class="param-section">
            <div class="param-label">Nitrite (ppm)</div>
            <div class="swatches" id="nitrite-swatches"></div>
        </div>

        <div class="param-section">
            <div class="param-label">Nitrate (ppm)</div>
            <div class="swatches" id="nitrate-swatches"></div>
        </div>

        <textarea id="notes" placeholder="observations..."></textarea>

        <button onclick="submitTest()">Log Test</button>
    </div>

    <div class="confirmation" id="confirmation">
        <h2>✓ Test Logged</h2>
        <div class="values" id="logged-values"></div>
        <button onclick="resetForm()">Log Another</button>
    </div>

    <script>
        const swatches = {
            ph: [
                {value: 6.0, color: "#F5E642"},
                {value: 6.4, color: "#D4D832"},
                {value: 6.6, color: "#A8C832"},
                {value: 6.8, color: "#72B832"},
                {value: 7.0, color: "#3A9E6E"},
                {value: 7.2, color: "#2A8A7A"},
                {value: 7.6, color: "#1A6E7A"}
            ],
            ammonia: [
                {value: 0, color: "#F5E642"},
                {value: 0.25, color: "#C8D832"},
                {value: 0.50, color: "#9AC832"},
                {value: 1.0, color: "#6AB832"},
                {value: 2.0, color: "#3A9832"},
                {value: 4.0, color: "#1A7A1A"},
                {value: 8.0, color: "#0A5A0A"}
            ],
            nitrite: [
                {value: 0, color: "#C8E8D0"},
                {value: 0.25, color: "#A882C0"},
                {value: 0.50, color: "#8A6AB0"},
                {value: 1.0, color: "#7050A0"},
                {value: 2.0, color: "#563888"},
                {value: 5.0, color: "#3A1870"}
            ],
            nitrate: [
                {value: 0, color: "#F5F0A0"},
                {value: 5, color: "#F0D060"},
                {value: 10, color: "#E0A830"},
                {value: 20, color: "#D06820"},
                {value: 40, color: "#C03010"},
                {value: 80, color: "#A01808"},
                {value: 160, color: "#780808"}
            ]
        };

        const selected = {ph: null, ammonia: null, nitrite: null, nitrate: null};

        function renderSwatches(param, containerId) {
            const container = document.getElementById(containerId);
            swatches[param].forEach(s => {
                const item = document.createElement('div');
                item.className = 'swatch-item';

                const swatch = document.createElement('div');
                swatch.className = 'swatch';
                swatch.style.backgroundColor = s.color;
                swatch.onclick = () => selectSwatch(param, s.value, swatch);

                const label = document.createElement('div');
                label.className = 'swatch-label';
                label.textContent = s.value;

                item.appendChild(swatch);
                item.appendChild(label);
                container.appendChild(item);
            });
        }

        function selectSwatch(param, value, element) {
            // Deselect previous
            const container = element.parentElement.parentElement;
            container.querySelectorAll('.swatch').forEach(s => s.classList.remove('selected'));

            // Select new
            element.classList.add('selected');
            selected[param] = value;
        }

        async function submitTest() {
            const data = {
                event_type: "water_test",
                timestamp: new Date().toISOString(),
                data: {
                    ph: selected.ph,
                    ammonia: selected.ammonia,
                    nitrite: selected.nitrite,
                    nitrate: selected.nitrate
                },
                notes: document.getElementById('notes').value
            };

            try {
                const response = await fetch('/api/events', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(data)
                });

                if (response.ok) {
                    showConfirmation(data.data, data.notes);
                } else {
                    alert('Error logging test');
                }
            } catch (error) {
                alert('Network error: ' + error.message);
            }
        }

        function showConfirmation(values, notes) {
            const html = `
                <div><span>pH:</span>${values.ph !== null ? values.ph : '—'}</div>
                <div><span>Ammonia:</span>${values.ammonia !== null ? values.ammonia + ' ppm' : '—'}</div>
                <div><span>Nitrite:</span>${values.nitrite !== null ? values.nitrite + ' ppm' : '—'}</div>
                <div><span>Nitrate:</span>${values.nitrate !== null ? values.nitrate + ' ppm' : '—'}</div>
                ${notes ? '<div><span>Notes:</span>' + notes + '</div>' : ''}
            `;
            document.getElementById('logged-values').innerHTML = html;
            document.getElementById('form-container').style.display = 'none';
            document.getElementById('confirmation').style.display = 'block';
        }

        function resetForm() {
            selected.ph = selected.ammonia = selected.nitrite = selected.nitrate = null;
            document.querySelectorAll('.swatch').forEach(s => s.classList.remove('selected'));
            document.getElementById('notes').value = '';
            document.getElementById('form-container').style.display = 'block';
            document.getElementById('confirmation').style.display = 'none';
        }

        // Initialize
        renderSwatches('ph', 'ph-swatches');
        renderSwatches('ammonia', 'ammonia-swatches');
        renderSwatches('nitrite', 'nitrite-swatches');
        renderSwatches('nitrate', 'nitrate-swatches');
    </script>
</body>
</html>
    """
    return render_template_string(html)


# --- Health check (Telegram heartbeat can ping this) ---
@app.route("/api/health", methods=["GET"])
def health():
    conn = get_db()
    row = conn.execute(
        "SELECT timestamp FROM sensor_readings ORDER BY timestamp DESC LIMIT 1"
    ).fetchone()
    conn.close()

    last_reading = dict(row)["timestamp"] if row else "never"
    return jsonify({"status": "alive", "last_reading": last_reading})


if __name__ == "__main__":
    init_db()
    # 0.0.0.0 makes it accessible from ESP32 on same WiFi network
    print("\n=== Media Luna Sensor Server ===")
    print("POST sensor data to: http://<your-ip>:5001/api/sensors")
    print("View latest reading: http://localhost:5001/api/sensors/latest")
    print("View recent readings: http://localhost:5001/api/sensors?limit=20")
    print("================================\n")
    app.run(host="0.0.0.0", port=5001, debug=True)
