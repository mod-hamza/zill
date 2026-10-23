# RUNBOOK_DEMO

Everything here runs on `localhost` with no internet. Start servers about 10 minutes before you walk in.

## 1. Pre-flight checklist (in this order)

1. Laptop charged and plugged in; power mode set to performance; notifications off; screen sleep off.
2. Close other heavy apps. The film needs the GPU.
3. Start the servers (section 2). Wait for `Zill ready`.
4. Open `http://localhost:3000/health`. Every row green (backend, city data, shade assets, replay available, WebGL, frame rate). Amber on "Model reachable" is expected without an API key: the agent runs in recorded/scripted replay and says so on screen.
5. Browser: Chrome or Edge, zoom 100 %, no extensions, one tab. Open `http://localhost:3000/film`, press `F` for fullscreen, check the projector resolution and aspect ratio (open item) and that the text is legible from the back.
6. Press `Space` for 10 seconds to confirm it plays, then `1` to go back to chapter 1 and `Esc` to pause. Press `H` to confirm chrome hides and shows again.
7. Open `/app` once (press `A` in the film), click a hero chip, confirm routes and the Journey panel render, press Backspace to return.
8. Put the backup files on the desktop: `docs/deck_assets/backup_film.mp4`, `backup_app_demo.mp4`, and the stills folder `docs/deck_assets/stills/` (re-generate with `make record`; see section 6).
9. Know the time budget: the film is 13:00 at speed 1.0. `]` speeds up to 1.15x (about 11:20), `[` slows to 0.85x (about 15:20).

## 2. Start commands

| | With make | Without make |
| --- | --- | --- |
| First time on a machine | `make setup` | `python scripts/zill.py setup` |
| Demo (production build, recommended) | `make demo` | `python scripts/zill.py demo` |
| Dev servers with reload (not for the stage) | `make dev` | `python scripts/zill.py dev` |
| Tests | `make test` | `python scripts/zill.py test` |

Requirements: Python 3.11 via `uv`, Node 20+ with npm. `demo` builds the frontend, starts FastAPI on `:8000` and Next on `:3000`, and prints `Zill ready -> http://localhost:3000/film`. Stop with Ctrl+C in that terminal. If a port is busy, stop the old process first (the ports are fixed).

URLs: Film `http://localhost:3000/film`, App `http://localhost:3000/app`, health `http://localhost:3000/health`, hotel widget `http://localhost:3000/embed/hotel`, API docs `http://localhost:8000/docs`. Presenter strip: `/film?presenter=1`.

## 3. Keyboard shortcuts (Film)

| Key | Action |
| --- | --- |
| `Space` | start / pause autoplay |
| `[` / `]` | speed down / up in 0.05 steps, 0.85x to 1.15x |
| Left / Right | previous (or restart) / next chapter |
| `1`-`9`, `0`, `-`, `=` | jump to chapters 1-12 |
| `Esc` | pause |
| `F` | fullscreen |
| `T` | tiny elapsed-time and chapter indicator (hidden by default) |
| `H` | hide or show all UI chrome |
| `L` | toggle low-quality mode |
| `A` | go to `/app` keeping date and time (Backspace in `/app` returns to the film end) |

The scroll wheel also scrubs deterministically: the same position always renders the same frame.

## 4. If something fails

