# Hermes Orchestration — Autonomous Code Factory

> **Core Law:** *Hermes proposes. Python disposes.*

An autonomous software factory that executes a 5-phase pipeline (P0–P5) using 30 specialized tools (T01–T30). Hermes orchestrates code generation, verification, and integration — running locally on Windows with Intel Arc GPU via NoLlama, or via Cursor SDK.

---

## 🎯 What This Does

| Capability | Description |
|------------|-------------|
| **Autonomous Development** | Takes a seeded objective → produces tested, verified, integrated code |
| **Semantic Pipeline** | 5 phases: Genesis → Blueprint → Implement → Audit → Integrate → Reconcile |
| **Tool Registry** | 30 tools (T01–T30) covering AST, RAG, Cursor agents, verification, git, WAL |
| **Local-First LLM** | Runs Qwen2.5-Coder-14B on Intel Arc GPU via NoLlama (no cloud required) |
| **Cursor Fallback** | Falls back to Cursor SDK when local bridge fails (Windows) |
| **Trading-Ready** | Pre-seeded strategies: RSI, LSTM/Optuna, Pairs/UKF, Factor Momentum, etc. |

---

## 📁 Repository Structure

```
Hermes_Orchestration/
├── README.md                    ← YOU ARE HERE
├── HOW_TO_RUN.md               ← Detailed runbook
├── .env.example                # Template for secrets
├── .env.local                  # Your secrets (gitignored)
├── AGENTS.md                   # Agent instructions
│
├── hermes/                     # Core Hermes runtime (NEW organized structure)
│   ├── core/                   # Orchestrator, preflight, secrets, NoLlama client
│   ├── config/                 # Configuration & embeddings
│   ├── connectivity/           # Cursor bridge, WSL launcher, live stack
│   └── scripts/                # Model install, GPU ops, RAG indexing
│       ├── install_models/     # One-time model downloads
│       ├── run_intel_gpu/      # Daily NoLlama/GPU operations
│       └── setup_index/        # Codebase RAG index build
│
├── main orchestration loop/    # Full 5-phase pipeline implementation
│   ├── config/                 # Loop config, 30-tool registry
│   ├── state/                  # WAL, snapshots, AST map, alerts
│   ├── orchestrator/           # Session loop, phases, contracts, gauntlet
│   ├── tools/                  # T01–T30 implementations (7 categories)
│   ├── models/                 # Hermes Qwen, classifiers, schemas
│   ├── agents/                 # Cursor SDK, prompts, sync barrier
│   ├── docs/schemas/           # Fuzz sources
│   ├── system_tools/           # Synthesized tools (quarantine/active)
│   ├── run/                    # Windows batch launchers
│   └── verification/           # 8-script test suite
│
├── generated/                  # Evolved strategy outputs (10 slugs)
│   ├── simple_rsi_strategy/
│   ├── lstm_optuna_vault_trader/
│   ├── pairs_regime_ukf_trader/
│   └── ... (6 more)
│
├── Agentic_campaign/           # 5 fix campaigns with prompts
│   ├── Fix_1_prompts/ ... Fix_5_prompts/
│   └── FIX_1.md ... FIX_5.md
│
└── daedalus/                   # RSI ENGINE — SEPARATE PROJECT
    # (25+ subdirs: agents, orchestrator, search, metrics, frozen, etc.)
    # NOT included in Hermes — see daedalus/README.md
```

---

## 🔑 Requirements to Run

### **Hardware**
- **Intel Arc GPU** (A750/A770 or better) — for local Qwen via NoLlama
- **32 GB+ RAM** recommended
- **Windows 10/11** (primary) or WSL2 Ubuntu

### **Software**
| Component | Version | Purpose |
|-----------|---------|---------|
| Python | 3.11+ | Main runtime |
| NoLlama | Latest | Local LLM server for Qwen |
| Cursor IDE | Latest | Cursor SDK bridge (optional) |
| Git | Latest | Version control |
| PowerShell 7+ | 7.4+ | Launch scripts |

