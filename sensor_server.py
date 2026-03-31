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
from flask import Flask, request, jsonify, send_file

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
    body = request.get_json()
    if not body or "event_type" not in body:
        return jsonify({"error": "Need event_type"}), 400

    valid_types = {"water_test", "water_change", "feeding", "observation", "manual_override", "snapshot"}
    if body["event_type"] not in valid_types:
        return jsonify({"error": f"event_type must be one of: {', '.join(sorted(valid_types))}"}), 400

    # Use provided timestamp or default to now
    timestamp = body.get("timestamp") or datetime.now().isoformat()
    event_type = body["event_type"]
    data = body.get("data", {})
    source = body.get("source", "manual")

    conn = get_db()
    conn.execute(
        "INSERT INTO events (timestamp, event_type, data_json, source) VALUES (?, ?, ?, ?)",
        (timestamp, event_type, json.dumps(data), source),
    )
    conn.commit()
    conn.close()

    print(f"[{timestamp}] EVENT ({source}): {event_type} — {data}")
    return jsonify({"status": "ok", "timestamp": timestamp}), 201


@app.route("/api/events", methods=["GET"])
def get_events():
    limit = request.args.get("limit", 50, type=int)
    since = request.args.get("since", None)
    event_type = request.args.get("type", None)

    conn = get_db()
    query = "SELECT * FROM events"
    params = []
    conditions = []

    if since:
        conditions.append("timestamp > ?")
        params.append(since)
    if event_type:
        conditions.append("event_type = ?")
        params.append(event_type)

    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY timestamp DESC LIMIT ?"
    params.append(limit)

    rows = conn.execute(query, params).fetchall()
    conn.close()

    results = []
    for r in rows:
        row = dict(r)
        try:
            row["data"] = json.loads(row.pop("data_json") or "{}")
        except (json.JSONDecodeError, KeyError):
            row["data"] = {}
        results.append(row)

    return jsonify(results)


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
