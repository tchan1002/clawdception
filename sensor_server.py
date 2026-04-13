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
from pathlib import Path
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
    # Add data column to manual_events if it doesn't exist
    try:
        conn.execute("ALTER TABLE manual_events ADD COLUMN data TEXT DEFAULT '{}'")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # column already exists
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
    ph_raw = (data.get("debug") or {}).get("ph_before_offset") or data.get("ph")
    ph_offset = (data.get("calibration") or {}).get("ph_offset") or 0
    ph = round(ph_raw + ph_offset, 4) if ph_raw is not None else None
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
            -webkit-tap-highlight-color: transparent;
        }
        .nav {
            background: #161b22;
            padding: 12px 20px;
            display: flex;
            gap: 24px;
            border-bottom: 1px solid #30363d;
        }
        .nav a {
            color: #8b949e;
            text-decoration: none;
            font-size: 14px;
            transition: color 0.2s;
        }
        .nav a:hover { color: white; }
        .nav a.active { color: white; font-weight: 600; }
        .container { padding: 20px; }
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
    <div class="nav">
        <a href="/">Dashboard</a>
        <a href="/agent">Agent</a>
        <a href="/water-test" class="active">Water Test</a>
        <a href="/log-event">Log Event</a>
    </div>
    <div class="container">
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
                swatch.dataset.param = param;
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
            document.querySelectorAll('.swatch[data-param="' + param + '"]').forEach(s => s.classList.remove('selected'));

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
    </div>