| Symptom | What to do |
| --- | --- |
| Backend not running or `/health` backend row red | The film needs the API for its data (scenarios, weather, route), so it will show "The film data could not be loaded" rather than play. Restart `make demo`. If it will not come back, play `backup_film.mp4`. |
| WebGL fails or the film is black/frozen | Press `L` for low quality; reload the page. If it persists, switch the browser to a discrete GPU, or play `backup_film.mp4` and show the stills. Note: an in-browser stills fallback (PRD 17.4) is not confirmed implemented; `frontend/public/stills/` is populated for it by `python scripts/zill.py deck`. |
| Frame rate drops mid-film | The scene auto-downgrades; you can also press `L`. Close other apps. |
| Agent live call fails or no key | Nothing to do. The agent falls back to replay automatically and the badge reads "Scripted session (live model not connected)" or "Recorded session". Free-text in replay answers with the recorded-session notice. Do not describe a replay as live. |
| No internet | Everything works. Weather uses recorded files (`data/weather_cache/`), the agent uses replay, fonts and models are self-hosted. |
| A number on screen looks wrong | Say "model estimate", then check `data/scenarios/hero.json`; the App's Journey panel for the same trip should match to the displayed precision. |
| App route request errors | Reload `/app`; check `http://localhost:8000/api/health`. |
| Judge asks to try their own trip | Press `A`, type two places in the command bar (gazetteer is local, 50 POIs), pick walk, read the three cards. |
| Need to cut time | Press `]` up to 1.15x, or jump chapters with the number keys (chapters 9-11 are the shortest to skip, but keep 10 "Does it work?"). |

## 5. Adding the LLM key and re-recording live sessions

1. Copy `.env.example` to `.env` and set `ZILL_LLM_API_KEY` (OpenAI-compatible Voke endpoint, `ZILL_LLM_BASE_URL=https://www.vokeapi.com/v1`). Never commit `.env`. Confirm `ZILL_MODEL` and `ZILL_MODEL_FAST` exist on the endpoint; `/api/health` reports the chosen id and `http://localhost:3000/health` should turn the model row green.
2. Re-record all four sessions with the real model: `backend/.venv/Scripts/python.exe scripts/record_replay.py --live` (macOS/Linux: `backend/.venv/bin/python`). Then `cd backend && .venv/Scripts/python.exe -m pytest -q tests/test_replay.py`.
3. Recorded files with `live: true` are badged "Recorded session"; scripted ones are badged "Scripted session". Check one in `/app` before the pitch.
4. Run `python scripts/zill.py record` again afterwards so the backup videos show the new sessions.

## 6. Re-recording weather on the day

`cd backend && .venv/Scripts/python.exe -m zill.weather.record` re-fetches Open-Meteo and rewrites `data/weather_cache/dubai_downtown_*.json` (the hackathon file is a forecast fetched 2026-10-22; refresh it on 2026-10-23 or 24). Needs internet once; afterwards the demo is offline again. The Film reads weather through `/api/weather`, so restart nothing, just reload.

## 7. Backup video, stills, deck assets

| Command | Produces |
| --- | --- |
| `python scripts/zill.py deck` | architecture PNG; 14 stills in `docs/deck_assets/stills/` and `frontend/public/stills/` (+ `manifest.json`) |
| `python scripts/zill.py record` | all of the above plus `backup_film.webm/.mp4` (realtime, about 13 minutes plus load) and `backup_app_demo.mp4` (about 100 s) |
| `python scripts/zill.py record --no-film` | skip the 13-minute film (quick refresh of stills + app video) |
| `python scripts/zill.py record --skip-build` | reuse the last `next build` |
| `cd frontend && npx tsx scripts/record-film.ts --crf 24` | smaller film file |

`record` builds the frontend and starts its own servers; if servers are already answering on `:8000`/`:3000` it reuses them and leaves them running. The film recording is H.264 at crf 20 and is large because of film grain (about 6.7 Mbit/s measured on a 30 s test, so expect roughly 600-700 MB for 13 minutes; use `--crf 24` for smaller). Open each still and the videos before the deck deadline; the recorder cannot judge composition. The app video shows whatever mode the agent is in; the on-screen badge keeps it honest.

Clean-clone check (needs ports free and everything committed): `python scripts/zill.py freshclone` clones the repo to a temp directory, runs setup and demo there, runs the Playwright specs, tears down, and prints PASS or FAIL. `--quick` runs only the smoke spec; `--keep` keeps the clone.

## 8. Run of show

Open `docs/SPEAKER_NOTES.md` on a second device. Start on chapter 1 paused. Press `Space` as you begin speaking. The chapter timings are nominal; the presenter strip (`?presenter=1`) shows elapsed against target. After chapter 12, take questions in `/app` (`A`).
