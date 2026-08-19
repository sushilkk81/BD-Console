"""External reference-data lookups: openFDA (free, no key) for strengths/cartridge/fill,
Tavily + Claude for viscosity literature search and brand-website fallback.

See docs/superpowers/specs/2026-08-19-external-reference-lookup-design.md for the full design.

Every public LookupService method swallows all exceptions internally and returns a
found=False result — nothing here should ever raise into the router.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.config import Settings, get_settings

logger = logging.getLogger("external_lookup")

FDA_LABEL_URL = "https://api.fda.gov/drug/label.json"
TAVILY_SEARCH_URL = "https://api.tavily.com/search"
ANTHROPIC_MODEL = "claude-opus-5"
HTTP_TIMEOUT_SECONDS = 10.0


def cartridge_for_fill(fill_ml: float) -> str:
    """Deterministic business rule — NOT delegated to the LLM. The LLM only ever extracts
    raw fill_ml numbers; this function decides the matching cartridge size."""
    return "1.5 mL" if fill_ml <= 1.5 else "3 mL"


@dataclass
class StrengthLookupResult:
    found: bool
    molecule: str | None = None
    device: str | None = None
    strengths: list[dict] = field(default_factory=list)
    citation: str | None = None


@dataclass
class ViscosityLookupResult:
    found: bool
    visc_val: float | None = None
    citation: str | None = None


class LookupService:
    """Owns every outbound call this app makes to FDA/Tavily/Claude.

    A FastAPI dependency (get_lookup_service) hands one of these to each router request;
    tests override that dependency with a fake to avoid any real network call.
    """

    def __init__(self, settings: Settings):
        self.settings = settings

    def lookup_strengths(self, brand: str, market: str) -> StrengthLookupResult:
        try:
            label = self._fetch_fda_label(brand)
            search_results: list[dict] = []
            if label is None:
                if not self.settings.tavily_api_key:
                    return StrengthLookupResult(found=False)
                search_results = self._search_tavily(f"{brand} manufacturer prescribing information")
                if not search_results:
                    return StrengthLookupResult(found=False)
            if not self.settings.anthropic_api_key:
                return StrengthLookupResult(found=False)
            return self._extract_strengths_with_claude(brand, label, search_results)
        except Exception:
            logger.warning("lookup_strengths failed for brand=%r market=%r", brand, market, exc_info=True)
            return StrengthLookupResult(found=False)

    def lookup_viscosity(self, brand: str, molecule: str | None) -> ViscosityLookupResult:
        try:
            if not self.settings.tavily_api_key or not self.settings.anthropic_api_key:
                return ViscosityLookupResult(found=False)
            query = f"{molecule or brand} injectable formulation viscosity cP"
            search_results = self._search_tavily(query)
            if not search_results:
                return ViscosityLookupResult(found=False)
            return self._synthesize_viscosity_with_claude(brand, molecule, search_results)
        except Exception:
            logger.warning("lookup_viscosity failed for brand=%r", brand, exc_info=True)
            return ViscosityLookupResult(found=False)

    # --- internal helpers (network/LLM calls — filled in in Task 4) ---

    def _fetch_fda_label(self, brand: str) -> dict | None:
        raise NotImplementedError

    def _search_tavily(self, query: str) -> list[dict]:
        raise NotImplementedError

    def _extract_strengths_with_claude(
        self, brand: str, label: dict | None, search_results: list[dict]
    ) -> StrengthLookupResult:
        raise NotImplementedError

    def _synthesize_viscosity_with_claude(
        self, brand: str, molecule: str | None, search_results: list[dict]
    ) -> ViscosityLookupResult:
        raise NotImplementedError


def get_lookup_service() -> LookupService:
    return LookupService(settings=get_settings())