</body>
</html>
    """
    return html


# --- Agent status UI for mobile ---
@app.route("/agent", methods=["GET"])
def agent_status():
    from pathlib import Path
    import os

    # Get paths
    base_dir = Path(os.getcwd())
    logs_dir = base_dir / "logs"
    decisions_dir = logs_dir / "decisions"
    journal_dir = base_dir / "journal"
    monitor_log_path = logs_dir / "monitor.log"

    # Read latest decision
    decision = None
    risk_level = "unknown"
    risk_color = "#8b949e"

    # Try today's decisions, then yesterday
    for days_back in [0, 1]:
        target_date = datetime.now() - timedelta(days=days_back)
        decision_file = decisions_dir / f"{target_date.date()}.jsonl"

        if decision_file.exists():
            try:
                lines = [line.strip() for line in decision_file.read_text().splitlines() if line.strip()]
                for line in reversed(lines):
                    entry = json.loads(line)
                    if "parameter_status" in entry:
                        decision = entry
                        risk_level = decision.get("risk_level", "unknown")
                        break
                if decision:
                    break
            except (json.JSONDecodeError, FileNotFoundError):
                pass

    # Map risk colors
    if risk_level == "green":
        risk_color = "#2ea043"
    elif risk_level == "yellow":
        risk_color = "#d29922"
    elif risk_level == "red":
        risk_color = "#da3633"

    # Get all available journal dates sorted descending (from YYYY-MM-DD-HHMM.md files)
    journal_dates = []
    if journal_dir.exists():
        seen = set()
        for journal_file in sorted(journal_dir.glob("????-??-??-????.md"), reverse=True):
            date_str = journal_file.stem[:10]  # extract YYYY-MM-DD
            if date_str not in seen:
                seen.add(date_str)
                journal_dates.append(date_str)

    # Read most recent journal entry (concatenate all entries for that date)
    journal_text = ""
    journal_date = ""
    if journal_dates:
        journal_date = journal_dates[0]
        entries = sorted(journal_dir.glob(f"{journal_date}-????.md"))
        journal_text = "\n\n".join(f.read_text() for f in entries)

    # Read monitor log tail
    monitor_lines = []
    if monitor_log_path.exists():
        try:
            lines = monitor_log_path.read_text().splitlines()
            monitor_lines = lines[-10:] if len(lines) > 10 else lines
        except FileNotFoundError:
            pass

    html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Media Luna · Agent Status</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@300;400;500&display=swap');
        :root {{
            --bg: #080e10;
            --surface: #0d1a1e;
            --border: #1a3a40;
            --accent: #00c9a7;
            --accent2: #0099cc;
            --warn: #e8a838;
            --danger: #e84040;
            --text: #c8dde0;
            --muted: #4a6a70;
            --grid: #0f2428;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            background: var(--bg);
            color: var(--text);
            font-family: 'IBM Plex Mono', monospace;
            font-size: 12px;
            line-height: 1.5;
            min-height: 100vh;
            -webkit-tap-highlight-color: transparent;
        }}
        body::before {{
            content: '';
            position: fixed;
            inset: 0;
            background-image:
                linear-gradient(var(--grid) 1px, transparent 1px),
                linear-gradient(90deg, var(--grid) 1px, transparent 1px);
            background-size: 40px 40px;
            opacity: 0.6;
            pointer-events: none;
            z-index: 0;
        }}
        .nav {{
            background: #161b22;
            padding: 12px 20px;
            display: flex;
            gap: 24px;
            border-bottom: 1px solid var(--border);
            position: relative;
            z-index: 10;
        }}
        .nav a {{
            color: var(--muted);
            text-decoration: none;
            font-size: 11px;
            letter-spacing: 0.1em;
            text-transform: uppercase;
            transition: color 0.2s;
            font-family: 'IBM Plex Mono', monospace;
        }}
        .nav a:hover {{ color: var(--text); }}
        .nav a.active {{ color: var(--accent); font-weight: 500; }}
        .container {{
            position: relative;
            z-index: 1;
            max-width: 900px;
            margin: 0 auto;
            padding: 24px 20px;
        }}
        h1 {{
            font-size: 16px;
            font-weight: 500;
            color: var(--accent);
            letter-spacing: 0.05em;
            margin-bottom: 24px;
            padding-bottom: 16px;
            border-bottom: 1px solid var(--border);
        }}
        .section {{ margin-bottom: 28px; }}
        .section-title {{
            font-size: 9px;
            font-weight: 400;
            color: var(--muted);
            text-transform: uppercase;
            letter-spacing: 0.2em;
            margin-bottom: 10px;
        }}
        .risk-badge {{
            display: inline-block;
            padding: 4px 10px;
            font-size: 10px;
            font-weight: 500;
            text-transform: uppercase;
            letter-spacing: 0.15em;
            background: {risk_color}18;
            color: {risk_color};
            border: 1px solid {risk_color}50;
        }}
        .param-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 10px;
            margin-bottom: 16px;
        }}
        .param-card {{
            background: var(--surface);
            border: 1px solid var(--border);
            padding: 12px;
        }}
        .param-name {{
            font-size: 9px;
            color: var(--muted);
            text-transform: uppercase;
            letter-spacing: 0.15em;
            margin-bottom: 6px;
        }}
        .param-value {{
            font-size: 18px;
            font-weight: 500;
            margin-bottom: 4px;
        }}
        .param-note {{
            font-size: 10px;
            color: var(--muted);
            line-height: 1.5;
        }}
        .reasoning {{
            background: var(--surface);
            border: 1px solid var(--border);
            padding: 14px;
            font-size: 11px;
            line-height: 1.7;
            color: var(--text);
        }}
        .actions {{
            background: var(--surface);
            border: 1px solid var(--border);
            padding: 14px;
        }}
        .actions ul {{
            list-style: none;
            padding-left: 0;
        }}
        .actions li {{
            padding: 7px 0;
            border-bottom: 1px solid rgba(26,58,64,0.4);
            font-size: 11px;
        }}
        .actions li:last-child {{ border-bottom: none; }}
        .actions li:before {{
            content: "→";
            margin-right: 8px;
            color: var(--accent);
        }}
        .journal {{
            background: var(--surface);
            border: 1px solid var(--border);
            padding: 14px;
            max-height: 400px;
            overflow-y: auto;
            white-space: pre-wrap;
            font-size: 11px;
            line-height: 1.7;
            color: var(--text);
            min-height: 80px;
        }}
        .journal.loading {{
            display: flex;
            align-items: center;
            justify-content: center;
            color: var(--muted);
            font-style: italic;
        }}
        .journal-nav {{
            display: flex;
            gap: 8px;
            margin-top: 10px;
            align-items: center;
        }}
        .journal-nav button {{
            background: none;
            color: var(--muted);
            border: 1px solid var(--border);
            font-family: 'IBM Plex Mono', monospace;
            font-size: 9px;
            letter-spacing: 0.1em;
            padding: 4px 10px;
            cursor: pointer;
            transition: color 0.2s, border-color 0.2s;
        }}
        .journal-nav button:hover {{ color: var(--accent); border-color: var(--accent); }}
        .journal-nav button:disabled {{
            opacity: 0.3;
            cursor: not-allowed;
            color: var(--muted);
            border-color: var(--border);
        }}
        .journal-nav #journal-date {{
            font-size: 9px;
            color: var(--accent);
            letter-spacing: 0.1em;
            flex: 1;
            text-align: center;
        }}
        .monitor-log {{
            background: var(--surface);
            border: 1px solid var(--border);
            padding: 14px;
            font-family: 'IBM Plex Mono', monospace;
            font-size: 10px;
            line-height: 1.8;
        }}
        .monitor-log div {{
            padding: 3px 0;
            color: var(--muted);
            border-bottom: 1px solid rgba(26,58,64,0.3);
        }}
        .monitor-log div:last-child {{ border-bottom: none; }}
        .not-available {{
            color: var(--muted);
            font-style: italic;
            padding: 20px;
            text-align: center;
            font-size: 11px;
        }}
        .status-green {{ color: var(--accent); }}
        .status-yellow {{ color: var(--warn); }}
        .status-red {{ color: var(--danger); }}
    </style>
</head>
<body>
    <div class="nav">
        <a href="/">Dashboard</a>
        <a href="/agent" class="active">Agent</a>
        <a href="/water-test">Water Test</a>
        <a href="/log-event">Log Event</a>
    </div>
    <div class="container">
        <h1>Agent Status</h1>

        <div class="section">
            <div class="section-title">Current Risk Level</div>
            <div class="risk-badge">{risk_level}</div>
        </div>

        {''.join([f"""
        <div class="section">
            <div class="section-title">Parameter Status</div>
            <div class="param-grid">
                <div class="param-card">
                    <div class="param-name">Temperature</div>
                    <div class="param-value status-{decision["parameter_status"]["temperature"]["status"]}">{decision["parameter_status"]["temperature"]["value"]}{decision["parameter_status"]["temperature"]["unit"]}</div>
                    <div class="param-note">{decision["parameter_status"]["temperature"]["note"]}</div>
                </div>
                <div class="param-card">
                    <div class="param-name">pH</div>
                    <div class="param-value status-{decision["parameter_status"]["ph"]["status"]}">{decision["parameter_status"]["ph"]["value"]}</div>
                    <div class="param-note">{decision["parameter_status"]["ph"]["note"]}</div>
                </div>
                <div class="param-card">
                    <div class="param-name">TDS</div>
                    <div class="param-value status-{decision["parameter_status"]["tds"]["status"]}">{decision["parameter_status"]["tds"]["value"]} {decision["parameter_status"]["tds"]["unit"]}</div>
                    <div class="param-note">{decision["parameter_status"]["tds"]["note"]}</div>
                </div>
            </div>
        </div>

        <div class="section">
            <div class="section-title">Reasoning</div>
            <div class="reasoning">{decision.get("reasoning", "Not available")}</div>
        </div>

        <div class="section">
            <div class="section-title">Recommended Actions</div>
            <div class="actions">
                <ul>
                    {"".join([f"<li>{action}</li>" for action in decision.get("recommended_actions", [])])}
                </ul>
            </div>
        </div>
        """ if decision else '<div class="section"><div class="not-available">No agent decisions available yet</div></div>'])}

        <div class="section">
            <div class="section-title">Journal Entry</div>
            <div id="journal-content" class="journal">{'<pre style="margin: 0; font-family: inherit; white-space: pre-wrap;">' + journal_text + '</pre>' if journal_text else '<div class="not-available">No journal entries yet</div>'}</div>
            {f'''<div class="journal-nav">
                <button id="prev-btn" onclick="navigateJournal(-1)">◀ prev</button>
                <span id="journal-date">{journal_date if journal_date else ""}</span>
                <button id="next-btn" onclick="navigateJournal(1)">next ▶</button>
            </div>''' if journal_dates else ''}
        </div>

        <div class="section">
            <div class="section-title">Monitor Log (Last 10)</div>
            {'<div class="monitor-log">' + "".join([f"<div>{line}</div>" for line in monitor_lines]) + '</div>' if monitor_lines else '<div class="not-available">No monitor log yet</div>'}
        </div>
    </div>

    <script>
        // Journal navigation
        const journalDates = {json.dumps(journal_dates)};
        let currentIndex = 0;

        console.log('Journal dates loaded:', journalDates);
        console.log('Current index:', currentIndex);

        function updateNavigationButtons() {{
            const prevBtn = document.getElementById('prev-btn');
            const nextBtn = document.getElementById('next-btn');

            console.log('Updating button states - currentIndex:', currentIndex, 'total dates:', journalDates.length);

            if (prevBtn && nextBtn) {{
                prevBtn.disabled = currentIndex >= journalDates.length - 1;
                nextBtn.disabled = currentIndex <= 0;
                console.log('Prev disabled:', prevBtn.disabled, 'Next disabled:', nextBtn.disabled);
            }}
        }}

        async function navigateJournal(direction) {{
            console.log('navigateJournal called with direction:', direction);
            console.log('Current index before:', currentIndex);

            currentIndex += direction;
            if (currentIndex < 0) currentIndex = 0;
            if (currentIndex >= journalDates.length) currentIndex = journalDates.length - 1;

            console.log('Current index after:', currentIndex);

            const date = journalDates[currentIndex];
            console.log('Fetching journal for date:', date);

            const contentDiv = document.getElementById('journal-content');

            // Show loading state
            contentDiv.classList.add('loading');
            contentDiv.innerHTML = 'Loading...';

            try {{
                const url = `/api/journal?date=${{date}}`;
                console.log('Fetching URL:', url);

                const response = await fetch(url);
                console.log('Response status:', response.status);

                if (!response.ok) throw new Error('Failed to fetch journal');

                const data = await response.json();
                console.log('Response data:', data);

                document.getElementById('journal-date').textContent = data.date;

                // Remove loading state
                contentDiv.classList.remove('loading');

                if (data.exists && data.content) {{
                    contentDiv.innerHTML = '<pre style="margin: 0; font-family: inherit; white-space: pre-wrap;">' + data.content + '</pre>';
                }} else {{
                    contentDiv.innerHTML = '<div class="not-available">No journal entry for this date</div>';
                }}

                updateNavigationButtons();
            }} catch (error) {{
                console.error('Error fetching journal:', error);
                contentDiv.classList.remove('loading');
                contentDiv.innerHTML = '<div class="not-available">Error loading journal</div>';
            }}
        }}

        // Initialize button states
        console.log('Initializing navigation buttons');
        updateNavigationButtons();

        // Auto-refresh every 60 seconds
        setTimeout(() => {{ window.location.reload(); }}, 60000);
    </script>
</body>
</html>
    """
    return html


