#!/usr/bin/env python3
"""Zill task runner (stdlib only, cross-platform). Usage: python scripts/zill.py <command> [args]

Commands: setup, dev, demo, test, bake, record, deck, freshclone, lint
"""

from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

# Windows consoles default to cp1252; a single non-Latin character in server output must not
# kill the log-pump thread (a dead pump stops draining the pipe and stalls the server).
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(errors="replace")  # type: ignore[union-attr]
    except AttributeError:
        pass

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
IS_WIN = os.name == "nt"
VENV_PY = BACKEND / ".venv" / ("Scripts/python.exe" if IS_WIN else "bin/python")
NPM = "npm.cmd" if IS_WIN else "npm"
NPX = "npx.cmd" if IS_WIN else "npx"
API_PORT = 8000
WEB_PORT = 3000


def say(msg: str) -> None:
    print(f"[zill] {msg}", flush=True)


def rel(p: Path) -> str:
    try:
        return str(p.relative_to(ROOT)) or "."
    except ValueError:
        return str(p)


def run(cmd: list, cwd: Path = ROOT, check: bool = True) -> int:
    say("$ " + " ".join(str(c) for c in cmd) + f"   (in {rel(cwd)})")
    rc = subprocess.call([str(c) for c in cmd], cwd=str(cwd))
    if check and rc != 0:
        say(f"command failed with exit code {rc}")
        sys.exit(rc)
    return rc


def need_venv() -> None:
    if not VENV_PY.exists():
        say("backend venv missing. Run: python scripts/zill.py setup")
        sys.exit(1)


# --- setup ---------------------------------------------------------------------------------------
def cmd_setup(_args: list) -> int:
    uv = shutil.which("uv")
    if not VENV_PY.exists():
        if not uv:
            say("uv not found. Install it from https://docs.astral.sh/uv/ (it provides Python 3.11).")
            return 1
        say("1/4 creating Python 3.11 venv")
        run([uv, "venv", "--python", "3.11", BACKEND / ".venv"])
    else:
        say("1/4 venv already present")
    say("2/4 installing backend[dev]")
    spec = f"{BACKEND}[dev]"
    if uv:
        run([uv, "pip", "install", "--python", VENV_PY, "-e", spec])
    else:
        run([VENV_PY, "-m", "pip", "install", "-e", spec])
    say("3/4 installing frontend packages")
    run([NPM, "ci" if (FRONTEND / "package-lock.json").exists() else "install"], cwd=FRONTEND)
    say("4/4 installing Playwright chromium")
    run([NPX, "playwright", "install", "chromium"], cwd=FRONTEND, check=False)
    say("setup complete")
    return 0


# --- process helpers -----------------------------------------------------------------------------
def spawn(prefix: str, cmd: list, cwd: Path) -> subprocess.Popen:
    say(f"starting {prefix}: {' '.join(str(c) for c in cmd)}")
    kwargs: dict = {}
    if IS_WIN:
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    p = subprocess.Popen(
        [str(c) for c in cmd],
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        **kwargs,
    )

    def pump() -> None:
        assert p.stdout is not None
        for line in p.stdout:
            print(f"[{prefix}] {line.rstrip()}", flush=True)

    threading.Thread(target=pump, daemon=True).start()
    return p


