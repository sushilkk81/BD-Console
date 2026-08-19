"""External reference-data lookups: openFDA (free, no key) for strengths/cartridge/fill,
Tavily + Claude for viscosity literature search and brand-website fallback.

See docs/superpowers/specs/2026-08-19-external-reference-lookup-design.md for the full design.

Every public LookupService method swallows all exceptions internally and returns a
found=False result — nothing here should ever raise into the router.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import anthropic
import httpx

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
        self._http_client: httpx.Client | None = None
        self._anthropic_client: "anthropic.Anthropic | None" = None

    @property
    def http_client(self) -> httpx.Client:
        if self._http_client is None:
            self._http_client = httpx.Client(timeout=HTTP_TIMEOUT_SECONDS)
        return self._http_client

    @property
    def anthropic_client(self) -> "anthropic.Anthropic":
        if self._anthropic_client is None:
            self._anthropic_client = anthropic.Anthropic(api_key=self.settings.anthropic_api_key)
        return self._anthropic_client

    def lookup_strengths(self, brand: str, market: str) -> StrengthLookupResult:
        try:
            if not self.settings.anthropic_api_key:
                return StrengthLookupResult(found=False)
            label = self._fetch_fda_label(brand)
            search_results: list[dict] = []
            if label is None:
                if not self.settings.tavily_api_key:
                    return StrengthLookupResult(found=False)
                search_results = self._search_tavily(f"{brand} manufacturer prescribing information")
                if not search_results:
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
        resp = self.http_client.get(
            FDA_LABEL_URL,
            params={"search": f'openfda.brand_name:"{brand}" AND openfda.route:"SUBCUTANEOUS"', "limit": 1},
            timeout=HTTP_TIMEOUT_SECONDS,
        )
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError:
            return None
        results = resp.json().get("results", [])
        return results[0] if results else None

    def _search_tavily(self, query: str) -> list[dict]:
        resp = self.http_client.post(
            TAVILY_SEARCH_URL,
            json={"api_key": self.settings.tavily_api_key, "query": query, "max_results": 10},
            timeout=HTTP_TIMEOUT_SECONDS,
        )
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError:
            return []
        return resp.json().get("results", [])

    def _extract_strengths_with_claude(
        self, brand: str, label: dict | None, search_results: list[dict]
    ) -> StrengthLookupResult:
        source_text = (
            (label or {}).get("dosage_forms_and_strengths", "")
            or "\n".join(r.get("content", "") for r in search_results)
        )
        tool = {
            "name": "record_strengths",
            "description": "Record the extracted strengths and presentation for a drug product.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "molecule": {"type": "string"},
                    "device": {"type": ["string", "null"]},
                    "strengths": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "strength": {"type": "string"},
                                "fill_ml": {"type": "number"},
                            },
                            "required": ["strength", "fill_ml"],
                            "additionalProperties": False,
                        },
                    },
                    "citation": {"type": "string"},
                },
                "required": ["molecule", "strengths", "citation"],
                "additionalProperties": False,
            },
            "strict": True,
        }
        message = self.anthropic_client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=1024,
            tools=[tool],
            tool_choice={"type": "tool", "name": "record_strengths"},
            messages=[{
                "role": "user",
                "content": (
                    f"Extract every strength and its fill volume (in mL) for the drug product "
                    f"'{brand}' from this label/reference text:\n\n{source_text}"
                ),
            }],
        )
        tool_use = next(b for b in message.content if b.type == "tool_use")
        data = tool_use.input
        strengths = [
            {
                "strength": s["strength"],
                "cartridge": cartridge_for_fill(float(s["fill_ml"])),
                "fill_ml": float(s["fill_ml"]),
            }
            for s in data.get("strengths", [])
        ]
        if not strengths:
            return StrengthLookupResult(found=False)
        return StrengthLookupResult(
            found=True,
            molecule=data.get("molecule"),
            device=data.get("device"),
            strengths=strengths,
            citation=data.get("citation"),
        )

    def _synthesize_viscosity_with_claude(
        self, brand: str, molecule: str | None, search_results: list[dict]
    ) -> ViscosityLookupResult:
        source_text = "\n\n".join(
            f"{r.get('title', '')}\n{r.get('content', '')}" for r in search_results
        )
        tool = {
            "name": "record_viscosity",
            "description": "Record a synthesized viscosity value from literature search results.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "visc_val": {"type": ["number", "null"]},
                    "citation": {"type": "string"},
                },
                "required": ["visc_val", "citation"],
                "additionalProperties": False,
            },
            "strict": True,
        }
        message = self.anthropic_client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=512,
            tools=[tool],
            tool_choice={"type": "tool", "name": "record_viscosity"},
            messages=[{
                "role": "user",
                "content": (
                    f"Based on this literature search on the viscosity of {molecule or brand} "
                    f"injectable formulations, give a single representative viscosity value in cP "
                    f"if the literature supports one clean figure; otherwise return null. "
                    f"Cite your source.\n\n{source_text}"
                ),
            }],
        )
        tool_use = next(b for b in message.content if b.type == "tool_use")
        data = tool_use.input
        visc_val = data.get("visc_val")
        if visc_val is None:
            return ViscosityLookupResult(found=False)
        return ViscosityLookupResult(found=True, visc_val=float(visc_val), citation=data.get("citation"))


def get_lookup_service() -> LookupService:
    return LookupService(settings=get_settings())
