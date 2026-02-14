"""Secure random utilities for Scala 40."""

import random
import secrets


def create_rng(seed: int | None = None) -> random.Random:
    """Create a Random instance.

    If seed is provided, returns a deterministic Random (for tests/replay).
    If seed is None, returns SystemRandom (cryptographically secure).
    """
    if seed is not None:
        return random.Random(seed)
    return secrets.SystemRandom()


def generate_lobby_code(length: int = 6) -> str:
    """Generate an alphanumeric lobby code (no ambiguous chars)."""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(length))