def kill_tree(p: subprocess.Popen) -> None:
    if p.poll() is not None:
        return
    try:
        if IS_WIN:
            subprocess.call(
                ["taskkill", "/T", "/F", "/PID", str(p.pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            os.killpg(os.getpgid(p.pid), signal.SIGTERM)
    except Exception:
        p.kill()


def supervise(procs: list) -> int:
    try:
        while True:
            for p in procs:
                if p.poll() is not None:
                    say(f"a child exited with code {p.returncode}; shutting down")
                    return p.returncode or 1
            time.sleep(0.5)
    except KeyboardInterrupt:
        say("Ctrl+C: stopping")
        return 0
    finally:
        for p in procs:
            kill_tree(p)


def http_ok(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=3) as r:
            return 200 <= r.status < 400
    except Exception:
        return False


def uvicorn_cmd(reload: bool) -> list:
    cmd = [VENV_PY, "-m", "uvicorn", "zill.api.main:app", "--port", str(API_PORT), "--host", "127.0.0.1"]
    if reload:
        cmd.append("--reload")
    return cmd


# --- dev / demo ----------------------------------------------------------------------------------
def cmd_dev(_args: list) -> int:
    need_venv()
    procs = [spawn("api", uvicorn_cmd(True), BACKEND), spawn("web", [NPM, "run", "dev"], FRONTEND)]
    say(f"dev servers: http://localhost:{WEB_PORT}/film  (api on :{API_PORT})")
    return supervise(procs)


def cmd_demo(_args: list) -> int:
    need_venv()
    say("building frontend")
    run([NPM, "run", "build"], cwd=FRONTEND)
    procs = [spawn("api", uvicorn_cmd(False), BACKEND), spawn("web", [NPM, "run", "start"], FRONTEND)]

    def waiter() -> None:
        deadline = time.time() + 120
        while time.time() < deadline:
            if http_ok(f"http://127.0.0.1:{API_PORT}/api/health") and http_ok(
                f"http://localhost:{WEB_PORT}/film"
            ):
                say(f"Zill ready -> http://localhost:{WEB_PORT}/film")
                return
            time.sleep(1)
        say("timed out waiting for servers")

    threading.Thread(target=waiter, daemon=True).start()
    return supervise(procs)


# --- test ----------------------------------------------------------------------------------------
def parse_pytest(xml_path: Path) -> dict:
    root = ET.parse(xml_path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    tests = sum(int(s.get("tests", 0)) for s in suites)
    bad = sum(int(s.get("failures", 0)) + int(s.get("errors", 0)) for s in suites)
    skipped = sum(int(s.get("skipped", 0)) for s in suites)
    return {"passed": tests - bad - skipped, "failed": bad}


def capture(cmd: list, cwd: Path) -> tuple:
    say("$ " + " ".join(str(c) for c in cmd) + f"   (in {rel(cwd)})")
    p = subprocess.run(
        [str(c) for c in cmd],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    out = (p.stdout or "") + (p.stderr or "")
    print(out, flush=True)
    return p.returncode, out


def cmd_test(_args: list) -> int:
    need_venv()
    failed = False
    summary: dict = {"backend": {"passed": 0, "failed": 0}, "frontend": {"passed": 0, "failed": 0}}

    say("backend: pytest")
    xml = Path(tempfile.gettempdir()) / "zill_pytest.xml"
    if xml.exists():
        xml.unlink()
    rc = run([VENV_PY, "-m", "pytest", "-q", f"--junitxml={xml}"], cwd=BACKEND, check=False)
    if xml.exists():
        summary["backend"] = parse_pytest(xml)
    failed |= rc != 0

    say("frontend: typecheck")
    failed |= run([NPM, "run", "typecheck"], cwd=FRONTEND, check=False) != 0
    say("frontend: lint")
    failed |= run([NPM, "run", "lint"], cwd=FRONTEND, check=False) != 0
    say("frontend: vitest")
    rc, out = capture([NPM, "run", "test"], FRONTEND)
    failed |= rc != 0
    m = re.search(r"Tests\s+(?:(\d+) failed\s*\|\s*)?(\d+) passed", out)
    if m:
        summary["frontend"] = {"passed": int(m.group(2)), "failed": int(m.group(1) or 0)}
    elif rc != 0:
        summary["frontend"]["failed"] = 1

    summary["ts"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    out_path = ROOT / "data" / "test_results.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    say(f"wrote {rel(out_path)}: {json.dumps(summary)}")
    say("TESTS FAILED" if failed else "all tests passed")
    return 1 if failed else 0


# --- bake / record / lint ------------------------------------------------------------------------
def cmd_bake(args: list) -> int:
    need_venv()
    return run([VENV_PY, "-m", "zill.data.bake", *args], cwd=BACKEND, check=False)


DECK_DIR = ROOT / "docs" / "deck_assets"


def tsx(script: str, *args: str) -> int:
    """Run a frontend/scripts/*.ts tool with tsx (Playwright based)."""
    return run([NPX, "tsx", f"scripts/{script}", *args], cwd=FRONTEND, check=False)


class DemoServers:
    """Context manager: (build and) start FastAPI + Next in production mode; reuse servers that
    are already answering (and then leave them running); stop only what it started."""

    def __init__(self, build: bool = True) -> None:
        self.build = build
        self.procs: list = []

    def __enter__(self) -> "DemoServers":
        need_venv()
        api_up = http_ok(f"http://127.0.0.1:{API_PORT}/api/health")
        web_up = http_ok(f"http://localhost:{WEB_PORT}/film")
        if api_up and web_up:
            say("servers already running on :8000/:3000 - reusing them (will not stop them)")
            return self
        if api_up or web_up:
            raise RuntimeError("only one of :8000/:3000 is answering; free the ports and retry")
        if self.build:
            say("building frontend")
            run([NPM, "run", "build"], cwd=FRONTEND)
        self.procs = [spawn("api", uvicorn_cmd(False), BACKEND), spawn("web", [NPM, "run", "start"], FRONTEND)]
        deadline = time.time() + 120
        while time.time() < deadline:
            if http_ok(f"http://127.0.0.1:{API_PORT}/api/health") and http_ok(f"http://localhost:{WEB_PORT}/film"):
                say("servers ready")
                return self
            for p in self.procs:
                if p.poll() is not None:
                    code = p.returncode
                    self.__exit__(None, None, None)
                    raise RuntimeError(f"a server exited early with code {code}")
            time.sleep(1)
        self.__exit__(None, None, None)
        raise RuntimeError("timed out waiting for servers")

    def __exit__(self, *_exc: object) -> None:
        for p in self.procs:
            kill_tree(p)
        if self.procs:
            say("servers stopped")
        self.procs = []


def render_architecture() -> int:
    """docs/deck_assets/architecture.svg -> architecture.png (Playwright screenshot of the SVG)."""
    svg = DECK_DIR / "architecture.svg"
    if not svg.exists():
        say(f"missing {rel(svg)}")
        return 1
    return tsx("render-svg.ts", str(svg), str(DECK_DIR / "architecture.png"))


def parse_flags(args: list) -> dict:
    out: dict = {}
    i = 0
    while i < len(args):
        a = args[i]
        if a.startswith("--"):
            k = a[2:]
            if i + 1 < len(args) and not args[i + 1].startswith("--"):
                out[k] = args[i + 1]
                i += 1
            else:
                out[k] = True
        i += 1
    return out


def cmd_deck(args: list) -> int:
    """Architecture PNG + Film stills -> docs/deck_assets/stills and frontend/public/stills."""
    f = parse_flags(args)
    rc = render_architecture()
    try:
        with DemoServers(build=not f.get("skip-build")):
            rc |= tsx("export-deck-assets.ts", *(["--swiftshader"] if f.get("swiftshader") else []))
    except RuntimeError as e:
        say(f"deck failed: {e}")
        return 1
    return 1 if rc else 0


def cmd_record(args: list) -> int:
    """build -> demo servers -> deck stills -> film video -> app video -> stop servers (PRD 17.6).
    Flags: --skip-build, --no-film, --no-app, --no-stills, --swiftshader, --film-rate N (smoke only)."""
    f = parse_flags(args)
    sw = ["--swiftshader"] if f.get("swiftshader") else []
    rc = render_architecture()
    DECK_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with DemoServers(build=not f.get("skip-build")):
            if not f.get("no-stills"):
                rc |= tsx("export-deck-assets.ts", *sw)
            if not f.get("no-film"):
                extra = ["--rate", str(f["film-rate"])] if f.get("film-rate") else []
                rc |= tsx("record-film.ts", *sw, *extra)
            if not f.get("no-app"):
                rc |= tsx("record-app.ts", *sw)
    except RuntimeError as e:
        say(f"record failed: {e}")
        return 1
    for n in ("backup_film.mp4", "backup_film.webm", "backup_app_demo.mp4", "architecture.png"):
        p = DECK_DIR / n
        size = f" ({p.stat().st_size / 1e6:.1f} MB)" if p.exists() else ""
        say(f"{'ok     ' if p.exists() else 'MISSING'} {rel(p)}{size}")
    stills = sorted((DECK_DIR / "stills").glob("*.png"))
    say(f"{len(stills)} stills in {rel(DECK_DIR / 'stills')}")
    return 1 if rc else 0


def _rmtree(path: Path) -> None:
    def onerr(func, p, _exc):  # read-only files on Windows
        try:
            os.chmod(p, 0o700)
            func(p)
        except Exception:
            pass

    shutil.rmtree(path, onerror=onerr)


def cmd_freshclone(args: list) -> int:
    """Clone the repo (committed state only) to a temp dir, setup + demo there, run the Playwright
    smoke against it, tear down, print PASS/FAIL. Never touches the working copy. Needs :3000/:8000 free.
    Flags: --quick (smoke.spec only), --keep (keep the clone)."""
    f = parse_flags(args)
    results: list = []

    def check(name: str, ok: bool, detail: str = "") -> bool:
        results.append((name, ok, detail))
        say(f"{'PASS' if ok else 'FAIL'}  {name} {detail}")
        return ok

    if http_ok(f"http://127.0.0.1:{API_PORT}/api/health") or http_ok(f"http://localhost:{WEB_PORT}/film"):
        say("FAIL: ports 8000/3000 are in use. Stop the running servers first (the clone must bind them).")
        return 1
    dirty = subprocess.run(
        ["git", "status", "--porcelain"], cwd=str(ROOT), capture_output=True, text=True
    ).stdout.strip()
    if dirty:
        say(
            f"warning: {len(dirty.splitlines())} uncommitted change(s) in the working copy are NOT in the "
            "clone - commit first for a faithful test"
        )
    tmp = Path(tempfile.mkdtemp(prefix="zill-fresh-"))
    clone = tmp / "zill"
    demo = None
    try:
        rc = subprocess.call(["git", "clone", "--quiet", "--local", str(ROOT), str(clone)])
        if not check("git clone", rc == 0):
            return 1
        py = sys.executable
        setup_rc = subprocess.call([py, str(clone / "scripts" / "zill.py"), "setup"], cwd=str(clone))
        if not check("setup (venv, backend, npm ci, playwright)", setup_rc == 0):
            return 1
        demo = spawn("demo", [py, str(clone / "scripts" / "zill.py"), "demo"], clone)
        deadline = time.time() + 420
        up = False
        while time.time() < deadline:
            if demo.poll() is not None:
                break
            if http_ok(f"http://127.0.0.1:{API_PORT}/api/health") and http_ok(f"http://localhost:{WEB_PORT}/film"):
                up = True
                break
            time.sleep(2)
        if not check("demo servers up", up, "" if up else "(build failed or timed out)"):
            return 1
        for path in ("/film", "/app", "/health", "/api/health", "/api/scenarios/dubai_downtown", "/api/cities"):
            check(f"GET {path}", http_ok(f"http://localhost:{WEB_PORT}{path}"))
        e2e = [NPX, "playwright", "test", "--reporter=line"] + (["e2e/smoke.spec.ts"] if f.get("quick") else [])
        e2e_rc = subprocess.call(e2e, cwd=str(clone / "frontend"))
        check("playwright smoke" + (" (quick)" if f.get("quick") else ""), e2e_rc == 0)
    finally:
        if demo is not None:
            kill_tree(demo)
        time.sleep(2)
        if f.get("keep"):
            say(f"kept clone at {tmp}")
        else:
            _rmtree(tmp)
    ok = all(r[1] for r in results)
    summary = ", ".join(f"{n}:{'ok' if o else 'FAIL'}" for n, o, _ in results)
    say(f"FRESHCLONE {'PASS' if ok else 'FAIL'}  ({summary})")
    return 0 if ok else 1


def cmd_lint(_args: list) -> int:
    need_venv()
    rc = run([VENV_PY, "-m", "ruff", "check", "."], cwd=BACKEND, check=False)
    rc |= run([NPM, "run", "lint"], cwd=FRONTEND, check=False)
    return 1 if rc else 0


COMMANDS = {
    "setup": cmd_setup,
    "dev": cmd_dev,
    "demo": cmd_demo,
    "test": cmd_test,
    "bake": cmd_bake,
    "record": cmd_record,
    "deck": cmd_deck,
    "freshclone": cmd_freshclone,
    "lint": cmd_lint,
}


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        return 2
    return COMMANDS[sys.argv[1]](sys.argv[2:])


if __name__ == "__main__":
    sys.exit(main())