### **API Keys** (in `.env.local`)
```bash
CURSOR_API_KEY=sk-...          # Required for live Cursor agent spawns
HERMES_T09_RUNTIME=auto        # auto | cursor | qwen
```

### **Data Dependencies**
| Data Source | Purpose | Location |
|-------------|---------|----------|
| **FMP API** | Equity bars, fundamentals, splits | Vault equity pipeline |
| **Yahoo Finance** | Macro, forex, commodities | Vault macro pipeline |
| **PostgreSQL** | `market_5min.equity_bars`, `market_15min.equity_bars` | OHLCV storage |
| **Codebase vectors** | RAG index for T07 | `codebase_vectors.json` (built locally) |

---

## ⚡ Quick Start (30 seconds)

```powershell
# 1. Clone & enter
cd C:\Users\Rudol\Desktop\Hermes_Orchestration

# 2. Configure secrets
copy .env.example .env.local
# Edit .env.local → paste CURSOR_API_KEY

# 3. One-time setup (downloads ~14GB model)
.\hermes\scripts\install_models\00_install_everything.bat

# 4. Start NoLlama on GPU
.\hermes\scripts\run_intel_gpu\01_start_nollama.bat

# 5. Build RAG index
.\hermes\scripts\setup_index\01_build_index.bat

# 6. Verify GPU access
.\hermes\scripts\run_intel_gpu\04_verify_gpu_access.bat

# 7. Run a test task
python .\hermes\core\hermes_orchestrator.py "create a hello world module"
```

---

## 📊 What Data It Needs

### **For Trading Strategies (generated/)**
| Strategy | Data Required | Source |
|----------|---------------|--------|
| `simple_rsi_strategy` | 5-min equity bars, RSI(14) | FMP → PostgreSQL |
| `lstm_optuna_vault_trader` | 15-min bars, optuna studies | FMP + local optuna |
| `pairs_regime_ukf_trader` | Pair correlations, regime labels | Vault equity + stats |
| `factor_momentum_portfolio` | Factor returns, universe | FMP fundamentals |

### **For Vault Ingestion** (`FILE OF DATA/PROJECT/Vault/`)
| Asset Class | Scripts | Frequency |
|-------------|---------|-----------|
| Equities | `ingest_equity_*.py` | Daily EOD |
| Forex | `ingest_forex_*.py` | Hourly |
| Commodities | `ingest_commodity_*.py` | Daily |
| Indices | `ingest_index_*.py` | 5-min / 15-min |
| Macro | `ingest_macro_*.py` | FRED/Yahoo daily |
| Corporate Actions | `etl_yahoo_corp_actions.py` | Daily |

---

## 🚫 What's NOT Included

| Excluded | Reason |
|----------|--------|
| `daedalus/` | Separate RSI evolution engine — own repo |
| `FILE OF DATA/` | Raw data + cleaning — separate repo (`Quant-Data-Cleaning-and-Ingestion`) |
| Model weights | Downloaded on first run (`install_models/`) |
| PostgreSQL DB | External — configure in `.env.local` |
| Cursor API key | User-provided in `.env.local` |

---

## 📚 Key Documentation

| File | Purpose |
|------|---------|
| `HOW_TO_RUN.md` | **Complete runbook** — every command, mode, troubleshooting |
| `main orchestration loop/README.md` | Pipeline architecture, phase flow, modes |
| `hermes/scripts/START_HERE.txt` | Three-pillar setup summary |
| `AGENTS.md` | Agent behavior rules |
| `architecture.md` | T13 semantic contract |

---

## 🆘 Support

- **Verification suite**: `python "main orchestration loop\verification\run_all_verifications.py"`
- **GPU issues**: `.\hermes\scripts\run_intel_gpu\00_stop_nollama.bat` → `01_restart_nollama.bat`
- **Index issues**: `.\hermes\scripts\setup_index\03_verify_index.bat`
- **Model issues**: `.\hermes\scripts\install_models\04_verify_all_models_installed.bat`

---

**License**: Proprietary — Internal use only  
**Maintainer**: Hermes Orchestration Team