# --- Journal API for agent page navigation ---
@app.route("/api/journal", methods=["GET"])
def get_journal():
    from pathlib import Path
    import os

    date_param = request.args.get("date")
    base_dir = Path(os.getcwd())
    journal_dir = base_dir / "journal"

    # If no date provided, return most recent
    if not date_param:
        if journal_dir.exists():
            files = sorted(journal_dir.glob("????-??-??-????.md"), reverse=True)
            if files:
                date_param = files[0].stem[:10]

    if not date_param:
        return jsonify({"date": "", "content": "", "exists": False})

    # Validate date format
    try:
        datetime.strptime(date_param, "%Y-%m-%d")
    except ValueError:
        return jsonify({"error": "Invalid date format"}), 400

    # Concatenate all timestamped entries for this date
    entry_files = sorted(journal_dir.glob(f"{date_param}-????.md"))
    if entry_files:
        content = "\n\n".join(f.read_text() for f in entry_files)
        return jsonify({"date": date_param, "content": content, "exists": True})
    else:
        return jsonify({"date": date_param, "content": "", "exists": False})


# --- Agent state history ---
@app.route("/api/agent-state-history", methods=["GET"])
def get_agent_state_history():
    from pathlib import Path
    import os

    history_dir = Path(os.getcwd()) / "agent_state_history"
    date_param = request.args.get("date")

    if not history_dir.exists():
        return jsonify({"dates": [], "content": "", "exists": False})

    if date_param:
        try:
            datetime.strptime(date_param, "%Y-%m-%d")
        except ValueError:
            return jsonify({"error": "Invalid date format"}), 400
        # Match YYYY-MM-DD-HHMM.md; pick latest if multiple exist
        matches = sorted(history_dir.glob(f"{date_param}-????.md"), reverse=True)
        if matches:
            return jsonify({"date": date_param, "content": matches[0].read_text(), "exists": True})
        return jsonify({"date": date_param, "content": "", "exists": False})

    # List unique dates (YYYY-MM-DD) from YYYY-MM-DD-HHMM.md files, most recent first
    files = sorted(history_dir.glob("????-??-??-????.md"), reverse=True)
    seen = set()
    dates = []
    for f in files:
        date = f.stem[:10]
        if date not in seen:
            seen.add(date)
            dates.append(date)
    return jsonify({"dates": dates})


