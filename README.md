# Zill

*The AI agent that routes you through the shade.*

Zill builds a 3D model of a hot city from open data, computes where the sun's shadows fall at any minute of any day, and routes people through shade and air-conditioned links. This repository holds the engine and agent (Python, FastAPI), the cinematic film at `/film`, and the live app at `/app`.

## Prerequisites

- Python 3.11, provided through [uv](https://docs.astral.sh/uv/) (`uv venv --python 3.11` is run for you)
- Node 20 or newer, with npm
- GNU make is optional. Every make target is a thin wrapper around `python scripts/zill.py <target>`.

## Run it

| Goal | make | Without make |
| --- | --- | --- |
| Install everything | `make setup` | `python scripts/zill.py setup` |
| Dev servers with reload | `make dev` | `python scripts/zill.py dev` |
| Production build and serve | `make demo` | `python scripts/zill.py demo` |
| Run all tests | `make test` | `python scripts/zill.py test` |
| Bake a city from OpenStreetMap | `make bake` | `python scripts/zill.py bake` |
| Lint | `make lint` | `python scripts/zill.py lint` |
| Record backup video and stills | `make record` | `python scripts/zill.py record` |

`make demo` prints `Zill ready` once both servers answer. The film is at http://localhost:3000/film, the app at http://localhost:3000/app, and the pre-flight check at http://localhost:3000/health. The API runs on port 8000 and Next proxies `/api/*` to it.

## Configuration

Copy `.env.example` to `.env` and add `ZILL_LLM_API_KEY`. Without a key the agent runs in recorded replay mode.

## Documentation

All documents live in `docs/`: `CONTRACTS.md` (shared formats), `DECISIONS.md`, `PROGRESS.md`, `OPEN_ITEMS.md`, `ARCHITECTURE.md`, `VALIDATION.md`, `RUNBOOK_DEMO.md`, `PITCH_STORYBOARD.md` and `SPEAKER_NOTES.md`. The product spec is `PRD.md`.

Map data: &copy; OpenStreetMap contributors.
