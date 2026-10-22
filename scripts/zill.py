#!/usr/bin/env python3
"""Zill task runner (stdlib only, cross-platform). Usage: python scripts/zill.py <command> [args]

Commands: setup, dev, demo, test, bake, record, lint
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


def cmd_record(_args: list) -> int:
    say("record: not implemented yet")
    return 0


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
    "lint": cmd_lint,
}


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        return 2
    return COMMANDS[sys.argv[1]](sys.argv[2:])


if __name__ == "__main__":
    sys.exit(main())
