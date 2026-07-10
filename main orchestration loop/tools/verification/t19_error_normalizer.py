"""T19 — Error-Class Normalizer."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass


@dataclass
class NormalizedError:
    signature: str
    hash: str
    opaque: bool


class ErrorNormalizer:
    def normalize(self, raw_trace: str) -> NormalizedError:
        exc = re.search(r"(\w+Error|\w+Exception)", raw_trace)
        exc_class = exc.group(1) if exc else "UnknownError"
        funcs = re.findall(r"in (\w+)", raw_trace)
        func_chain = ">".join(funcs[:8])
        scrubbed = re.sub(r"line \d+", "line N", raw_trace)
        scrubbed = re.sub(r":\d+:\d+", ":N:N", scrubbed)
        signature = f"{exc_class}@{func_chain}" if func_chain else exc_class
        digest = "err:" + hashlib.sha256(signature.encode()).hexdigest()[:16]
        opaque = exc_class == "UnknownError" and not func_chain
        if opaque:
            digest = "err:" + hashlib.sha256(raw_trace[:500].encode()).hexdigest()[:16]
        return NormalizedError(signature=signature, hash=digest, opaque=opaque)
