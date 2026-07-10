INSTALL ALL HERMES MODELS (first-time setup)
============================================

Run these scripts IN ORDER when setting up a new machine.
Requires stable internet for steps 02 and 03.

WHAT GETS INSTALLED
-------------------
  1. NoLlama runtime repo     (OpenVINO backend for Intel Arc / Core Ultra)
  2. Qwen3-14B-int4-ov        (~8 GB OpenVINO weights for Intel Arc GPU)
  3. Hermes Python packages   (openai, sentence-transformers, etc.)
  4. BAAI/bge-m3              (RAG embeddings — auto-downloads on first embed)

RUN ORDER
---------
  00_install_everything.bat           Master script: runs 01 → 02 → 03
  01_clone_nollama_repo.bat           Clone NoLlama to %NOLLAMA_HOME%
  02_download_qwen14b_intel_gpu.bat   venv + Qwen3 14B GPU model (~8 GB)
  03_install_python_packages.bat      pip install -r requirements-hermes.txt
  04_verify_all_models_installed.bat  Check only — confirms everything on disk

PREREQUISITES
-------------
  - Git
  - PowerShell 7: winget install Microsoft.PowerShell
  - Python 3.10+ with pip

ENV VARS (set automatically by 02)
----------------------------------
  NOLLAMA_HOME=C:\Users\Rudol\NoLlama   (or your path)
  HERMES_CHAT_MODEL=qwen3-14b-int4

AFTER INSTALL
-------------
  Go to scripts\run_intel_gpu\ and run:
    01_start_nollama.bat
    04_verify_gpu_access.bat
