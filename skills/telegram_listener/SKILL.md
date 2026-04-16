# telegram-listener

Polls Telegram every 2min. Reads messages from owner chat only. Three message types handled.

---

## Message routing

```
update
  callback_query → handle_callback_query (approve/reject/edit proposal buttons)
  photo          → handle_photo → shrimp_vision.process_photo → vision reply via call_toby
  text/caption   → handle_text
    pending_edit? → handle_edit_reply (proposal edit flow)
    is_question?  → answer_question (heuristic pre-filter — no Claude classify call)
    else          → classify_message (Claude tool call) → post_event + ack
```

## `is_question` heuristic

Runs before any Claude call. Routes to `answer_question` directly if:
- text ends with `?`
- text starts with: what / how / why / when / is / are / do / does / did / can / should / will

No LLM cost for obvious questions. Edge cases that slip through get classified as `owner_note`.

## `classify_message`

Single Claude tool call. `CLASSIFY_TOOL` enum: `water_change`, `water_test`, `feeding`, `observation`, `heater_adjust`, `dosing`, `maintenance`, `plant_addition`, `shrimp_added`, `owner_note`. No `question` type — routing handled upstream by heuristic.

Returns `{event_type, notes, data}`. `data.source = "telegram"` always injected by `handle_text`.

## `answer_question`

Builds context from: latest reading, 24hr events, 7-day notable events (owner_photo excluded), journal tail, agent state. Calls Claude (no tool), max_tokens=500. Returns 2–3 sentence Telegram reply.

## Photo flow

`handle_photo` → `download_photo` → `save_photo` (snapshots/photos/YYYY-MM-DD_HH-MM-SS.jpg) → `process_photo` → `format_vision_reply` → `call_toby`.

Download failure: logs `owner_photo` event with `error: download_failed`, sends warning.

## Proposal review (callback_query flow)

Inline buttons on proposal messages: approve / reject / edit.
- approve → `install_proposal` → copies run.py + SKILL.md to skills/{name}/
- reject → writes status.json
- edit → sets `state/pending_edit.json`, next text message → `handle_edit_reply` → `apply_edit_to_proposal` (Claude rewrites files) → re-sends proposal with buttons

## State files

| File | Purpose |
|------|---------|
| `logs/telegram_offset.txt` | Last processed update_id + 1 |
| `state/pending_edit.json` | Set when waiting for edit instructions; cleared after apply |

## Dependencies

- `skills/call_toby/run.py` — `call_toby`, `send_with_buttons`
- `skills/shrimp_vision/run.py` — `process_photo`
- `utils.py` — `call_claude`, `fetch_events`, `fetch_latest_reading`, `fetch_notable_events`, `format_notable_events`, `format_recent_events`, `post_event`, `read_agent_state`, `read_journal`
- `config.py` — `get_cycle_day`, `PATHS`, `COLONY_START`
