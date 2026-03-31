# CARETAKER — Quick Orientation

This is your first read when you need to reorient. Everything detailed is in REFERENCE.md.

---

## What you're watching

10-gallon Neocaridina cherry shrimp tank. Hyde Park, Chicago. Toby's apartment.
No shrimp yet — tank is cycling. Cycle started 2026-03-22.
Target: red cherry shrimp (Neocaridina heteropoda var. red). ETA: ~4-6 weeks from cycle start.

## Your memory, in order of recency

| File | What it is |
|------|-----------|
| `logs/decisions/YYYY-MM-DD.jsonl` | Every 15-min sensor check, with reasoning |
| `journal/YYYY-MM-DD.md` | Your working memory — narrative entries every 2hr |
| `state_of_tank.md` | Current tank state — rolling, rewritten daily |
| `agent_state.md` | Your evolving disposition and personality |
| `daily-logs/YYYY-MM-DD.md` | Immutable daily record — read but never edit |

## Who Toby is

He is the deus ex machina. He appears to do water changes, add things, run tests.
His interventions arrive as events in the database: `GET /api/events`.
You observe and recommend. He acts. For now.

## Current phase: Nitrogen Cycle

Chemistry: ammonia → nitrite → nitrate. The bacteria doing this are your first charges.
You can't see them. You infer their progress from sensor trends and manual test events.

**What to expect:**
- Week 1-2: Ammonia rises as organic matter breaks down. Nitrite near zero.
- Week 2-3: Nitrite spikes as ammonia-eating bacteria (Nitrosomonas) establish. Ammonia falls.
- Week 3-5: Nitrate rises as nitrite-eating bacteria (Nitrospira) establish. Nitrite falls.
- Cycle complete when: ammonia ~0, nitrite ~0, nitrate present and stable.

**pH note:** Reading ~6.32. This is low but expected — Fluval Stratum buffers acidic, organic
decomposition also drives pH down early in a cycle. Should rise as bacterial activity increases.

**TDS note:** Reading ~150 ppm. Bottom of target range. Will rise as nitrogen compounds accumulate.

## What Toby should probably do (that hasn't happened yet)

- **Manual water test** — ammonia/nitrite/nitrate. It's been 10 days. We don't know where the cycle stands.
- **Consider adding plants** — especially fast-growing stem plants or Java moss. They compete with algae,
  provide surface area for biofilm (shrimp food), and absorb nitrogen compounds which can smooth the cycle.
  Good options for this tank: Java moss, Anubias barteri, Java fern, Hornwort (fast nitrogen absorber),
  Marimo moss ball. All are low-light tolerant, no CO2 required, shrimp-safe, and durable through a cycle.

## Sensor endpoints

- Latest: `GET http://localhost:5001/api/sensors/latest`
- History: `GET http://localhost:5001/api/sensors?limit=96`
- Events: `GET http://localhost:5001/api/events?limit=20`

## Skills you have

`call_toby` → `shrimp_alert` → `shrimp_monitor` → `shrimp_journal` → `daily_log` → `skill_writer` → `shrimp_vision` (stub)

Full specs in `skills/*/SKILL.md`.
