#!/usr/bin/env python3
"""
Verify all Hermes models and local install artifacts are on disk (no server required).

  python scripts/install_models/verify_models_installed.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

HERMES_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERMES_DIR))

from hermes_config import EMBED_MODEL_DEFAULT, NOLLAMA_HOME  # noqa: E402

MIN_MODEL_BIN_BYTES = 100 * 1024 * 1024
HERMES_PACKAGES = (
    ("numpy", "numpy"),
    ("openai", "openai"),
    ("sentence_transformers", "sentence-transformers"),
)


def _nollama_home() -> Path:
    return Path(os.environ.get("NOLLAMA_HOME", NOLLAMA_HOME))


def _model_cache_valid(model_dir: Path) -> tuple[bool, str]:
    if not model_dir.is_dir():
        return False, f"Missing directory: {model_dir}"
    for name in ("openvino_model.bin", "openvino_language_model.bin"):
        candidate = model_dir / name
        if candidate.is_file() and candidate.stat().st_size > MIN_MODEL_BIN_BYTES:
            size_gb = candidate.stat().st_size / (1024**3)
            return True, f"{candidate.name} ({size_gb:.1f} GB)"
    return False, f"No valid OpenVINO weights in {model_dir}"


def _start_ps1_uses_gpu(home: Path) -> tuple[bool, str]:
    start_ps1 = home / "start.ps1"
    if not start_ps1.is_file():
        return False, f"Missing {start_ps1}"
    text = start_ps1.read_text(encoding="utf-8", errors="replace")
    if "--device GPU" in text or "--device GPU".lower() in text.lower():
        return True, str(start_ps1)
    return False, f"{start_ps1} does not pass --device GPU to NoLlama"


def _embed_model_cached(model_id: str) -> tuple[bool, str]:
    cache_root = Path.home() / ".cache" / "huggingface" / "hub"
    slug = model_id.replace("/", "--")
    if cache_root.is_dir():
        for entry in cache_root.iterdir():
            if slug in entry.name:
                return True, f"HF cache: {entry.name}"
    try:
        from sentence_transformers import SentenceTransformer

        SentenceTransformer(model_id, device="cpu")
        return True, f"Loaded {model_id}"
    except Exception as exc:
        return False, f"{model_id} not cached yet ({exc}) — runs on first embed"


def main() -> int:
    home = _nollama_home()
    failures: list[str] = []
    warnings: list[str] = []

    print("=== Verify Hermes models (disk only) ===")
    print(f"NOLLAMA_HOME={home}")
    print(f"EMBED_MODEL={EMBED_MODEL_DEFAULT}")
    print()

    if not (home / "nollama.py").is_file():
        failures.append(f"NoLlama clone missing: {home / 'nollama.py'}")
        print("[FAIL] NoLlama clone")
    else:
        print(f"[OK] NoLlama clone: {home}")

    venv_python = home / "venv" / "Scripts" / "python.exe"
    if not venv_python.is_file():
        failures.append(f"NoLlama venv missing: {venv_python}")
        print("[FAIL] NoLlama venv")
    else:
        print(f"[OK] NoLlama venv: {venv_python}")

    model_ok, model_detail = _model_cache_valid(home / "model")
    if model_ok:
        print(f"[OK] Qwen3-14B GPU model: {model_detail}")
    else:
        failures.append(model_detail)
        print(f"[FAIL] Qwen3-14B GPU model: {model_detail}")

    gpu_ok, gpu_detail = _start_ps1_uses_gpu(home)
    if gpu_ok:
        print(f"[OK] Intel GPU start.ps1: {gpu_detail}")
    else:
        failures.append(gpu_detail)
        print(f"[FAIL] Intel GPU start.ps1: {gpu_detail}")

    missing_pkgs: list[str] = []
    for mod, pip_name in HERMES_PACKAGES:
        try:
            __import__(mod)
        except ImportError:
            missing_pkgs.append(pip_name)
    if missing_pkgs:
        failures.append(f"Missing pip packages: {', '.join(missing_pkgs)}")
        print(f"[FAIL] Hermes Python packages: {', '.join(missing_pkgs)}")
    else:
        print("[OK] Hermes Python packages: numpy, openai, sentence-transformers")

    embed_ok, embed_detail = _embed_model_cached(EMBED_MODEL_DEFAULT)
    if embed_ok:
        print(f"[OK] RAG embed model: {embed_detail}")
    else:
        warnings.append(embed_detail)
        print(f"[WARN] RAG embed model: {embed_detail}")

    print("\n=== Summary ===")
    if warnings:
        for item in warnings:
            print(f"  WARN: {item}")
    if failures:
        for item in failures:
            print(f"  FAIL: {item}")
        print("\nRun install scripts in order:")
        print("  scripts\\install_models\\01_clone_nollama_repo.bat")
        print("  scripts\\install_models\\02_download_qwen14b_intel_gpu.bat")
        print("  scripts\\install_models\\03_install_python_packages.bat")
        return 1

    print("  All required models and install artifacts are present.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
