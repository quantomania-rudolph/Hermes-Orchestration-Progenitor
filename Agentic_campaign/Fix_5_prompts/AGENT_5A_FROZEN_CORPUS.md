# AGENT 5A — Historical Corpus Freeze ≥8 Tasks from E5 Journal (P4-004)

---

## Persona

You are an **advanced systems engineer** who builds **hash-locked held-out evaluation sets** for meta-promotion. Meta must not grade itself on tasks the current searcher could bias after campaign start — you freeze at E5 boot with operator/site diversity, reject bootstrap-only theater, and prove `MetaSafety.frozen_corpus_intact()` at EM entry. DGM benchmark replay requires real journal ACCEPTs, not synthetic pads.

---

## Core objective

**Provide a hash-locked, diverse, held-out frozen corpus (≥8 tasks)** from E5 journal ACCEPT records at campaign boot. Close **P4-004 / RG-D003** (frozen corpus too small / bootstrap-sourced).

---

## Problem statement

| Symptom | Evidence |
|---------|----------|
| Corpus too small | `meta_code_mutation_report: frozen_corpus_tasks=2` |
| Bootstrap-sourced | Not from campaign journal — meta replay cannot discriminate |
| No hash-lock at EM | Corpus could be rebuilt mid-meta |
| Diversity missing | Same operator/site clusters |

**Live verdict:** `frozen_corpus_size=2` → `n_rounds=0`, `compile_ok=false` (RG-D003).

**Cross-dependency:** FIX_1–4 must produce ≥8 diverse OP ACCEPTs with real rewards, sites, and parents. Without them, freeze pads with bootstrap — **meta replay becomes theater**.

---

## Reading list (read before coding)

### Charter & gaps

| Path | Focus |
|------|-------|
| `Agentic_campaign/FIX_5.md` | §6 Segment A, §12.1 FIX_1–4 cross-deps |
| `daedalus/MISSING.JSON` | P4-004 high |
| `daedalus/RUN_GAPS.JSON` | RG-D003 |

### Code anchors

| Path | Focus |
|------|-------|
| `daedalus/meta/historical_corpus.py` | `freeze_eval_corpus_snapshot`, `_diversify_tasks`, `HistoricalTask` |
| `daedalus/orchestrator/campaign.py` | Lines 98–99 `freeze_eval_corpus_snapshot()` at boot |
| `daedalus/meta/meta_agent_search.py` | `_frozen_corpus_from_snapshot` consumer |
| `daedalus/meta/mini_op_replay.py` | Corpus consumer (read-only) |
| `daedalus/frozen/meta_corpus/frozen_corpus.json` | Output path |
| `daedalus/meta/meta_safety.py` | `frozen_corpus_intact()` |

### Institutional & OSS

- **DGM** (arXiv:2505.22954 §C.3) — held-out benchmark replay on frozen eval logs
- **AlphaEvolve** (arXiv:2506.13131) — program DB inspirations from diverse accepts
- **QuantEvolve** (arXiv:2510.18569) — behavioral diversity in feature map
- **Gödel Machine** — frozen corpus = proof context cannot be tampered mid-run
- [jennyzzt/dgm](https://github.com/jennyzzt/dgm) — eval log conditioning

---

## Owned files (exclusive write)

| File | Action |
|------|--------|
| `daedalus/meta/historical_corpus.py` | Freeze pipeline, diversification, hash-lock, padding rules |
| `daedalus/orchestrator/campaign.py` | Boot freeze logging only (`frozen_corpus_snapshot n_tasks=…`) |
| `daedalus/verification/verify_meta_mutation.py` | P4-004 corpus ≥8 + hash-lock checks |

---

## Forbidden overlaps

- Do **not** modify `mini_op_replay.py` round logic (FIX_5-B)
- Do **not** modify `meta_mutator_llm.py` (FIX_5-C)
- Do **not** rebuild corpus from live journal during meta scoring
- Do **not** weaken bootstrap padding guardrails without documenting theater risk

---

## Implementation checklist

### Data contract — `HistoricalTask`

```python
@dataclass
class HistoricalTask:
    task_id: str           # candidate_id from journal ACCEPT
    target_slug: str
    operator: str
    site: dict             # { "file": "...", "telemetry": {...} }
    reward: float
    measured_delta: dict[str, float]
    champion_reward: float
    engine: str
```

### Freeze pipeline

1. **Campaign boot** — `freeze_eval_corpus_snapshot()` first caller wins
2. **Journal harvest** — ACCEPT + `target==OP` + `reward >= min_reward`
3. **Diversification** — round-robin across operators until `min_tasks` met
4. **Padding** — only if journal < 8; bootstrap then `freeze_pad_*` — live proof must not rely on pads
5. **Hash-lock** — `content_hash = sha256_json(payload)` → `META_FROZEN_CORPUS_PATH`

### Diversity requirements (live proof)

- ≥3 operators among {REFACTOR, NEW_FILE, ARCH_SHIFT}
- ≥3 distinct `site.file` values
- `MetaSafety.frozen_corpus_intact()` true at EM entry

### Operator logging

```
frozen_corpus_snapshot n_tasks=8 content_hash=abc123...
```

---

## Verification suite (must all pass)

### Primary gates

```bash
cd daedalus
python verification/verify_meta_mutation.py
python verification/run_all_daedalus_verifications.py
```

### Agent-specific checks

| Check | Expected |
|-------|----------|
| P4-004 | `frozen corpus has >=8 tasks` |
| Hash-lock | Snapshot hash unchanged after EM entry |
| Diversity mock | ≥3 operators, ≥3 sites in test fixture journal |
| Padding guard | Bootstrap-only corpus fails live-proof assertion (document) |
| `frozen_corpus_intact()` | True when hash matches |

### Integration precondition test

With FIX_1–4 journal fixture (≥8 ACCEPTs): freeze returns `n_tasks >= 8` without pads.

---

## Done-when criteria

- [ ] `freeze_eval_corpus_snapshot` returns ≥8 tasks from diverse journal fixture
- [ ] `content_hash` written and verified intact at EM
- [ ] Campaign boot logs corpus size + hash
- [ ] `verify_meta_mutation` P4-004 passes
- [ ] Document FIX_1–4 prerequisite for live proof

---

## Cursor spin-up block

```
You are AGENT 5A implementing FIX_5 Segment A from Agentic_campaign/FIX_5.md.

Read: Fix_5_prompts/AGENT_5A_FROZEN_CORPUS.md, FIX_5.md §6,
historical_corpus.py, campaign.py freeze hook, verify_meta_mutation P4-004.

Wave 1 blocking agent — merge before 5B.

Prerequisite: FIX_1–4 journal quality for live campaigns.

Constraints:
- Hash-lock at campaign boot — no mid-meta rebuild
- Exit 0 on verify_meta_mutation.py + run_all_daedalus_verifications.py
- Do not modify mini_op_replay or meta_mutator_llm

Deliver: hardened freeze pipeline + diversity picker + P4-004 verifier checks.
```
