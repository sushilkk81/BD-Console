"""External reference-data lookups: openFDA (free, no key) for strengths/cartridge/fill,
Tavily + Claude for viscosity literature search and brand-website fallback.

See docs/superpowers/specs/2026-08-19-external-reference-lookup-design.md for the full design.
"""
from __future__ import annotations


def cartridge_for_fill(fill_ml: float) -> str:
    """Deterministic business rule — NOT delegated to the LLM. The LLM only ever extracts
    raw fill_ml numbers; this function decides the matching cartridge size."""
    return "1.5 mL" if fill_ml <= 1.5 else "3 mL"
