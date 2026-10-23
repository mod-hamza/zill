# LLM providers (live agent)

The agent talks to any OpenAI Chat Completions endpoint through one module, `backend/zill/agent/llm.py`.
Providers are tried in the order of `ZILL_LLM_PROVIDERS` (default `opencode,voke`). A provider with no key
is skipped. With no key at all the app behaves exactly as before: labelled recorded replays, no live LLM.

## Configure

| Variable | Default | Meaning |
| --- | --- | --- |
| `ZILL_LLM_PROVIDERS` | `opencode,voke` | priority order |
| `ZILL_OPENCODE_API_KEY` | none | OpenCode Go key (Bearer) |
| `ZILL_OPENCODE_BASE_URL` | `https://opencode.ai/inference/go/openai/v1` | chat completions base |
| `ZILL_OPENCODE_MODEL` / `_MODEL_FAST` | `kimi-k3` / `glm-5.3-flash` | main / fast model |
| `ZILL_OPENCODE_FALLBACK_MODELS` | `kimi-k3.1-pro,glm-5.3,glm-5.3-flash` | tried in order if the model is unknown (404), empty, or rejected |
| `ZILL_OPENCODE_MODELS_URL` | `https://opencode.ai/inference/go/v1/models` | availability probe (separate from the chat base) |
| `ZILL_VOKE_API_KEY` / `_BASE_URL` / `_MODEL` / `_MODEL_FAST` | Voke values | legacy `ZILL_LLM_API_KEY`, `ZILL_LLM_BASE_URL`, `ZILL_MODEL`, `ZILL_MODEL_FAST` still work and mean `voke` |

Locally: copy `.env.example` to `.env`, set the key(s), run the API. On the VM: add the same lines to
`/home/hamza/zill/.env`, then run `deploy/cd.sh --force` so the container restarts with them. Never paste
a key into chat, a commit, or a log. `GET /api/health` and `GET /api/agent/status` report which provider and
model are live (`provider`, `model`, `providers[]`) and never contain a key.

## Behaviour

- Fallback on connect error, timeout, 5xx, 401/403 or 429: next provider. A failed provider sits out
  for 30 s. Inside a provider, an unknown model (404), an empty completion or a 400 moves to the next model.
- Tool calling tolerates `reasoning_content` (kept and echoed back only to OpenCode, stripped for others),
  `<think>` blocks, empty `content` with tool calls, arguments as JSON strings, fenced JSON, and models
  without `tool_choice` support (one retry without it).
- OpenCode requires a stable `x-opencode-session` header per conversation (the request is rejected with
  `MissingSessionID` otherwise; verified keyless on 2026-10-23, 400 without it, 401 with it and no key).
  `LLMClient.for_session(session_id)` returns a view that sends that id; the default is a per-process id.
  Every request also sends `User-Agent: Zill-hackathon-prototype/0.1`.
- `chat(..., model="fast")` selects each provider's fast model.

## Models and cost (OpenCode Go page, 2026-10-23)

Go is $10/month and Go Plus $40/month, flat. Usage is capped as monthly dollar amounts per model
(5-hour 20%, weekly 50%, monthly 100% of that cap). Prices per 1M tokens (input / output):
Kimi K3 $3.00 / $15.00 (monthly cap $15 on the page's Go column), Kimi K3.1 Pro $2.00 / $10.00 ($15),
GLM-5.3 $1.40 / $4.40 ($15), GLM-5.3-Flash $0.15 / $0.50 ($60), DeepSeek V4.1 Flash $0.15-0.30 / $0.60-1.20
($80), LongCat 2.5 Preview free. Check https://opencode.ai/docs/go/ for the current table and the Go Plus caps.
DeepSeek models need the Global region. No replays were re-recorded tonight (no key available).
