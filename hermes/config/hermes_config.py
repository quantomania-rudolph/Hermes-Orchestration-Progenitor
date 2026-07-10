"""Shared Hermes defaults — NoLlama backend (Intel NPU / Arc / CPU)."""

import os
from pathlib import Path

HERMES_DIR = Path(__file__).resolve().parent
VECTORS_PATH = HERMES_DIR / "codebase_vectors.json"
BUILD_INDEX_SCRIPT = HERMES_DIR / "scripts" / "setup_index" / "build_index.py"
WORKSPACE_ROOT = HERMES_DIR.parent
# Default RAG scan roots (semicolon-separated on Windows). Override with HERMES_WORKSPACE_ROOTS.
INDEX_ROOTS_DEFAULT = os.environ.get("HERMES_INDEX_ROOTS_DEFAULT", str(HERMES_DIR))

# NoLlama OpenAI-compatible API (primary for Hermes chat + tools)
NOLLAMA_OPENAI_BASE_URL = os.environ.get(
    "NOLLAMA_OPENAI_BASE_URL", "http://localhost:8000/v1"
)
NOLLAMA_HEALTH_URL = os.environ.get("NOLLAMA_HEALTH_URL", "http://localhost:8000/health")
NOLLAMA_OLLAMA_TAGS_URL = os.environ.get(
    "NOLLAMA_OLLAMA_TAGS_URL", "http://localhost:11434/api/tags"
)

# Default chat model: set after `install.ps1` in NoLlama (see models.json).
# Qwen3 14B INT4 is the default for 16GB Arc (stronger coding/reasoning).
# For faster NPU-only runs, override with Qwen3 8B INT4-CW:
#   set HERMES_CHAT_MODEL=qwen3-8b-int4-cw
HERMES_CHAT_MODEL_DEFAULT = "qwen3-14b-int4"

# RAG embeddings: NoLlama has no /api/embeddings — use local sentence-transformers.
EMBED_MODEL_DEFAULT = os.environ.get("HERMES_EMBED_MODEL", "BAAI/bge-m3")

CURSOR_MODEL_DEFAULT = "composer-2.5"

# Optional: path to cloned NoLlama repo (contains install.ps1 / start.ps1 / nollama.py)
NOLLAMA_HOME = os.environ.get("NOLLAMA_HOME", r"C:\Users\Rudol\NoLlama")
