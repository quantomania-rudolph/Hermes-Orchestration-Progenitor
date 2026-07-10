#!/usr/bin/env python3
import sys
from pathlib import Path

LOOP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(LOOP_DIR))
from tools.verification.t19_error_normalizer import ErrorNormalizer  # noqa: E402


def main() -> int:
    n = ErrorNormalizer()
    a = n.normalize("TypeError at line 42 in foo\n  in validate\n  in run")
    b = n.normalize("TypeError at line 99 in foo\n  in validate\n  in run")
    if a.hash != b.hash:
        print("[FAIL] Line shift changed hash")
        return 1
    print(f"[OK] Stable hash: {a.signature}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