# --- General manual event logging UI ---
@app.route("/log-event", methods=["GET"])
def log_event_ui():
    html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Log Event — Media Luna</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            background: #0d1117;
            color: white;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
            font-size: 16px;
            -webkit-tap-highlight-color: transparent;
        }
        .nav {
            background: #161b22;
            padding: 12px 20px;
            display: flex;
            gap: 24px;
            border-bottom: 1px solid #30363d;
        }
        .nav a {
            color: #8b949e;
            text-decoration: none;
            font-size: 14px;
            transition: color 0.2s;
        }
        .nav a:hover { color: white; }
        .nav a.active { color: white; font-weight: 600; }
        .container { padding: 20px; }
        h1 { font-size: 24px; margin-bottom: 24px; }
        .field-label {
            font-size: 14px;
            font-weight: 600;
            margin-bottom: 10px;
            color: #8b949e;
        }
        .field-section { margin-bottom: 28px; }
        select {
            width: 100%;
            background: #161b22;
            border: 1px solid #30363d;
            border-radius: 6px;
            color: white;
            font-size: 16px;
            padding: 12px;
            font-family: inherit;
            appearance: none;
            background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='8' viewBox='0 0 12 8'%3E%3Cpath fill='%238b949e' d='M1 1l5 5 5-5'/%3E%3C/svg%3E");
            background-repeat: no-repeat;
            background-position: right 14px center;
        }
        select:focus { outline: none; border-color: #58a6ff; }
        select option { background: #161b22; }
        textarea {
            width: 100%;
            background: #161b22;
            border: 1px solid #30363d;
            border-radius: 6px;
            color: white;
            font-size: 16px;
            padding: 12px;
            resize: vertical;
            min-height: 100px;
            font-family: inherit;
        }
        textarea::placeholder { color: #6e7681; }
        textarea:focus { outline: none; border-color: #58a6ff; }
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
        button:disabled { background: #3a3a3a; cursor: not-allowed; }
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
        .error { color: #f85149; font-size: 14px; margin-top: 8px; display: none; }
    </style>
</head>
<body>
    <div class="nav">
        <a href="/">Dashboard</a>
        <a href="/agent">Agent</a>
        <a href="/water-test">Water Test</a>
        <a href="/log-event" class="active">Log Event</a>
    </div>
    <div class="container">
    <div id="form-container">
        <h1>Log Event</h1>

        <div class="field-section">
            <div class="field-label">Event Type</div>
            <select id="event-type">
                <option value="water_change">Water Change</option>
                <option value="heater_adjust">Heater Adjust</option>
                <option value="feeding">Feeding</option>
                <option value="observation">Observation</option>
                <option value="dosing">Dosing</option>
                <option value="maintenance">Maintenance</option>
                <option value="plant_addition">Plant Addition</option>
            </select>
        </div>

        <div class="field-section">
            <div class="field-label">Notes</div>
            <textarea id="notes" placeholder="e.g. 30% water change, adjusted heater to 76°F..."></textarea>
        </div>

        <div class="error" id="error-msg">Something went wrong. Please try again.</div>
        <button onclick="submitEvent()">Log Event</button>
    </div>

    <div class="confirmation" id="confirmation">
        <h2>✓ Event Logged</h2>
        <div class="values" id="logged-values"></div>
        <button onclick="resetForm()">Log Another</button>
    </div>

    <script>
        const EVENT_LABELS = {
            water_change: "Water Change",
            heater_adjust: "Heater Adjust",
            feeding: "Feeding",
            observation: "Observation",
            dosing: "Dosing",
            maintenance: "Maintenance",
            plant_addition: "Plant Addition"
        };

        async function submitEvent() {
            const eventType = document.getElementById('event-type').value;
            const notes = document.getElementById('notes').value.trim();
            const btn = document.querySelector('button');
            const errorEl = document.getElementById('error-msg');

            errorEl.style.display = 'none';
            btn.disabled = true;

            const payload = {
                event_type: eventType,
                timestamp: new Date().toISOString(),
                notes: notes,
                data: {}
            };

            try {
                const response = await fetch('/api/events', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(payload)
                });

                if (response.ok) {
                    showConfirmation(eventType, notes);
                } else {
                    errorEl.style.display = 'block';
                    btn.disabled = false;
                }
            } catch (err) {
                errorEl.textContent = 'Network error: ' + err.message;
                errorEl.style.display = 'block';
                btn.disabled = false;
            }
        }

        function showConfirmation(eventType, notes) {
            const html = `
                <div><span>Type:</span>${EVENT_LABELS[eventType] || eventType}</div>
                <div><span>Time:</span>${new Date().toLocaleTimeString()}</div>
                ${notes ? '<div><span>Notes:</span>' + notes + '</div>' : ''}
            `;
            document.getElementById('logged-values').innerHTML = html;
            document.getElementById('form-container').style.display = 'none';
            document.getElementById('confirmation').style.display = 'block';
        }

        function resetForm() {
            document.getElementById('notes').value = '';
            document.getElementById('event-type').selectedIndex = 0;
            document.getElementById('error-msg').style.display = 'none';
            document.querySelector('#form-container button').disabled = false;
            document.getElementById('form-container').style.display = 'block';
            document.getElementById('confirmation').style.display = 'none';
        }
    </script>
    </div>
</body>
</html>
    """
    return html


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


# --- Owner photo upload endpoints ---
PHOTOS_DIR = Path("snapshots/photos")


@app.route("/api/photos", methods=["POST"])
def upload_photo():
    """Owner POSTs a photo (multipart form) with optional notes text."""
    if "file" not in request.files:
        return jsonify({"error": "No file field"}), 400
    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "Empty filename"}), 400

    notes = request.form.get("notes", "")
    timestamp = datetime.now()
    ts_str = timestamp.isoformat()
    PHOTOS_DIR.mkdir(parents=True, exist_ok=True)

    filename = timestamp.strftime("%Y-%m-%d_%H-%M-%S") + ".jpg"
    dest = PHOTOS_DIR / filename
    f.save(str(dest))

    data_payload = json.dumps({"filename": filename})
    conn = get_db()
    conn.execute(
        "INSERT INTO manual_events (timestamp, event_type, data, notes) VALUES (?, ?, ?, ?)",
        (ts_str, "photo", data_payload, notes),
    )
    conn.commit()
    conn.close()

    print(f"[{ts_str}] PHOTO uploaded: {filename} — {notes}")
    return jsonify({"status": "ok", "filename": filename, "timestamp": ts_str}), 201


@app.route("/api/photos/<filename>", methods=["GET"])
def serve_photo(filename):
    """Serve an owner-uploaded photo."""
    path = PHOTOS_DIR / filename
    if not path.exists():
        return jsonify({"error": "Not found"}), 404
    return send_file(str(path), mimetype="image/jpeg")


# --- ESP32-CAM snapshot endpoints ---
SNAPSHOTS_DIR = Path("snapshots")


@app.route("/api/snapshot", methods=["POST"])
def receive_snapshot():
    """ESP32-CAM POSTs raw JPEG bytes here every 5 minutes."""
    if not request.content_type or "image/jpeg" not in request.content_type:
        return jsonify({"error": "Expected Content-Type: image/jpeg"}), 400

    img_bytes = request.data
    if not img_bytes:
        return jsonify({"error": "Empty body"}), 400

    timestamp = datetime.now()
    ts_str = timestamp.isoformat()

    SNAPSHOTS_DIR.mkdir(exist_ok=True)
    (SNAPSHOTS_DIR / "latest.jpg").write_bytes(img_bytes)
    archive_name = timestamp.strftime("%Y-%m-%d_%H-%M-%S") + ".jpg"
    (SNAPSHOTS_DIR / archive_name).write_bytes(img_bytes)

    print(f"[{ts_str}] SNAPSHOT {len(img_bytes)} bytes → snapshots/{archive_name}")
    return jsonify({"status": "ok", "timestamp": ts_str, "bytes": len(img_bytes)}), 201


@app.route("/api/snapshot/latest", methods=["GET"])
def get_snapshot():
    """Serve the most recent ESP32-CAM JPEG for vision analysis."""
    latest = SNAPSHOTS_DIR / "latest.jpg"
    if not latest.exists():
        return jsonify({"error": "No snapshot yet"}), 404
    return send_file(str(latest), mimetype="image/jpeg")


if __name__ == "__main__":
    init_db()
    # 0.0.0.0 makes it accessible from ESP32 on same WiFi network
    print("\n=== Media Luna Sensor Server ===")
    print("POST sensor data to: http://<your-ip>:5001/api/sensors")
    print("View latest reading: http://localhost:5001/api/sensors/latest")
    print("View recent readings: http://localhost:5001/api/sensors?limit=20")
    print("================================\n")
    app.run(host="0.0.0.0", port=5001, debug=False)
