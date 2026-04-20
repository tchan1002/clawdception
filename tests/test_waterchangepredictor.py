"""
Tests for waterchangepredictor — pure math functions only. No HTTP, no Claude API.

Run with:
    cd ~/clawdception && python3 -m pytest tests/test_waterchangepredictor.py -v
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from skills.waterchangepredictor.run import (
    linreg,
    r_squared,
    days_to_threshold,
    READINGS_PER_DAY,
    TDS_CEILING,
    PH_FLOOR,
)


class TestLinreg:
    def test_flat_line(self):
        slope, intercept = linreg([0, 1, 2, 3], [5, 5, 5, 5])
        assert slope == pytest.approx(0.0, abs=1e-9)
        assert intercept == pytest.approx(5.0)

    def test_rising_line(self):
        slope, intercept = linreg([0, 1, 2, 3], [10, 20, 30, 40])
        assert slope == pytest.approx(10.0)
        assert intercept == pytest.approx(10.0)

    def test_single_point_returns_zero_slope(self):
        slope, intercept = linreg([0], [7.0])
        assert slope == 0.0
        assert intercept == pytest.approx(7.0)

    def test_vertical_xs_returns_zero_slope(self):
        # all x values identical — denominator zero
        slope, intercept = linreg([2, 2, 2], [5, 6, 7])
        assert slope == 0.0


class TestRSquared:
    def test_perfect_fit_is_one(self):
        xs = list(range(10))
        ys = [2 * x + 1 for x in xs]
        slope, intercept = linreg(xs, ys)
        assert r_squared(xs, ys, slope, intercept) == pytest.approx(1.0)

    def test_flat_data_returns_one(self):
        xs = [0, 1, 2, 3]
        ys = [5.0] * 4
        assert r_squared(xs, ys, 0.0, 5.0) == 1.0

    def test_noisy_data_less_than_one(self):
        xs = list(range(10))
        ys = [1, 5, 2, 8, 3, 7, 4, 6, 9, 2]
        slope, intercept = linreg(xs, ys)
        assert r_squared(xs, ys, slope, intercept) < 1.0


class TestDaysToThreshold:
    def _rising_vals(self, start, step, n=20):
        """newest-first: vals[0]=start, vals[-1]=start+(n-1)*step (oldest has lowest)"""
        return [start - i * step for i in range(n)]

    def test_tds_rising_to_ceiling(self):
        # TDS rising +5 ppm/reading, current=230 → 20 readings until 250
        vals = self._rising_vals(230, -5)  # newest=230, oldest=135... wait
        # newest-first means vals[0] is newest. Rising over time = vals decrease as i increases
        # oldest→newest should rise, so vals[0] (newest) > vals[-1] (oldest)
        vals = [200 + i * 2 for i in range(20)]  # oldest=200, ..., newest=238 → newest-first
        vals = list(reversed(vals))  # now newest-first: vals[0]=238
        days, slope_day, current, r2 = days_to_threshold(vals, 250, rising=True)
        assert days is not None
        assert days > 0
        assert current == pytest.approx(238.0)
        assert slope_day > 0

    def test_tds_already_at_ceiling_returns_zero(self):
        vals = [260.0] * 20
        days, _, current, _ = days_to_threshold(vals, TDS_CEILING, rising=True)
        assert days == pytest.approx(0.0)

    def test_tds_falling_returns_none(self):
        # TDS falling — will never hit ceiling above
        vals = list(reversed([260 - i * 2 for i in range(20)]))  # newest-first, falling
        days, _, _, _ = days_to_threshold(vals, TDS_CEILING, rising=True)
        assert days is None

    def test_ph_falling_to_floor(self):
        # newest-first: vals[0]=newest=6.4, vals[-1]=oldest=6.78 → falling over time
        vals = [6.4 + i * 0.02 for i in range(20)]  # newest=6.4, oldest=6.78
        days, slope_day, current, r2 = days_to_threshold(vals, PH_FLOOR, rising=False)
        assert days is not None
        assert days > 0
        assert current == pytest.approx(6.4, abs=0.01)
        assert slope_day < 0

    def test_ph_already_at_floor_returns_zero(self):
        vals = [6.1] * 20
        days, _, _, _ = days_to_threshold(vals, PH_FLOOR, rising=False)
        assert days == pytest.approx(0.0)

    def test_ph_rising_returns_none(self):
        # pH rising — won't hit floor
        vals = list(reversed([6.3 + i * 0.01 for i in range(20)]))  # newest=6.3, older=higher
        # Wait: newest-first, pH rising over time = newest > oldest... actually rising over time
        # means oldest < newest. newest-first: vals[0]=newest=highest
        vals = [6.5 + i * 0.01 for i in range(20)]  # newest=6.5, older values decrease
        # oldest (i=19) = 6.69. In time order oldest→newest: 6.69 → 6.5 (falling). Bad.
        # For rising: oldest→newest should increase. newest-first: vals[0] > vals[-1]
        # opposite: vals = [6.5 - i*0.01 for i in range(20)] → oldest=6.31, newest=6.5 (rising)
        # But we want pH rising = no floor concern → return None
        # rising over time = newest > oldest = vals[0] > vals[-1]
        vals = [6.5 + i * 0.01 for i in range(20)]  # newest=6.5+0=6.5, oldest=6.5+19*0.01=6.69
        # In oldest→newest order: 6.69 → 6.5 (FALLING). This would project hitting floor.
        # For RISING pH (good, no concern): oldest→newest = increasing
        # newest-first: vals[0] is biggest, vals[-1] is smallest
        vals = [6.7 - i * 0.01 for i in range(20)]  # newest=6.7, oldest=6.51 → rising over time
        days, _, _, _ = days_to_threshold(vals, PH_FLOOR, rising=False)
        assert days is None

    def test_too_few_readings_returns_none(self):
        days, _, _, _ = days_to_threshold([230, 235, 240], TDS_CEILING, rising=True)
        assert days is None

    def test_slope_per_day_uses_readings_per_day(self):
        # slope of 1 ppm/reading → READINGS_PER_DAY ppm/day
        vals = list(reversed([100 + i * 1.0 for i in range(20)]))  # newest=119, oldest=100
        _, slope_day, _, _ = days_to_threshold(vals, 250, rising=True)
        assert slope_day == pytest.approx(READINGS_PER_DAY * 1.0, rel=0.01)
