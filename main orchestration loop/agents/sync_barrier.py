"""T09->T10 sync barrier — delegates to Daedalus unified implementation."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DAEDALUS = _REPO_ROOT / "daedalus"
_HERMES = _REPO_ROOT / "main orchestration loop"
_DAEDALUS_SB = _DAEDALUS / "agents" / "sync_barrier.py"


def _load_daedalus_sync_barrier():
    saved_path = sys.path[:]
    partial_key = "agents.sync_barrier"
    partial = sys.modules.pop(partial_key, None)
    try:
        sys.path = [str(_DAEDALUS), str(_REPO_ROOT)] + [
            p for p in saved_path
            if p not in (str(_DAEDALUS), str(_REPO_ROOT), str(_HERMES))
        ]
        spec = importlib.util.spec_from_file_location(
            "_daedalus_sync_barrier_impl",
            _DAEDALUS_SB,
        )
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot load Daedalus sync_barrier from {_DAEDALUS_SB}")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)
        return mod
    finally:
        if partial is not None:
            sys.modules[partial_key] = partial
        sys.path = saved_path


_daedalus_sync = _load_daedalus_sync_barrier()

SyncBarrierTimeout = _daedalus_sync.SyncBarrierTimeout
file_hash = _daedalus_sync.file_hash
wait_consistent = _daedalus_sync.wait_consistent
wait_for_files = _daedalus_sync.wait_for_files

__all__ = [
    "SyncBarrierTimeout",
    "file_hash",
    "wait_consistent",
    "wait_for_files",
    "_daedalus_sync",
]
