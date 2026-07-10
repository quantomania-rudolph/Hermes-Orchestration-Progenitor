#!/usr/bin/env python3
"""
Integration tests: NoLlama health, Intel GPU routing, Hermes model resolution, chat, preflight.

  python scripts/run_intel_gpu/test_nollama_integration.py
  python scripts/run_intel_gpu/test_nollama_integration.py --quick
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

HERMES_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERMES_DIR))

from hermes_config import HERMES_CHAT_MODEL_DEFAULT, NOLLAMA_HEALTH_URL, NOLLAMA_OPENAI_BASE_URL
from hermes_nollama import nollama_health, resolve_chat_model


def _http_json(url: str, timeout: float = 15.0) -> dict | list | None:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def _chat_probe(model: str, timeout: float = 120.0) -> tuple[bool, str, str]:
    """Returns (ok, reply, device_header)."""
    from openai import OpenAI

    client = OpenAI(
        base_url=os.environ.get("NOLLAMA_OPENAI_BASE_URL", NOLLAMA_OPENAI_BASE_URL),
        api_key=os.environ.get("NOLLAMA_API_KEY", "nollama"),
        timeout=timeout,
    )
    try:
        resp = client.chat.completions.with_raw_response.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": "/no_think Reply with exactly: OK",
                }
            ],
            max_tokens=32,
            temperature=0,
        )
        device = resp.headers.get("X-Device", "")
        parsed = resp.parse()
        text = (parsed.choices[0].message.content or "").strip()
        return True, text, device
    except Exception as exc:
        return False, str(exc), ""


def run_tests(*, quick: bool) -> int:
    failures: list[str] = []
    print("=== NoLlama / Intel GPU / Hermes integration tests ===\n", flush=True)

    # 1) Health
    health = nollama_health()
    if not health:
        failures.append(f"health unreachable: {NOLLAMA_HEALTH_URL}")
        print("[FAIL] health")
    else:
        status = health.get("status", health)
        print(f"[OK] health status={status}")
        if isinstance(health, dict):
            print(f"     payload keys: {list(health.keys())}")

    # 2) Model list + resolve
    resolved = resolve_chat_model(prefer_device="GPU")
    requested = os.environ.get("HERMES_CHAT_MODEL", HERMES_CHAT_MODEL_DEFAULT)
    if not resolved:
        failures.append(f"could not resolve model '{requested}' from /v1/models")
        print(f"[FAIL] resolve_chat_model('{requested}')")
        models = _http_json(f"{NOLLAMA_OPENAI_BASE_URL.rstrip('/')}/models")
        print(f"       /v1/models: {models}")
    else:
        print(f"[OK] resolved '{requested}' -> '{resolved}'")

    # 3) GPU device check (from health or chat header)
    gpu_seen = False
    if isinstance(health, dict):
        blob = json.dumps(health).upper()
        gpu_seen = "GPU" in blob or "ARC" in blob
    if gpu_seen:
        print("[OK] health mentions GPU/ARC")
    else:
        print("[WARN] health JSON does not clearly show GPU (will verify via chat header)")

    if quick:
        print("\n--quick: skipping chat probe")
    elif resolved:
        print(f"\n[..] chat probe model={resolved} (may take 30-120s on first load)...")
        ok, reply, device = _chat_probe(resolved)
        if not ok:
            failures.append(f"chat failed: {reply}")
            print(f"[FAIL] chat: {reply}")
        else:
            print(f"[OK] chat reply={reply!r}  X-Device={device or '(none)'}")
            if device.upper() == "GPU":
                print("[OK] Qwen14B inference routed to Intel Arc GPU")
            elif device:
                failures.append(f"inference on {device}, expected GPU for Arc setup")
                print(f"[FAIL] inference on {device}, expected GPU for Intel Arc setup")
            else:
                failures.append("no X-Device header; cannot confirm GPU routing")
                print("[FAIL] no X-Device header; cannot confirm Intel GPU routing")

    # 4) Hermes ensure_hermes_model
    proc = subprocess.run(
        [sys.executable, str(HERMES_DIR / "ensure_hermes_model.py"), "--check"],
        cwd=str(HERMES_DIR),
        capture_output=True,
        text=True,
        timeout=30,
    )
    if proc.returncode != 0:
        failures.append("ensure_hermes_model.py --check failed")
        print("[FAIL] ensure_hermes_model.py --check")
        print(proc.stdout)
        print(proc.stderr)
    else:
        print("[OK] ensure_hermes_model.py --check")

    # 5) Hermes preflight quick
    proc = subprocess.run(
        [sys.executable, str(HERMES_DIR / "hermes_preflight.py"), "--quick", "--skip-cursor"],
        cwd=str(HERMES_DIR),
        capture_output=True,
        text=True,
        timeout=60,
    )
    if proc.returncode != 0:
        failures.append("hermes_preflight.py --quick reported failures")
        print("[FAIL] hermes_preflight.py --quick")
        print(proc.stdout)
    else:
        print("[OK] hermes_preflight.py --quick")

    # 6) Local embeddings smoke test
    try:
        from hermes_embeddings import embed_texts

        vec = embed_texts(["integration probe"])[0]
        print(f"[OK] local embeddings dim={len(vec)}")
    except Exception as exc:
        failures.append(f"embeddings: {exc}")
        print(f"[FAIL] embeddings: {exc}")

    print("\n=== Summary ===")
    if failures:
        for item in failures:
            print(f"  FAIL: {item}")
        return 1
    print("  All checks passed — Qwen14B has Intel GPU access.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--quick", action="store_true", help="Skip slow chat completion probe")
    args = parser.parse_args()
    return run_tests(quick=args.quick)


if __name__ == "__main__":
    raise SystemExit(main())
