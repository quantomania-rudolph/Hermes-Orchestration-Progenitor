#!/usr/bin/env python3
"""
NoLlama + Qwen readiness: audit Hermes backend and auto-repair LOCAL issues only.

Default fix mode never downloads anything — safe on spotty internet.
Network-heavy steps (--install, --pip) must be passed explicitly when online.

  python scripts/run_intel_gpu/nollama_setup.py              # local fix: ports + start server
  python scripts/run_intel_gpu/nollama_setup.py --check      # audit only, no changes
  python scripts/run_intel_gpu/nollama_setup.py --warmup     # local fix + localhost chat warmup
  python scripts/run_intel_gpu/nollama_setup.py --install    # ONLINE: clone/model/venv install
  python scripts/run_intel_gpu/nollama_setup.py --pip        # ONLINE: pip install Hermes deps

Typical flow after reboot (offline-safe):
  scripts\\run_intel_gpu\\03_daily_setup.bat
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

HERMES_DIR = Path(__file__).resolve().parents[2]
RUN_INTEL_GPU = Path(__file__).resolve().parent
INSTALL_MODELS = HERMES_DIR / "scripts" / "install_models"
sys.path.insert(0, str(HERMES_DIR))

from hermes_config import (  # noqa: E402
    HERMES_CHAT_MODEL_DEFAULT,
    NOLLAMA_HEALTH_URL,
    NOLLAMA_HOME,
    NOLLAMA_OPENAI_BASE_URL,
)
from hermes_nollama import nollama_health, resolve_chat_model  # noqa: E402

REQUESTED_MODEL = os.environ.get("HERMES_CHAT_MODEL", HERMES_CHAT_MODEL_DEFAULT)
MIN_MODEL_BIN_BYTES = 100 * 1024 * 1024
HERMES_PACKAGES = (
    ("numpy", "numpy"),
    ("openai", "openai"),
    ("sentence_transformers", "sentence-transformers"),
)
PORTS = (8000, 11434)
HEALTH_RETRIES = 5
HEALTH_RETRY_SLEEP_S = 3


@dataclass
class StepResult:
    name: str
    status: str  # OK | WARN | FAIL | FIX
    detail: str = ""


@dataclass
class Audit:
    steps: list[StepResult] = field(default_factory=list)
    fixes_applied: list[str] = field(default_factory=list)

    def add(self, name: str, status: str, detail: str = "") -> None:
        self.steps.append(StepResult(name, status, detail))
        tag = {"OK": "[OK]", "WARN": "[WARN]", "FAIL": "[FAIL]", "FIX": "[FIX]"}.get(status, status)
        print(f"{tag} {name}")
        for line in detail.splitlines():
            if line:
                print(f"      {line}")

    @property
    def failed(self) -> bool:
        return any(s.status == "FAIL" for s in self.steps)


def _fetch_json(url: str, timeout: float = 8.0) -> dict | list | None:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None


def _wait_for_health(*, wait_seconds: int = 120) -> dict | None:
    """Poll localhost health; tolerates slow model load, not internet."""
    deadline = time.time() + wait_seconds
    while time.time() < deadline:
        health = nollama_health()
        if health is not None:
            return health
        time.sleep(HEALTH_RETRY_SLEEP_S)
    return None


def _probe_health_with_retries() -> dict | None:
    for attempt in range(1, HEALTH_RETRIES + 1):
        health = nollama_health()
        if health is not None:
            return health
        if attempt < HEALTH_RETRIES:
            time.sleep(HEALTH_RETRY_SLEEP_S)
    return None


def _port_listeners() -> dict[int, list[int]]:
    """Return {port: [pid, ...]} for LISTENING sockets on Windows."""
    result: dict[int, list[int]] = {p: [] for p in PORTS}
    try:
        proc = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return result

    for line in proc.stdout.splitlines():
        if "LISTENING" not in line:
            continue
        match = re.search(r":(\d+)\s+.*LISTENING\s+(\d+)\s*$", line.strip())
        if not match:
            continue
        port, pid = int(match.group(1)), int(match.group(2))
        if port in result and pid > 0:
            result[port].append(pid)
    return result


def _process_name(pid: int) -> str:
    try:
        proc = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        line = proc.stdout.strip().splitlines()
        if not line or "No tasks" in line[0]:
            return ""
        return line[0].split(",")[0].strip('"').lower()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def _model_cache_valid(model_dir: Path) -> bool:
    if not model_dir.is_dir():
        return False
    for name in ("openvino_model.bin", "openvino_language_model.bin"):
        candidate = model_dir / name
        if candidate.is_file() and candidate.stat().st_size > MIN_MODEL_BIN_BYTES:
            return True
    return False


def _nollama_home() -> Path:
    return Path(os.environ.get("NOLLAMA_HOME", NOLLAMA_HOME))


def _pwsh() -> list[str]:
    if shutil.which("pwsh"):
        return ["pwsh", "-NoProfile", "-ExecutionPolicy", "Bypass"]
    return ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass"]


def check_install(audit: Audit) -> bool:
    home = _nollama_home()
    ok = True

    if not (home / "nollama.py").is_file():
        audit.add(
            "NoLlama clone",
            "FAIL",
            f"Missing {home / 'nollama.py'}\n"
            "Run: scripts\\install_models\\01_clone_nollama_repo.bat",
        )
        ok = False
    else:
        audit.add("NoLlama clone", "OK", str(home))

    venv_python = home / "venv" / "Scripts" / "python.exe"
    if not venv_python.is_file():
        audit.add(
            "NoLlama venv",
            "FAIL",
            f"Missing {venv_python}\n"
            "Run: scripts\\install_models\\02_download_qwen14b_intel_gpu.bat",
        )
        ok = False
    else:
        audit.add("NoLlama venv", "OK", str(venv_python))

    model_dir = home / "model"
    if not _model_cache_valid(model_dir):
        audit.add(
            "Qwen model files",
            "FAIL",
            f"No valid OpenVINO weights in {model_dir}\n"
            "Expected openvino_model.bin > 100 MB (Qwen3-14B-int4-ov ~8 GB).",
        )
        ok = False
    else:
        bin_path = model_dir / "openvino_model.bin"
        size_gb = bin_path.stat().st_size / (1024**3)
        audit.add("Qwen model files", "OK", f"{bin_path.name} ({size_gb:.1f} GB)")

    start_ps1 = home / "start.ps1"
    if not start_ps1.is_file():
        audit.add("start.ps1", "WARN", "Missing — install_models\\02 can regenerate it.")
    else:
        audit.add("start.ps1", "OK", str(start_ps1))

    return ok


def check_hermes_packages(audit: Audit) -> bool:
    missing: list[str] = []
    for mod, pip_name in HERMES_PACKAGES:
        try:
            __import__(mod)
        except ImportError:
            missing.append(pip_name)
    if missing:
        audit.add(
            "Hermes Python packages",
            "FAIL",
            f"Missing: {', '.join(missing)}\n"
            f"Fix: scripts\\install_models\\03_install_python_packages.bat",
        )
        return False
    audit.add("Hermes Python packages", "OK", "numpy, openai, sentence-transformers")
    return True


def check_ports(audit: Audit) -> None:
    listeners = _port_listeners()
    lines: list[str] = []
    stock_ollama = False

    for port in PORTS:
        pids = listeners.get(port, [])
        if not pids:
            lines.append(f"port {port}: free")
            continue
        for pid in pids:
            name = _process_name(pid) or "unknown"
            lines.append(f"port {port}: PID {pid} ({name})")
            if port == 11434 and name == "ollama.exe":
                stock_ollama = True

    status = "WARN" if stock_ollama else "OK"
    if stock_ollama:
        lines.append("Stock Ollama on :11434 can conflict with NoLlama — will stop during fix.")
    audit.add("Port listeners", status, "\n".join(lines))


def check_server(audit: Audit) -> bool:
    health = _probe_health_with_retries()
    if health is None:
        audit.add(
            "NoLlama health",
            "FAIL",
            f"No response from {NOLLAMA_HEALTH_URL} after {HEALTH_RETRIES} tries.\n"
            "Server not running or still loading weights (local — not an internet issue).",
        )
        return False

    lines = [f"{NOLLAMA_HEALTH_URL}", f"status={health.get('status', health)}"]
    resolved = resolve_chat_model(REQUESTED_MODEL, prefer_device="GPU")
    if resolved:
        lines.append(f"chat model: {resolved} (requested: {REQUESTED_MODEL})")
        audit.add("NoLlama health", "OK", "\n".join(lines))
        return True

    models = _fetch_json(f"{NOLLAMA_OPENAI_BASE_URL.rstrip('/')}/models")
    listed = []
    if isinstance(models, dict):
        listed = [m.get("id", "") for m in models.get("data", [])]
    audit.add(
        "NoLlama health",
        "WARN",
        "\n".join(lines)
        + f"\nModel '{REQUESTED_MODEL}' not listed yet."
        + (f"\nLoaded: {', '.join(listed) or '(none)'}" if listed else ""),
    )
    return False


def fix_hermes_packages(audit: Audit) -> bool:
    req = HERMES_DIR / "requirements-hermes.txt"
    audit.add(
        "Install Hermes packages",
        "FIX",
        f"pip install -r {req}\n(Requires internet — skipped unless --pip is passed.)",
    )
    proc = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-r", str(req)],
        cwd=str(HERMES_DIR),
        timeout=600,
    )
    if proc.returncode != 0:
        audit.add("Install Hermes packages", "FAIL", "pip install failed")
        return False
    audit.fixes_applied.append("pip install requirements-hermes.txt")
    return check_hermes_packages(audit)


def fix_gpu_install(audit: Audit) -> bool:
    ps1 = INSTALL_MODELS / "install_hermes_gpu.ps1"
    home = str(_nollama_home())
    audit.add(
        "GPU install",
        "FIX",
        f"Running {ps1.name}\n(Requires stable internet + ~8 GB download — only with --install.)",
    )
    proc = subprocess.run(
        _pwsh() + ["-File", str(ps1), "-NollamaHome", home],
        cwd=str(INSTALL_MODELS),
        timeout=7200,
    )
    if proc.returncode != 0:
        audit.add("GPU install", "FAIL", "install_hermes_gpu.ps1 failed")
        return False
    audit.fixes_applied.append("install_hermes_gpu.ps1")
    os.environ.setdefault("NOLLAMA_HOME", home)
    return check_install(audit)


def fix_stop_listeners(audit: Audit) -> bool:
    bat = RUN_INTEL_GPU / "00_stop_nollama.bat"
    audit.add("Stop port listeners", "FIX", "Freeing ports 8000 and 11434")
    subprocess.run(["cmd", "/c", str(bat), "nopause"], cwd=str(RUN_INTEL_GPU), timeout=60)
    subprocess.run(
        ["taskkill", "/IM", "ollama.exe", "/F"],
        capture_output=True,
        timeout=30,
    )
    time.sleep(2)
    audit.fixes_applied.append("stopped listeners on 8000/11434")
    check_ports(audit)
    return True


def fix_start_server(audit: Audit, *, wait_seconds: int = 120) -> bool:
    home = _nollama_home()
    start_ps1 = home / "start.ps1"
    if not start_ps1.is_file():
        audit.add("Start NoLlama", "FAIL", f"Missing {start_ps1}")
        return False

    if _probe_health_with_retries() is not None:
        audit.add("Start NoLlama", "OK", "Already responding")
        return True

    audit.add("Start NoLlama", "FIX", f"Launching new window: {start_ps1}")
    subprocess.Popen(
        [
            "cmd",
            "/c",
            "start",
            "NoLlama",
            "cmd",
            "/k",
            f'cd /d "{home}" && {" ".join(_pwsh())} -File start.ps1',
        ],
        cwd=str(home),
        creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0),
    )

    health = _wait_for_health(wait_seconds=wait_seconds)
    if health is not None:
        audit.add("Start NoLlama", "OK", f"Health up (waited up to {wait_seconds}s)")
        audit.fixes_applied.append("started NoLlama server")
        return True

    audit.add(
        "Start NoLlama",
        "FAIL",
        f"Health not ready after {wait_seconds}s.\n"
        "Check the NoLlama window for OpenVINO / GPU errors.\n"
        "(Local load — retry when ready; no download needed if model files exist.)",
    )
    return False


def fix_warmup(audit: Audit, *, timeout: float = 180.0) -> bool:
    resolved = resolve_chat_model(REQUESTED_MODEL, prefer_device="GPU")
    if not resolved:
        audit.add("Qwen warmup", "FAIL", f"Cannot resolve model '{REQUESTED_MODEL}'")
        return False

    audit.add("Qwen warmup", "FIX", f"Chat probe model={resolved} (first load can take 60-120s)")
    try:
        from openai import OpenAI

        client = OpenAI(
            base_url=os.environ.get("NOLLAMA_OPENAI_BASE_URL", NOLLAMA_OPENAI_BASE_URL),
            api_key=os.environ.get("NOLLAMA_API_KEY", "nollama"),
            timeout=timeout,
        )
        resp = client.chat.completions.with_raw_response.create(
            model=resolved,
            messages=[{"role": "user", "content": "/no_think Reply with exactly: OK"}],
            max_tokens=32,
            temperature=0,
        )
        device = resp.headers.get("X-Device", "")
        text = (resp.parse().choices[0].message.content or "").strip()
        detail = f"reply={text!r}"
        if device:
            detail += f"  device={device}"
        audit.add("Qwen warmup", "OK", detail)
        audit.fixes_applied.append("warmed Qwen chat path")
        return True
    except Exception as exc:
        audit.add("Qwen warmup", "FAIL", str(exc))
        return False


def run_audit(*, fix: bool, install: bool, pip: bool, warmup: bool) -> int:
    audit = Audit()
    print("=== NoLlama / Intel GPU setup ===")
    print(f"NOLLAMA_HOME={_nollama_home()}")
    print(f"HERMES_CHAT_MODEL={REQUESTED_MODEL}")
    if fix and not install and not pip:
        print("Mode: local fix only (no downloads — safe on spotty internet)")
    print()

    install_ok = check_install(audit)
    packages_ok = check_hermes_packages(audit)
    check_ports(audit)
    server_ok = check_server(audit)

    if not fix:
        print("\n=== Summary (check only) ===")
        if audit.failed or not install_ok or not packages_ok or not server_ok:
            print("Not ready. Re-run without --check for local auto-fix (start server, free ports).")
            if not install_ok:
                print("Missing files? Run scripts\\install_models\\00_install_everything.bat")
            if not packages_ok:
                print("Missing pip packages? Run scripts\\install_models\\03_install_python_packages.bat")
            return 1
        print("Stack looks ready.")
        return 0

    changed = False

    if pip and not packages_ok:
        changed = fix_hermes_packages(audit) or changed
        packages_ok = check_hermes_packages(audit)
    elif not packages_ok:
        audit.add(
            "Hermes Python packages",
            "WARN",
            "Missing packages — not auto-installing (needs --pip when online).",
        )

    if install and not install_ok:
        if fix_gpu_install(audit):
            changed = True
            install_ok = check_install(audit)
    elif not install_ok:
        audit.add(
            "Local install files",
            "WARN",
            "Clone/venv/model incomplete — not auto-installing (needs --install when online).\n"
            "Run: scripts\\install_models\\00_install_everything.bat",
        )
        print("\n=== Summary ===")
        print("Cannot start Qwen without local model files.")
        print("When internet is stable: scripts\\install_models\\00_install_everything.bat")
        return 1

    listeners = _port_listeners()
    stock_on_11434 = any(_process_name(pid) == "ollama.exe" for pid in listeners.get(11434, []))
    port_8000_busy = bool(listeners.get(8000))
    if stock_on_11434 or (port_8000_busy and not server_ok):
        fix_stop_listeners(audit)
        changed = True

    if not server_ok:
        if fix_start_server(audit):
            server_ok = True
            changed = True

    if server_ok and not resolve_chat_model(REQUESTED_MODEL, prefer_device="GPU"):
        audit.add(
            "Chat model",
            "WARN",
            f"'{REQUESTED_MODEL}' still not listed — server may still be loading weights.\n"
            "Wait and re-run, or check the NoLlama window.",
        )

    if warmup and server_ok:
        fix_warmup(audit)
        changed = True

    print("\n=== Summary ===")
    if audit.fixes_applied:
        print("Applied (local only):")
        for item in audit.fixes_applied:
            print(f"  - {item}")

    final_health = _probe_health_with_retries()
    final_model = bool(resolve_chat_model(REQUESTED_MODEL, prefer_device="GPU"))
    if final_health is not None and final_model:
        print("\nQwen14B is ready on Intel GPU for Hermes.")
        print("  python hermes_orchestrator.py \"your task\"")
        return 0

    if changed:
        print("\nPartial fix applied — check [FAIL]/[WARN] lines and the NoLlama window.")
        print("No downloads were attempted unless you passed --install or --pip.")
    else:
        print("\nNot ready — see [FAIL] lines above.")
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Check and repair NoLlama + Qwen for Hermes.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Audit only; do not start/stop services or install packages.",
    )
    parser.add_argument(
        "--install",
        action="store_true",
        help="ONLINE ONLY: run install_hermes_gpu.ps1 if clone/venv/model is missing.",
    )
    parser.add_argument(
        "--pip",
        action="store_true",
        help="ONLINE ONLY: pip install -r requirements-hermes.txt if packages missing.",
    )
    parser.add_argument(
        "--warmup",
        action="store_true",
        help="After server is up, run a localhost chat completion to load Qwen into GPU memory.",
    )
    args = parser.parse_args()
    return run_audit(
        fix=not args.check,
        install=args.install,
        pip=args.pip,
        warmup=args.warmup,
    )


if __name__ == "__main__":
    raise SystemExit(main())
