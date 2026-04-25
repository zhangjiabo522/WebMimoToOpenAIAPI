# MiMo2API Project Summary

## Goal
- Build a Xiaomi MiMo AI to OpenAI compatible API proxy with management UI, tool_calls support, and clean streaming output

## Status: COMPLETE

## Core Features
- Port 9999, nohup background execution
- Real-time usage stats with auto-refresh every 5 seconds
- Support stream and non-stream responses
- Tabs UI: stats/chat/settings/accounts
- Auto-login with email verification
- Email notifications for expired accounts
- Account check scheduler
- Version tagging: v1.2.4

## API Endpoints
- `/v1/chat/completions` (stream + non-stream)
- `/v1/responses` (SSE streaming)
- `/v1/models`
- `/api/usage`, `/api/logs`, `/api/config`, `/api/check-now`, `/api/checker/start/stop`
- `/api/accounts`, `/api/account/login`, `/api/account/delete`

## Streaming Fix (key breakthrough)
- The `stream_response()` function now uses a `buffer` that accumulates SSE data
- After each SSE event: check if `buffer.count("<think>") == buffer.count("</think>")`
  - If open think tags exist (`opens > closes`): skip sending, accumulate more data
  - If all think tags closed (`opens == closes`): strip think content from buffer, send only clean content
  - When a think block closes, reset `sent_len` to 0 to avoid re-sending accumulated content
- `remove_think_tags()` uses regex `<think>.*?</think>` with DOTALL flag to strip think content
- This ensures think content is NEVER sent to clients, even if it arrives in multiple SSE events

## Non-Stream Fix
- Added `remove_think_tags(cleaned_content)` after `parse_tool_calls()` to strip think tags
- Removed think content prepending: `full_content = cleaned_content` (no more `<think>{think_content}</think>\n{cleaned_content}`)

## Other Fixes
- Fixed duplicate content by tracking `sent_len` properly and resetting when think block closes
- Fixed indentation errors in routes.py
- Fixed error chunk JSON formatting
- Removed `yield_content` helper (unused after rewrite)
- Fixed SSE parsing in `/v1/responses` endpoint to handle `event:` prefix format
- Removed debug print statements from mimo_client.py

## Relevant Files
- `/root/MiMo2API/app/routes.py`: API routes, `stream_response()`, `remove_think_tags()`, `yield_content()`
- `/root/MiMo2API/app/mimo_client.py`: SSE streaming, `call_api()`
- `/root/MiMo2API/app/utils.py`: `parse_tool_calls()`
- `/root/MiMo2API/app/frontend/`: HTML/JS UI

## Testing Results
- Streaming: 5 clean chunks, no duplicates, no think tags
- Non-stream: Clean response without think tags