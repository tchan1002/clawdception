# water-change-predictor

**Type:** new skill  
**Risk:** read-only — observes and suggests, never acts

## What it does

Runs daily after daily-log. Fetches 7 days of sensor readings, fits linear trend to TDS and pH, estimates days until threshold crossed (TDS ≥250 ppm, pH ≤6.2). Writes projection to `state/next_water_change.md`. Calls Toby (low urgency) if either threshold is ≤2 days out.

## Outputs

- `state/next_water_change.md` — updated daily with current projections
- Telegram alert (low urgency) if change is due within 2 days

## Thresholds

- TDS ceiling: 250 ppm
- pH floor: 6.2
- Alert window: 2 days

## Cron

Add manually:
```
30 8 * * * cd /home/pi/clawdception && python3 skills/waterchangepredictor/run.py >> logs/water_change_predictor.log 2>&1
```

## Usage

```bash
python3 skills/waterchangepredictor/run.py          # normal run
python3 skills/waterchangepredictor/run.py --force  # always alert, skip no-data guard
```
