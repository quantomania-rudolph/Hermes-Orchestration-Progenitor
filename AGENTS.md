## Learned User Preferences

- **Agentic campaign orchestration:** When the operator supplies prompt files under `Agentic_campaign/Fix_*_prompts/` (or equivalent campaign folders), act as **lead orchestrator only** — do **not** implement agent deliverables in the parent session. Spin up **one dedicated subagent per `AGENT_*.md` prompt**, paste the **entire** prompt file verbatim (plus shared persona from `WAVE_CAMPAIGN.md`), and follow **wave order** (blocking waves first; parallel only when the campaign doc allows). Parent steps in only for: merge discipline, conflict resolution, verification gating, thermo-nuke audits when requested, and unblockers when a subagent fails or stalls. Never substitute parent implementation for 1B–1E (or equivalent) “to save time.”
- **Merge means both:** When the operator says **merge**, always do **both** (unless they explicitly say otherwise): (1) **internal** — fast-forward each agent branch into the campaign integration branch in `WAVE_CAMPAIGN.md` merge order (e.g. `fix2/agent-2b` → `fix2/integration`); (2) **main** — fast-forward `main` from that integration branch when the wave/campaign gate is green (`cd daedalus && python verification/run_all_daedalus_verifications.py` exit 0). Do not treat integration-only merge as done; `main` is the canonical published line.
- Operator owns verification gating (R18–R34, R51, adversary R27–R29); spine work stays on search → propose → mutate context → apply → archive/register only.
- Expect adversarial, honest audits of implementation quality against `daedalus/plans/MISSING.JSON` and frontier RSI references (AlphaEvolve, DGM, ADAS, QuantEvolve).
- During live campaigns, append architectural gaps to `daedalus/plans/RUN_GAPS.JSON` continuously with live evidence; write `phase_journal` entries at epoch stage boundaries, not only at campaign end.
- P1–P5 gap repair uses parallel agent spin-ups (one phase each); each agent must exit 0 on `python verification/run_all_daedalus_verifications.py` from `daedalus/`.
- Core Hermes/Daedalus work should match `01_HERMES_Tool_Registry`, `02_HERMES_Semantic_Pipeline`, and `03_HERMES_Architecture` — no stubs or half-wired tools when filling the orchestration skeleton.
- RSI research persona: specialize in search/mutation space, state clearly when the codebase is insufficient, and ground proposals in institutional search/mutate/apply patterns.
- First-campaign readiness is judged on real RSI signal/backtest evolution on the target tree, not loader-only or quarantine aux-file churn.
- Re-run verification suites and the pipeline after fixing errors rather than declaring done from a single pass.

## Learned Workspace Facts

- `Hermes_Orchestration` is the primary repo: `daedalus/` (RSI engine), `generated/` (evolved strategy targets), `main orchestration loop/` (Hermes semantic pipeline runner).
- Multi-workspace roots: `Hermes_Orchestration` (code), `FILE OF DATA` (architecture docs, `vault_equity` notebook, DAEDALUS pipeline specs), `NEAT Alpha Miner` (related mining project).
- `daedalus/plans/` — planning authority: `GATING+METRICS_Plan.md`, `DATA_INGESTION_POLICY.md`, `MISSING.JSON`, `RUN_GAPS.JSON`, `LIVE_RUN_HALTS.md`, `PLAN.JSON`, `live_run_halts_agentic_campaign/` (P0_BLOCK prompts live).
- `daedalus/plans/MISSING.JSON` is the phase-segmented P1–P5 gap inventory; `daedalus/plans/RUN_GAPS.JSON` is the live-run gap journal for the next agent spin-up.
- Campaign epoch spine: E0 grounding → E1/E2 search → E3/E4 verify → E5 assimilate, plus EM meta epoch; driver is `daedalus/orchestrator/campaign.py`.
- Live campaign target slug `simple_rsi_strategy`: canonical evolved tree under `generated/simple_rsi_strategy/`; fuller reference under `daedalus/RSI_scaled/simple_rsi_strategy/`.
- Live campaign entrypoint: `daedalus/verification/live/run_all_generated_campaigns.py --target simple_rsi_strategy` with `HERMES_CURSOR_EXECUTION=wsl_native`, `DAEDALUS_SEARCH_MODE=archive`, `DAEDALUS_META_MODE=agent_search`.
- OHLCV data contract: PostgreSQL `market_{5min|15min}.equity_bars` (FMP ingest per `vault_equity` notebook); loaders fall back to bundled sample CSV offline.
- Search spine direction per `PLAN.JSON`: program-database evolutionary loop (MAP-Elites/islands, archive-conditioned prompts) replacing UCB-on-site-grid hill-climbing.
- Frozen baseline pins `generated/<slug>/` under `daedalus/frozen/`; E5 assimilation can graduate accepted branches back to `generated/` when `DAEDALUS_GRADUATE_TO_TARGET` is enabled. Proposal queue (`proposal_queue/prop_*.json`) is the separate HERMES boundary — see `daedalus/RUN_FILES.md` § Graduation vs proposals.
- Key architecture references: `06_DAEDALUS_RSI_Architecture (7).md` in repo root; extended pipeline docs often live under `FILE OF DATA/`.
- **Gating + metrics:** spec `daedalus/plans/GATING+METRICS_Plan.md` v2.1; waves 1–3 in code; waves 4–7 prompts in `daedalus/agent_prompts/gating/`. Operator checklist: `daedalus/RUN_FILES.md`.

