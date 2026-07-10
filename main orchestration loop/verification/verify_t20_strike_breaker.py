#!/usr/bin/env python3
import sys
from pathlib import Path

LOOP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LOOP_DIR))
from tools.safety.t20_strike_breaker import StrikeBreaker  # noqa: E402


def main() -> int:
    sb = StrikeBreaker(cap=3)
    state: dict = {"strike_ledger": {}}
    for i in range(3):
        state, c = sb.record_strike(state, "f.py", "err:abc")
    if not sb.is_strikeout(c):
        print("[FAIL] Should strike out at 3")
        return 1
    print("[OK] Strike-out at 3")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
