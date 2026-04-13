# API Reference — Media Luna

## Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Serves dashboard HTML |
| POST | `/api/sensors` | Receive ESP32 reading (returns 201) |
| GET | `/api/sensors` | Recent readings (`?limit=50`, `?hours=N`) |
| GET | `/api/sensors/latest` | Single latest reading |
| POST | `/api/events` | Log a structured event |
| GET | `/api/events` | Query events (`?limit=N`, `?since=ISO`, `?type=water_test`) |
| POST | `/api/photos` | Upload owner photo (multipart: `file` + optional `notes`); saves to `snapshots/photos/` and creates a `photo` event |
| GET | `/api/photos/<filename>` | Serve a photo from `snapshots/photos/` |
| GET | `/api/health` | Health check, returns last reading timestamp |

Server: `http://localhost:5001` (Pi) or `http://192.168.12.76:5001` (remote)

## Event Types

```json
{
  "event_type": "water_test" | "water_change" | "feeding" | "observation" | "manual_override" | "snapshot" | "shrimp_added" | "photo" | "owner_note" | "owner_photo",
  "data": {},
  "source": "nfc" | "manual" | "agent" | "telegram",
  "timestamp": "ISO 8601 (optional, defaults to now)"
}
```

Examples:
```json
{"event_type": "water_test", "data": {"ammonia_ppm": 1.0, "nitrite_ppm": 0.25, "nitrate_ppm": 5.0}, "source": "manual"}
{"event_type": "water_change", "data": {"percent": 25, "treated": true, "notes": "used Prime"}, "source": "manual"}
{"event_type": "observation", "data": {"note": "biofilm forming on driftwood"}, "source": "manual"}
{"event_type": "shrimp_added", "data": {"count": 10, "source": "LFS"}, "notes": "Initial colony introduction"}
{"event_type": "owner_note", "data": {"source": "telegram"}, "notes": "Free-text message from owner"}
{"event_type": "owner_photo", "data": {"filename": "2026-04-13_14-30-00.jpg", "source": "telegram"}, "notes": "Optional caption"}
{"event_type": "photo", "data": {"filename": "2026-04-13_14-30-00.jpg"}, "notes": "Uploaded via dashboard"}
```

**Photo upload** (multipart form to `/api/photos`):
```bash
curl -X POST http://localhost:5001/api/photos \
  -F "file=@tank.jpg" \
  -F "notes=shrimp looking active today"
```

## Database Schema

```sql
CREATE TABLE sensor_readings (
    id INTEGER PRIMARY KEY,
    timestamp TEXT,
    temp_c REAL, temp_f REAL, ph REAL, tds_ppm REAL,
    source TEXT,
    raw_json TEXT  -- full ESP32 JSON payload
);

CREATE TABLE events (
    id INTEGER PRIMARY KEY,
    timestamp TEXT,
    event_type TEXT,
    data_json TEXT,  -- flexible JSON depending on event_type
    source TEXT      -- "nfc" | "manual" | "agent"
);

-- Legacy table (kept for backward compat)
CREATE TABLE manual_events (
    id INTEGER PRIMARY KEY,
    timestamp TEXT, event_type TEXT, notes TEXT
);
```

## Quick Queries

```bash
sqlite3 ~/clawdception/media_luna.db ".schema"
sqlite3 ~/clawdception/media_luna.db "SELECT * FROM sensor_readings ORDER BY id DESC LIMIT 5;"
sqlite3 ~/clawdception/media_luna.db "SELECT * FROM events ORDER BY id DESC LIMIT 10;"
```

## Schema Changes

If modifying the schema, note the migration needed and flag it to the user — the Pi's `media_luna.db` is source of truth and must be migrated manually.
