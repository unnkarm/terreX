---
name: ollama-chat-agent
description: Architecture and extension guide for the TerreX Ollama-backed analyst chat agent. Use this skill when working on the chat agent, changing the Ollama model, modifying the system prompt, adding new chat tools/intents, or debugging chat availability.
---

# Ollama Chat Agent

## When to Use
- Working on `services/chat_agent.py` or `api/routes_chat.py`
- Changing the LLM model, system prompt, or intent handlers
- Debugging why chat is unavailable or returning wrong results

## Design Principles
- **Grounded**: Every factual claim queries TerreX DB before answering. No hallucination.
- **RAM-aware**: `ram_available()` checks free memory. If below `CHAT_SAFE_THRESHOLD_GB=1.5` ? 503, don't load model.
- **Auto-unload**: LLM unloads after `CHAT_IDLE_TIMEOUT_SECONDS=120` of inactivity to free RAM for AI inference.
- **Optional**: If Ollama not running ? `GET /api/system/status` reports `chat_available: false`. Other features unaffected.

## Key Config
`CHAT_MODEL=qwen2.5:1.5b` · `OLLAMA_BASE_URL=http://localhost:11434` · `CHAT_SAFE_THRESHOLD_GB=1.5` · `CHAT_IDLE_TIMEOUT_SECONDS=120`
Max history: 8 turns per session (in-memory `_conversation_history` dict).

## API Endpoints
`POST /api/chat/message` · `GET /api/chat/status` · `DELETE /api/chat/session`

## Staging Ollama Offline
```bash
docker pull ollama/ollama:latest
docker compose --profile chat up -d ollama
docker exec terrex-ollama ollama pull qwen2.5:1.5b-instruct-q4_K_M
docker exec terrex-ollama ollama list   # verify cached
```

## Changing the Model
1. Update `CHAT_MODEL` in `.env`
2. Pull model: `docker exec terrex-ollama ollama pull <model>`
3. Adjust `CHAT_SAFE_THRESHOLD_GB` if new model needs more RAM
4. `docker compose restart backend`

## Adding a New Intent
1. Add pattern to `_detect_intent()` in `chat_agent.py`
2. Write handler `_handle_<intent>(session_id, query, ...)` — always query DB first for grounding
3. Return `{"message": str, "data": dict, "intent": str}`

## Availability Check Pattern
```python
from services.chat_agent import is_chat_available
if not is_chat_available():
    return JSONResponse(status_code=503, content={"detail": "Chat unavailable"})
```