## Gating + Metrics Plan — plain English (v2.1)

**What this is for.** Daedalus already has a real verification gate: mutated code cannot promote itself. What we do not have yet is a proper scoring layer for quant strategies — Sharpe, drawdown, tail risk, training speed, and the self-improvement stats that tell you whether the loop is actually learning. The plan describes how to add that without letting the AI pick its own grades.

**The big idea: measure everything, gate on a small set.** We will hardcode a large library of metrics (roughly 50) in Python. Every candidate gets measured against all of them and the results go in the journal. But only **5 or 6** of those metrics actually decide promote vs reject for a given target. That small set is the “gate profile.” Think of it like a full blood panel vs the three numbers your doctor uses to clear you for surgery.

**Who is in charge (this was the main fix after review).** Three separate layers, no blurring:

1. **Operator policy** — You set the rules at campaign start: required safety checks, which metrics the agent is allowed to pick from, what it cannot relax. Fixed for the run.
2. **Cursor agent (WSL2)** — Reads the target codebase and *suggests* which 5–6 metrics should gate promotion. It does **not** promote anything. It does not write gate code.
3. **Python resolver** — Takes the suggestion, clamps it to your rules, and outputs the final frozen profile. Only that resolved profile feeds the existing gate cascade (R08 scalarizer → R26 accept/discard).

So: agent proposes, Python disposes. Same measurement-monopoly principle as before.

**What gets measured (high level).**

- **Trading:** Sharpe, Sortino, Jensen’s alpha, CVaR, drawdown, profit factor, hit rate vs payoff, turnover, slippage sensitivity, and similar.
- **Speed / ops:** wall time, time per trade, time per signal, pipeline dead time.
- **ML training:** samples per second, time to convergence, GPU use — via a standard `train_profile()` hook on the target when it exists.
- **Self-improvement (RSI):** learning rate per iteration (e.g. Δ Sharpe), stability of improvements, edit efficiency, drift from original objective, gate pass/fail rates. These mostly feed meta-epoch and dashboards, not single-candidate promotion unless explicitly enabled.

**How promotion works.** Cheap checks first (compile, tests, quick backtest smoke), then full backtest in an isolated sandbox copy. Metrics must be **finite and valid** on both baseline and mutant before scoring — bad or missing data means reject, not a silent zero. Mutants cannot fake metrics in stdout; the harness measures from outside (same anti-cheat idea as DGM reward-hacking lessons).

**How we know it works (not “we computed 45 numbers”).** Each phase has pass/fail tests with real thresholds: golden values for formulas, 10 reruns must match, a frozen corpus of labeled good/bad mutants must get the right verdict, false accept rate under 2%, throughput at least ~12 candidates/hour on the MVP path, etc. No phase ships on vibes.

**Build order (contract-first).** Do not wire the full pipeline on day one.

- **G0:** Data shapes, policy file, resolver logic — tests only.
- **G1:** Small MVP metric set + default profile for `simple_rsi_strategy`.
- **G2:** End-to-end path from measure → score → journal + oracle tests.
- **G3–G6:** More metrics, then the Cursor gate-picker agent, then ML and extended quant metrics behind flags.
- **G7:** Hardening and live dry-run.

**Defaults already chosen (override via policy file before E0).**

- Pytest correctness anchors stay; CVaR is a risk gate, not a fourth anchor.
- Slippage sensitivity uses fixed 5 bps for now.
- Gate agent runs at epoch 0 and again if improvement gets unstable.
- CSV sample data offline; PostgreSQL when `DATABASE_URL` is set.
- New gate profiles get a **shadow epoch** (journal only) before they control promotion.

**Status.** Waves **1–7 implemented** (contracts through G7 campaign readiness: full AC table, R29/R51 quant hardening, dry-run harness, `CAMPAIGN_READY` guard). `run_all_daedalus_verifications.py` must exit 0 before live smoke; `run_all_gating_verifications.py --ready` currently fails **KNOBS P01** (envelope quant-default vs legacy test fixture — see `plans/LIVE_RUN_HALTS.md` HALT-P0-003). Live Cursor path: `run_all_gating_verifications.py --live`. See `daedalus/agent_prompts/gating/00_ORCHESTRATION.md`. Live blockers: `daedalus/plans/LIVE_RUN_HALTS.md`.

**Implementation agent prompts:** `daedalus/agent_prompts/gating/00_ORCHESTRATION.md` — waves 1–7 (AGENT_A–J).

