# HOW TO RUN — Hermes Orchestration Complete Runbook

> **Golden Rule:** *Hermes proposes. Python disposes.*  
> Every agent action is verified by Python gauntlets before integration.

---

## 📋 Table of Contents

1. [Prerequisites](#prerequisites)
2. [First-Time Setup](#first-time-setup)
3. [Daily Operations](#daily-operations)
4. [Running Modes](#running-modes)
5. [Executing Tasks](#executing-tasks)
6. [Pipeline Execution](#pipeline-execution)
7. [Verification & Testing](#verification--testing)
8. [Troubleshooting](#troubleshooting)
9. [Advanced Configuration](#advanced-configuration)
10. [Data Pipeline Integration](#data-pipeline-integration)

---

## 1️⃣ Prerequisites

### Hardware Requirements
| Component | Minimum | Recommended |
|-----------|---------|-------------|
| **GPU** | Intel Arc A750 (8GB VRAM) | Intel Arc A770 (16GB VRAM) |
| **RAM** | 16 GB | 32 GB+ |
| **Storage** | 50 GB free | 100 GB+ NVMe |
| **CPU** | 8 cores | 16+ cores |

### Software Requirements
```powershell
# Verify versions
python --version      # 3.11+
git --version         # 2.40+
pwsh --version        # 7.4+ (PowerShell 7)
nvidia-smi            # Not needed - Intel Arc uses different tooling
```

### Windows Features
- **WSL2** with Ubuntu 22.04+ (for Daedalus integration)
- **Virtual Machine Platform** enabled
- **Hyper-V** disabled (conflicts with WSL2 GPU passthrough)

### API Keys Required
Create `.env.local` from `.env.example`:
```bash
# Required for live Cursor agent spawns
CURSOR_API_KEY=sk-...your-key...

# Optional: override runtime
HERMES_T09_RUNTIME=auto    # auto | cursor | qwen

# Optional: workspace roots for RAG indexing
HERMES_WORKSPACE_ROOTS=C:\Users\Rudol\Desktop\Hermes_Orchestration;C:\Users\Rudol\Desktop\FILE OF DATA

# Optional: Database (if using Vault ingestion)
DATABASE_URL=postgresql://user:pass@localhost:5432/market_data
```

---

## 2️⃣ First-Time Setup (~30 minutes + 14GB download)

### Step 1: Clone & Configure
```powershell
cd C:\Users\Rudol\Desktop\Hermes_Orchestration
copy .env.example .env.local
notepad .env.local    # Paste your CURSOR_API_KEY
```

### Step 2: Install Models (One-time, ~14GB)
```powershell
# Downloads Qwen2.5-Coder-14B + NoLlama server
.\hermes\scripts\install_models\00_install_everything.bat

# Verify installation
.\hermes\scripts\install_models\04_verify_all_models_installed.bat
```

**What this installs:**
- `Qwen2.5-Coder-14B-Instruct-GGUF` (~8.5GB)
- `NoLlama` server binary (~500MB)
- Python dependencies from `requirements-hermes.txt`

### Step 3: Start NoLlama on GPU
```powershell
# Starts NoLlama on Intel Arc GPU (port 8010)
.\hermes\scripts\run_intel_gpu\01_start_nollama.bat

# Verify GPU access
.\hermes\scripts\run_intel_gpu\04_verify_gpu_access.bat
```

**Expected output:**
```
NoLlama v0.3.1 starting on Intel Arc A770
Model: Qwen2.5-Coder-14B loaded (8.5GB VRAM)
Server listening on http://localhost:8010
```

### Step 4: Build RAG Codebase Index
```powershell
# Initial full index (takes 2-5 minutes)
.\hermes\scripts\setup_index\01_build_index.bat

# Verify index health
.\hermes\scripts\setup_index\03_verify_index.bat
```

---

## 3️⃣ Daily Operations (2 minutes)

### Morning Startup
```powershell
cd C:\Users\Rudol\Desktop\Hermes_Orchestration

# 1. Daily GPU/NoLlama setup (checks model, restarts if needed)
.\hermes\scripts\run_intel_gpu\03_daily_setup.bat

# 2. Daily Hermes startup (preflight + warmup)
.\hermes\scripts\run_intel_gpu\07_hermes_daily.bat

# 3. Quick health check
.\hermes\scripts\run_intel_gpu\04_verify_gpu_access.bat
```

### Evening Shutdown
```powershell
# Stop NoLlama gracefully
.\hermes\scripts\run_intel_gpu\00_stop_nollama.bat
```

---

## 4️⃣ Running Modes

| Mode | Env Var | When to Use |
|------|---------|-------------|
| **Auto (Default)** | `HERMES_T09_RUNTIME=auto` | Production — tries Cursor bridge, falls back to Qwen |
| **Cursor Only** | `HERMES_T09_RUNTIME=cursor` | Development — requires Cursor IDE running |
| **Qwen Only** | `HERMES_T09_RUNTIME=qwen` | Offline / no Cursor API / pure local |

### Switching Modes
```powershell
# Temporary override for single command
$env:HERMES_T09_RUNTIME="qwen"; python hermes/core/hermes_orchestrator.py "task"

# Permanent (edit .env.local)
HERMES_T09_RUNTIME=qwen
```

---

## 5️⃣ Executing Tasks

### Single Task (Interactive)
```powershell
cd C:\Users\Rudol\Desktop\Hermes_Orchestration

# Basic task
python hermes/core/hermes_orchestrator.py "create a Python module for RSI calculation"

# With custom seed JSON
python hermes/core/hermes_orchestrator.py --seed "main orchestration loop/pipeline_state.test_trading.seed.json"

# Dry run (no Cursor spawns, full Python gauntlet)
$env:HERMES_DRY_RUN=1; python hermes/core/hermes_orchestrator.py "refactor auth module"
```

### Task with Specific Pipeline State
```powershell
# List available seeds
ls "main orchestration loop\pipeline_state.*.seed.json"

# Run with specific strategy seed
python hermes/core/hermes_orchestrator.py --seed "main orchestration loop\pipeline_state.simple_rsi_strategy.seed.json"
```

---

## 6️⃣ Pipeline Execution (Autonomous Factory)

### Live Trading Test (Full Pipeline)
```powershell
cd "C:\Users\Rudol\Desktop\Hermes_Orchestration\main orchestration loop"

# Run live test with real Cursor/Qwen agents
.\run\04_run_trading_test.bat live

# Or with specific strategy
.\run\10_run_live_lr_cursor.bat
.\run\12_run_live_lstm_cursor.bat
.\run\14_run_live_pairs_ukf_cursor.bat
```

### Stress Campaigns
```powershell
# Run all stress tests
.\run\13_run_stress_campaign.bat

# Individual stress tests
.\run\15_retry_cli_fastapi.sh
.\run\16_retry_fastapi_only.sh
```

### WSL2 Bridge (For Daedalus Integration)
```powershell
# Probe WSL connectivity
.\run\_wsl_agent_probe.sh

# Verify Cursor spawn from WSL
.\run\_wsl_verify_cursor.sh

# Kill stale bridges
.\run\_wsl_kill_stale_bridges.sh
```

---

## 7️⃣ Verification & Testing

### Full Verification Suite (Run Before Commits)
```powershell
cd "C:\Users\Rudol\Desktop\Hermes_Orchestration\main orchestration loop"

# All 8 verification scripts
python verification/run_all_verifications.py

# Individual checks
python verification/verify_campaign_preflight.py
python verification/verify_process_hygiene.py
python verification/verify_wsl_native_launcher.py
python verification/verify_quant_ukf_ingestion.py
python verification/verify_preflight_ping_resilience.py
python verification/verify_wsl_reexec_pid.py
python verification/verify_live_stack_dedup.py
python verification/verify_db_wsl_reachability.py
```

### Daedalus Verification (Separate)
```powershell
cd "C:\Users\Rudol\Desktop\Hermes_Orchestration\daedalus"
python verification/run_all_daedalus_verifications.py
```

### Quick Health Checks
```powershell
# GPU/NoLlama
.\hermes\scripts\run_intel_gpu\04_verify_gpu_access.bat
.\hermes\scripts\run_intel_gpu\check_hermes_model.bat

# RAG Index
.\hermes\scripts\setup_index\03_verify_index.bat
.\hermes\scripts\setup_index\04_verify_incremental_growth.bat

# Models
.\hermes\scripts\install_models\04_verify_all_models_installed.bat
```

---

## 8️⃣ Troubleshooting

### NoLlama Won't Start
```powershell
# 1. Check GPU drivers
.\hermes\scripts\run_intel_gpu\04_verify_gpu_access.bat

# 2. Kill stale processes
.\hermes\scripts\run_intel_gpu\00_stop_nollama.bat
taskkill /F /IM nollama.exe

# 3. Restart fresh
.\hermes\scripts\run_intel_gpu\01_start_nollama.bat
```

### Cursor Bridge Fails (Windows)
```powershell
# Error: "Cursor local bridge unavailable"
# Solution: Falls back to Qwen automatically (auto mode)
# Or force Qwen mode:
$env:HERMES_T09_RUNTIME="qwen"
```

### Index Build Fails
```powershell
# Clear cache and rebuild
Remove-Item -Recurse -Force "hermes/scripts/setup_index/__pycache__"
.\hermes\scripts\setup_index\01_build_index.bat
```

### GPU OOM (Out of Memory)
```powershell
# Reduce batch size in hermes_config.py
# Or switch to CPU mode (slow):
$env:HERMES_T09_RUNTIME="qwen"
$env:NO_LLAMA_CPU_ONLY=1
```

### WSL2 Connection Issues
```powershell
# From Windows
.\run\_wsl_kill_stale_bridges.sh

# From WSL
ssh -O exit localhost  # Kill SSH control masters
```

---

## 9️⃣ Advanced Configuration

### Environment Variables Reference
| Variable | Default | Description |
|----------|---------|-------------|
| `HERMES_T09_RUNTIME` | `auto` | `auto\|cursor\|qwen` |
| `HERMES_DRY_RUN` | `0` | Skip Cursor spawns, run Python gauntlet only |
| `HERMES_SKIP_CURSOR` | `0` | Force deterministic co-verify |
| `HERMES_IN_SESSION` | `0` | Set by session; runs unit tests only |
| `HERMES_WORKSPACE_ROOTS` | Auto | Semicolon-separated paths for RAG |
| `CURSOR_API_KEY` | Required | For live T09/T10/T24 |
| `NO_LLAMA_PORT` | `8010` | NoLlama server port |
| `DATABASE_URL` | None | PostgreSQL for Vault data |

### Custom Pipeline State
Create `pipeline_state.my_strategy.seed.json`:
```json
{
  "objective": "Build a mean-reversion equity strategy using Bollinger Bands",
  "constraints": [
    "Max 10 positions",
    "Stop loss 2%",
    "Universe: SP500"
  ],
  "master_plan": [
    "ingest_data",
    "feature_engineer",
    "backtest",
    "optimize",
    "validate"
  ],
  "tools_allowed": ["T06", "T07", "T08", "T09", "T10", "T15"]
}
```

### Adding New Strategies to `generated/`
```powershell
# After successful pipeline run, artifacts land in:
generated/<strategy_slug>/
├── daedalus_manifest.json
├── artifacts/
│   ├── strategy.py
│   ├── backtest_results.json
│   └── risk_metrics.json
└── reports/
    └── pnl_report.md
```

---

## 🔟 Data Pipeline Integration

### Vault Data Ingestion (Separate Repo: `FILE OF DATA/PROJECT/`)
```powershell
cd "C:\Users\Rudol\Desktop\FILE OF DATA\PROJECT\Vault\scripts"

# Equity daily catchup
python vault_forward_catchup.py

# Macro (FRED + Yahoo)
python ingest_macro_missing.py
python ingest_macro_yahoo.py

# Corporate actions
python etl_yahoo_corp_actions.py

# Verify coverage
python verify_equity_coverage.py
```

### PostgreSQL Schema
```sql
-- Equity bars (5-min)
CREATE TABLE market_5min.equity_bars (
    symbol TEXT,
    ts_utc TIMESTAMPTZ,
    open DOUBLE PRECISION,
    high DOUBLE PRECISION,
    low DOUBLE PRECISION,
    close DOUBLE PRECISION,
    volume BIGINT,
    PRIMARY KEY (symbol, ts_utc)
);

-- Equity bars (15-min)
CREATE TABLE market_15min.equity_bars (LIKE market_5min.equity_bars);

-- Macro series
CREATE TABLE macro.series (
    series_id TEXT PRIMARY KEY,
    source TEXT,
    freq TEXT,
    last_updated TIMESTAMPTZ
);
```

---

## 📂 File Locations Quick Reference

| Need | Location |
|------|----------|
| **Main orchestrator** | `hermes/core/hermes_orchestrator.py` |
| **Pipeline entry** | `main orchestration loop/orchestrator/` |
| **Tool implementations** | `main orchestration loop/tools/` |
| **Model scripts** | `hermes/scripts/install_models/` |
| **GPU/NoLlama scripts** | `hermes/scripts/run_intel_gpu/` |
| **RAG index scripts** | `hermes/scripts/setup_index/` |
| **Pipeline seeds** | `main orchestration loop/pipeline_state.*.seed.json` |
| **Verification** | `main orchestration loop/verification/` |
| **Generated strategies** | `generated/<slug>/` |
| **Vault data scripts** | `FILE OF DATA/PROJECT/Vault/scripts/` |
| **Daedalus RSI** | `daedalus/` (separate system) |

---

## 🆘 Emergency Commands

```powershell
# Nuclear reset - stop everything
.\hermes\scripts\run_intel_gpu\00_stop_nollama.bat
taskkill /F /IM nollama.exe
taskkill /F /IM python.exe

# Clear all caches
Remove-Item -Recurse -Force "hermes/scripts/setup_index/__pycache__"
Remove-Item -Recurse -Force "main orchestration loop/__pycache__"
Remove-Item -Recurse -Force "daedalus/__pycache__"

# Rebuild from scratch
.\hermes\scripts\install_models\00_install_everything.bat
.\hermes\scripts\run_intel_gpu\01_start_nollama.bat
.\hermes\scripts\setup_index\01_build_index.bat
```

---

## 📞 Support Contacts

| Issue | Contact |
|-------|---------|
| GPU/NoLlama | Check `hermes/scripts/run_intel_gpu/README_RUN_INTEL_GPU.txt` |
| Cursor SDK | `hermes/connectivity/hermes_cursor_connectivity.py` |
| Pipeline logic | `main orchestration loop/orchestrator/` |
| Verification failures | `main orchestration loop/verification/` |
| Data ingestion | `FILE OF DATA/PROJECT/Vault/scripts/` |
| Daedalus RSI | `daedalus/orchestrator/campaign.py` |

---

**Last Updated:** July 2026  
**Version:** Hermes Orchestration v1.0  
**Status:** Production Ready