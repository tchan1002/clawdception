"""
Tests for export_dashboard — verifies STATIC_DATA snapshot includes ph_calibrating state.

Run with:
    cd ~/clawdception && python3 -m pytest tests/test_export_dashboard.py -v
"""

import json
import re
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


def _get_static_data(html: str) -> dict:
    idx = html.find("STATIC_DATA =")
    end = html.find(";\n\nconst API_URL", idx)
    blob = html[idx + len("STATIC_DATA =") : end]
    return json.loads(blob)


def _make_mock_db(sensors=None, events=None):
    conn = MagicMock()
    sensors = sensors or []
    events = events or []

    def execute_side_effect(query, *args):
        result = MagicMock()
        if "sensor_readings" in query:
            result.fetchall.return_value = [dict(r) for r in sensors]
        elif "water_test" in query:
            result.fetchone.return_value = None
        else:
            result.fetchall.return_value = [dict(r) for r in events]
        return result

    conn.execute.side_effect = execute_side_effect
    return conn


class TestExportDashboardPhCalibrating:
    def _run_export(self, ph_calibrating: bool) -> str:
        import sensor_server
        conn = _make_mock_db()
        with (
            patch.object(sensor_server, "get_db", return_value=conn),
            patch.object(sensor_server, "PH_CALIBRATING", ph_calibrating),
            patch("sensor_server.Path.exists", return_value=False),
        ):
            app = sensor_server.app
            with app.test_client() as client:
                resp = client.get("/export/dashboard")
                return resp.data.decode()

    def test_ph_calibrating_true_baked_into_static_data(self):
        html = self._run_export(ph_calibrating=True)
        data = _get_static_data(html)
        assert data["phCalibrating"] is True

    def test_ph_calibrating_false_baked_into_static_data(self):
        html = self._run_export(ph_calibrating=False)
        data = _get_static_data(html)
        assert data["phCalibrating"] is False

    def test_js_seed_line_present_before_health_fetch(self):
        html = self._run_export(ph_calibrating=True)
        seed = "if (window.STATIC_DATA) phCalibrating = !!window.STATIC_DATA.phCalibrating;"
        fetch = "fetch('/api/health')"
        assert seed in html
        assert html.index(seed) < html.index(fetch)
