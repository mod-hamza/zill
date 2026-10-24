# Costs (Zill & Shams)

Every figure is either measured (method stated) or labelled as an assumption. Prices we could not verify are
stated as not priced. Measured 2026-10-23; VPS price added 2026-10-24 (team).

## 1. Fixed cost: the VPS

- Contabo VPS plan price: `$6.93 per month` (team, 2026-10-24; 4 vCPU AMD EPYC, 8 GB RAM per `nproc` / `free` on the VM). The VM is shared with other apps (n8n stack, Caddy),
  so the real marginal cost of Zill is a fraction of it.
- Domain: itshamza.me already owned; `zill.` is a subdomain, so marginal cost is zero.
- TLS: Caddy automatic certificates, free.
- Map, building and tree data: OpenStreetMap (ODbL, free; attribution required). Weather: Open-Meteo (free tier, non-commercial;
  a paid commercial plan (API Standard, 1M calls per month; price shown at checkout, not published) is needed before B2B revenue; source https://open-meteo.com/en/pricing, which lists the free tier as non-commercial, 300,000 calls per month).

## 2. LLM cost per agent conversation

### Method

The recorded replays in `backend/replay/*.json` store UI events, not the messages sent to a model, and they were
recorded by the **scripted planner** (`live: false`, model `zill-scripted-planner`), not a real LLM. So token counts
were measured one level deeper: the real orchestrator was run in-process for the three hero scenarios with the
scripted planner wrapped to capture everything passed to `llm.chat(...)` (system prompt, growing message history
with real `model_view` tool results, the tool schema, and the narrator and verifier calls). Characters were
converted to tokens at **4 characters per token** (a common approximation for English/JSON; real tokenizers of
Kimi, GLM or DeepSeek will differ, plausibly by +-25%, and the JSON-heavy input skews toward more tokens per
character). No tokenizer package was installed.

### Measured (characters / 4)

| Scenario | LLM requests | Input tokens (sum over requests) | Output tokens (scripted) |
| --- | --- | --- | --- |
| tourist_walk | 8 | about 24,400 | about 520 |
| rider_cycle | 7 | about 19,100 | about 460 |
| crew_shuttle | 11 | about 47,400 | about 810 |
| mean | 8.7 | about 30,300 | about 600 |

Caveat: the scripted planner writes terse outputs. A real model will emit more output tokens (and reasoning models
bill hidden reasoning as output). Treat output as a lower bound; input is the reliable part. The `replan_demo`
replay reuses the tourist scenario plus monitoring and adds no extra model calls in this measurement.

### Price under OpenCode Go (flat subscription)

Source: https://opencode.ai/docs/go/ , read 2026-10-23. Go is **$10/month**, Go Plus **$40/month**. Each model has a
monthly dollar limit and the page lists estimated requests per month "based on typical usage". We did not find a
published per-token price there, so we use the page's own request estimates. Conversations per month =
requests per month / 8.7 requests per conversation (assumption: our request size is similar to the "typical" one
behind the estimate; our requests average about 3,500 input tokens, which may be larger than typical, so these
counts could be optimistic).

| Model | Go requests/mo | Conversations/mo on Go | on Go Plus | Implied $/conversation at the plan limit |
| --- | --- | --- | --- | --- |
| kimi-k3 | 490 | about 56 | about 225 | $0.27 |
| kimi-k3.1-pro | 735 | about 84 | about 338 | $0.18 |
| glm-5.3 | 1,080 | about 124 | about 993 | $0.12 |
| deepseek-v4-pro | 5,200 | about 598 | about 2,391 | $0.025 |
| minimax-m3.1-flash | 19,380 | about 2,228 | about 8,910 | $0.009 |
| glm-5.3-flash | 31,580 | about 3,630 | about 10,890 | $0.017 |
| deepseek-v4.1-flash | 173,330 | about 19,900 | about 39,800 | $0.004 |

"Implied $/conversation" = the model's monthly dollar limit / requests per month x 8.7. It is the value of the
quota consumed, not an invoice: under the subscription the marginal cost of a conversation is $0 until the limit
is hit, then calls fail (the provider fallback in `docs/LLM.md` moves to the next provider).

**Reading:** a demo or pilot on Go with `glm-5.3-flash` or `deepseek-v4.1-flash` covers thousands of
conversations per month for $10. The strongest model on the plan (`kimi-k3`) covers only about 56. A B2B product
needs either Go Plus with a flash model for routine turns, or per-token API pricing, which we have not priced because we run on the flat subscription.

### Price under Voke (current default)

Not priced: we run on the flat OpenCode Go subscription, not per token. With the measured 30,300 input and about 600 output tokens per
conversation: cost = 30,300 x price_in + 600 x price_out (times roughly 1.5 to 3 for a real model's longer output).

## 3. Cost to add a city

Measured from existing logs (dev machine, Intel i7-13700HX; not the VM):

- **Data bake (Dubai):** 7.5 s of compute (`meta.json` diagnostics `wall_s`, steps: buildings, heights, graph,
  covered links, write). This figure excludes network time because the Overpass responses were already cached
  locally. Fetching a new city from Overpass is network-bound: the Oslo bake log (`data/raw/logs/oslo_bake.log`)
  shows repeated 502/504 retries across at least 13 minutes (22:30 to 22:43 on 2026-10-23, run still going when read).
- **Shade bake:** 487.5 s for four dates (316 steps) for Dubai, about 120 s per date and about 1.5 s per step
  (`data/raw/logs/shade_bake.log`).
- **Disk:** Dubai is 39 MB (29 MB of shade PNGs).
- **Money:** open data is free; Overpass is a shared service with fair-use limits (no cost, but no SLA). Realistic
  elapsed time to add a city: under one hour of unattended compute plus a few hours to check results (height data
  quality, landmark POIs). We have not measured person-time for QA.

## 4. Capacity and cost per 1,000 users

Load-test results (`scripts/loadtest.py`; mix 25% city list, 15% sun, 35% route, 15% departure, 10% health; virtual
users think 0.2 to 0.8 s between requests; single uvicorn worker, no rate limit):

**Local machine** (production-mode API on :8010, same host as the load generator):

| Concurrent users | Requests | Req/s | p50 | p95 | 429 | Errors |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 34 | 1.7 | 21 ms | 135 ms | 0 | 0 |
| 2 | 71 | 3.4 | 28 ms | 128 ms | 0 | 0 |
| 5 | 186 | 8.9 | 28 ms | 158 ms | 0 | 0 |
| 10 | 358 | 17.4 | 43 ms | 207 ms | 0 | 0 |
| 20 | 560 | 26.4 | 224 ms | 596 ms | 0 | 0 |
| 40 | 378 | 17.1 | 1,723 ms | 2,604 ms | 0 | 0 |

20 s per level. Throughput peaks near 26 req/s at 20 concurrent users and then falls: past that the single worker
saturates and latency queues up (no errors, but p95 above 2.5 s at 40). Other overnight jobs shared this machine, so
treat the numbers as indicative.

**Live VM** (https://zill.itshamza.me, read-only mix, 12 s per level, 48 s total, max 20 concurrent; latency includes
the network round trip from the test machine, and the live site at that time did not yet have the rate limiter):

| Concurrent users | Requests | Req/s | p50 | p95 | 429 | Errors |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 15 | 1.2 | 245 ms | 620 ms | 0 | 0 |
| 5 | 75 | 5.9 | 222 ms | 758 ms | 0 | 0 |
| 10 | 133 | 10.4 | 323 ms | 1,048 ms | 0 | 0 |
| 20 | 223 | 16.9 | 540 ms | 1,607 ms | 0 | 0 |

Raw results: `data/raw/logs/loadtest-local.json`, `data/raw/logs/loadtest-live.json`. The VM has 4 vCPU and 8 GB RAM
($6.93 per month); the live run did not reach the saturation point (20 concurrent was the agreed cap).

### Cost per 1,000 users (assumptions labelled)

- Assumption A: one visit makes about 20 API requests (city list, a few shade tiles, 2 to 3 routes, 1 departure).
  Not measured; change it to fit analytics once there are any.
- Assumption B: 10% of visits use the agent, 1 conversation each (8.7 LLM requests).
- Compute: 1,000 visits x 20 requests = 20,000 requests. At the local saturated rate of 26 req/s that is about
  770 s of one worker, which is 0.03% of a month (770 s / 2.63 million s). So the VPS share is
  **P x 0.0003** where P = $6.93 per month, i.e. **about $0.002 per 1,000 users**. The static shade tiles and the 3D scene
  are served by Caddy and Next, not counted here.
- LLM: 100 conversations. On Go with `glm-5.3-flash` that is inside a single month's quota (about 3,630 conversations),
  so marginal cost is $0 and the fixed cost is $10 per month. On `kimi-k3` it would exceed the Go quota after 56.
  Per-token pricing alternative: 100 x (30,300 x price_in + 600 x price_out); not priced, since we use the flat subscription.
- Total fixed cost today: $6.93 (VPS, shared) + $10 (OpenCode Go) = **about $17 per month**, which covers
  thousands of visits under the assumptions above. Per 1,000 users that is about $0.002 of server plus $0 of LLM
  inside the Go quota.
- Practical conclusion from the data: the first bottleneck is the single API worker (about 26 req/s for this mix), not
  money. The second is the LLM monthly quota if the agent is used heavily.
