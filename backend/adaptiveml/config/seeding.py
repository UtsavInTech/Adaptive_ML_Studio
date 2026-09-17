"""Deterministic sub-seed derivation.

Every random component gets its own seed derived from the master seed and a stable component
name, so adding a component never shifts the seeds of the others.
"""

import hashlib


def derive_seed(master: int, component: str) -> int:
    digest = hashlib.sha256(f"{master}:{component}".encode()).digest()
    return int.from_bytes(digest[:4], "big")
