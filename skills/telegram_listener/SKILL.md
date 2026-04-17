# telegram-listener

Polls Telegram every 2min. Reads messages from owner chat only. Three message types handled.

---

## Message routing

```
update
  callback_query → handle_callback_query (approve/reject proposal buttons)
  photo          → handle_photo → shrimp_vision.process_photo → vision reply via call_toby
  text/caption   → handle_text
                   → classify_message (single Claude tool call)
                     event_type == "question" → answer_question → call_toby reply
                     else                     → post_event + ack via call_toby
```

## `classify_message`

Single Claude tool call. `CLASSIFY_TOOL` enum: `water_change`, `water_test`, `feeding`, `observation`, `heater_adjust`, `dosing`, `maintenance`, `plant_addition`, `shrimp_added`, `owner_note`, `question`.

Use `question` when owner asks about tank status, parameters, history, or advice. Use `owner_note` if intent unclear.

Returns `{event_type, notes, data}`. `data.source = "telegram"` always injected by `handle_text`.

## `answer_question`

Builds context from: latest reading, 24hr events, 7-day notable events (owner_photo excluded), journal tail, agent state. Calls Claude (no tool), max_tokens=500. Returns 2–3 sentence Telegram reply.

## Photo flow

`handle_photo` → `download_photo` → `save_photo` (snapshots/photos/YYYY-MM-DD_HH-MM-SS.jpg) → `process_photo` → `format_vision_reply` → `call_toby`.

Download failure: logs `owner_photo` event with `error: download_failed`, sends warning.

`format_vision_reply` outputs: caption (if present), shrimp count, water clarity, plant health, algae description (if visible), concerns, narrative.

## Proposal review (callback_query flow)

Inline buttons on proposal messages: approve / reject only (no edit flow).
- approve → `install_proposal` → copies run.py + SKILL.md to skills/{name}/, writes status.json
- reject → writes status.json as rejected

Proposals sent by `skill_writer` via `send_with_buttons` — no text-based state machine.

## State files

| File | Purpose |
|------|---------|
| `logs/telegram_offset.txt` | Last processed update_id + 1 |

## Dependencies

- `skills/call_toby/run.py` — `call_toby`, `send_with_buttons`
- `skills/shrimp_vision/run.py` — `process_photo`
- `utils.py` — `call_claude`, `fetch_events`, `fetch_latest_reading`, `fetch_notable_events`, `format_notable_events`, `format_recent_events`, `post_event`, `read_agent_state`, `read_journal`
- `config.py` — `get_cycle_day`, `PATHS`, `COLONY_START`
