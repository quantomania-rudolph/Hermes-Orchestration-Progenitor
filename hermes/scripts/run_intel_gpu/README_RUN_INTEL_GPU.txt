RUN NOLLAMA ON INTEL ARC / CORE ULTRA GPU
=========================================

Use these scripts to start NoLlama and confirm Qwen3-14B runs on your Intel GPU.
All scripts here are offline-safe unless noted.

PREREQUISITE
------------
  Models must be installed first:
    scripts\install_models\04_verify_all_models_installed.bat

DAILY RUN ORDER (offline-safe)
------------------------------
  03_daily_setup.bat              Free ports, start NoLlama, warmup Qwen (recommended)
  01_start_nollama.bat            Start server if not running (leave window open)
  02_warmup_qwen14b.bat           Load Qwen into GPU memory
  04_verify_gpu_access.bat        Confirm Qwen14B uses Intel Arc GPU

FULL STARTUP (first boot of the day)
------------------------------------
  00_startup_everything.bat       Runs 01 → 02 → 04
  06_hermes_startup.bat           Full 7-step Hermes readiness check
  07_hermes_daily.bat             Quick daily boot + preflight
  check_hermes_model.bat          Verify chat model is listed

TROUBLESHOOTING
---------------
  00_stop_nollama.bat             Free ports 8000 and 11434
  01_restart_nollama.bat          Stop + fresh start
  check_nollama_health.bat        Quick health probe (exit 0 = up)
  check_nollama_full.bat          Full audit (read-only)
  run_integration_tests.bat       Full Hermes + GPU integration tests

CHAT MODEL
----------
  Default: qwen3-14b-int4 (Qwen3 14B INT4 on Intel Arc)
  Override: set HERMES_CHAT_MODEL=qwen3-8b-int4-cw  (faster NPU option)

API ENDPOINTS
-------------
  OpenAI API : http://localhost:8000/v1
  Health     : http://localhost:8000/health
