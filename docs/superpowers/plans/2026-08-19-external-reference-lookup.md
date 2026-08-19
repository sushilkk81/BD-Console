# External Reference-Data Lookup Agents Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the customer wizard's static "Need assistance" viscosity copy and closed brand list with real, on-demand external lookups (openFDA for strengths/cartridge/fill, Tavily + Claude for viscosity literature search), persisting results into the existing reference-data tables so the core matching engine is untouched.

**Architecture:** A new `LookupService` class in `backend/app/services/external_lookup.py` owns all outbound HTTP/LLM calls behind a FastAPI-injectable seam (`get_lookup_service`, mirroring the existing `get_db` pattern). A new router (`backend/app/routers/reference_lookup.py`) exposes two cache-first endpoints that upsert into `ReferenceProduct`/`ReferenceProductMarket` on a successful lookup. The frontend wizard gains two on-demand trigger buttons that call these endpoints and merge results into local state — no change to the existing request-creation/update flow.

**Tech Stack:** FastAPI, SQLAlchemy, httpx, `anthropic` Python SDK (`claude-opus-5`), Tavily REST API, Next.js/React (frontend).

**Spec:** `docs/superpowers/specs/2026-08-19-external-reference-lookup-design.md`

## Global Constraints

- Every external call (openFDA, Tavily, Claude) must fail gracefully — network error, missing API key, no match, or bad LLM output all collapse to `found: false` in a normal `200` response. Nothing external-facing raises an unhandled exception into the router.
- No API key configured → short-circuit to `found: false` before any network call.
- The `cartridge_for_fill` mapping (≤1.5 mL → `"1.5 mL"`, else `"3 mL"`) is deterministic Python, never delegated to the LLM.
- Cache-first: check the DB for an existing row before calling anything external.
- A strengths lookup upserts `ReferenceProductMarket` (never overwrites an existing `ReferenceProduct` base row's fields); a viscosity lookup upserts the `ReferenceProduct` base row only (`ReferenceProductMarket` has no `visc_val` column).
- All httpx calls carry an explicit ~8–10s timeout.
- Model is `claude-opus-5` (per `claude-api` skill defaults — do not substitute a cheaper model without being asked).

---

### Task 1: Settings, dependency, and env plumbing

**Files:**
- Modify: `backend/app/config.py`
- Modify: `backend/requirements.txt`
- Modify: `.env.example`
- Modify: `docker-compose.yml`
- Modify: `CLAUDE.md`

**Interfaces:**
- Produces: `Settings.anthropic_api_key: str` (default `""`), `Settings.tavily_api_key: str` (default `""`), read via the existing `get_settings()`.

- [ ] **Step 1: Add the two settings fields**

In `backend/app/config.py`, add to the `Settings` class (after `cors_origins`):

```python
    anthropic_api_key: str = ""
    tavily_api_key: str = ""
```

- [ ] **Step 2: Add the `anthropic` dependency**

In `backend/requirements.txt`, add a line (keep alphabetical if the file already is, otherwise append):

```
anthropic==0.69.0
```

- [ ] **Step 3: Install it**

Run: `cd backend && .venv/bin/pip install -r requirements.txt`
Expected: `anthropic` installs successfully alongside existing deps.

- [ ] **Step 4: Document the new env vars**

In `.env.example`, append:

```
ANTHROPIC_API_KEY=
TAVILY_API_KEY=
```

In `docker-compose.yml`, add two lines to the `backend` service's `environment:` block (after `CORS_ORIGINS`):

```yaml
      ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY:-}
      TAVILY_API_KEY: ${TAVILY_API_KEY:-}
```

- [ ] **Step 5: Note the new optional env vars in CLAUDE.md**

In `CLAUDE.md`'s backend section, add one sentence near the existing `PYTHONPATH=. DATABASE_URL=...` pytest command block noting: `ANTHROPIC_API_KEY` and `TAVILY_API_KEY` are optional — the `/reference-lookup/*` endpoints degrade to `found: false` when unset, so the test suite and local dev both work without them.

- [ ] **Step 6: Commit**

```bash
git add backend/app/config.py backend/requirements.txt .env.example docker-compose.yml CLAUDE.md
git commit -m "chore: add optional ANTHROPIC_API_KEY/TAVILY_API_KEY settings"
```

---

### Task 2: `cartridge_for_fill` — the one piece of pure business logic

**Files:**
- Create: `backend/app/services/external_lookup.py`
- Test: `backend/tests/test_external_lookup.py`

**Interfaces:**
- Produces: `cartridge_for_fill(fill_ml: float) -> str`, importable as `from app.services.external_lookup import cartridge_for_fill`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_external_lookup.py`:

```python
from app.services.external_lookup import cartridge_for_fill


def test_cartridge_for_fill_at_or_below_1_5ml():
    assert cartridge_for_fill(1.5) == "1.5 mL"
    assert cartridge_for_fill(1.0) == "1.5 mL"
    assert cartridge_for_fill(0.5) == "1.5 mL"


def test_cartridge_for_fill_above_1_5ml():
    assert cartridge_for_fill(1.51) == "3 mL"
    assert cartridge_for_fill(3.0) == "3 mL"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && PYTHONPATH=. DATABASE_URL="sqlite:///:memory:" JWT_SECRET=test CORS_ORIGINS='["http://localhost:3000"]' .venv/bin/pytest tests/test_external_lookup.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.external_lookup'`

- [ ] **Step 3: Write the minimal implementation**

Create `backend/app/services/external_lookup.py`:

```python
"""External reference-data lookups: openFDA (free, no key) for strengths/cartridge/fill,
Tavily + Claude for viscosity literature search and brand-website fallback.

See docs/superpowers/specs/2026-08-19-external-reference-lookup-design.md for the full design.
"""
from __future__ import annotations


def cartridge_for_fill(fill_ml: float) -> str:
    """Deterministic business rule — NOT delegated to the LLM. The LLM only ever extracts
    raw fill_ml numbers; this function decides the matching cartridge size."""
    return "1.5 mL" if fill_ml <= 1.5 else "3 mL"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && PYTHONPATH=. DATABASE_URL="sqlite:///:memory:" JWT_SECRET=test CORS_ORIGINS='["http://localhost:3000"]' .venv/bin/pytest tests/test_external_lookup.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/external_lookup.py backend/tests/test_external_lookup.py
git commit -m "feat: cartridge_for_fill deterministic mapping"
```

---

### Task 3: Result dataclasses and the `LookupService` seam

**Files:**
- Modify: `backend/app/services/external_lookup.py`
- Test: `backend/tests/test_external_lookup.py`

**Interfaces:**
- Consumes: `Settings` from `app.config.get_settings` (has `.anthropic_api_key`, `.tavily_api_key`).
- Produces:
  - `StrengthLookupResult` — fields `found: bool`, `molecule: str | None`, `device: str | None`, `strengths: list[dict] | None` (each dict: `{"strength": str, "cartridge": str, "fill_ml": float}`), `citation: str | None`.
  - `ViscosityLookupResult` — fields `found: bool`, `visc_val: float | None`, `citation: str | None`.
  - `LookupService(settings)` with methods `lookup_strengths(brand: str, market: str) -> StrengthLookupResult` and `lookup_viscosity(brand: str, molecule: str | None) -> ViscosityLookupResult`.
  - `get_lookup_service() -> LookupService` (module-level factory, FastAPI dependency target).
- This task stubs the two internal helpers (`_fetch_fda_label`, `_search_tavily`, `_extract_strengths_with_claude`, `_synthesize_viscosity_with_claude`) as private methods returning `None`/`[]` for now — Task 4 fills in the real HTTP/LLM bodies. `lookup_strengths`/`lookup_viscosity` are fully implemented in this task against those stubs, so their `found: False` no-key/no-data behavior is testable now without any network dependency.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_external_lookup.py`:

```python
from app.config import Settings
from app.services.external_lookup import LookupService, get_lookup_service


def test_lookup_strengths_no_key_configured_returns_not_found():
    svc = LookupService(settings=Settings(anthropic_api_key="", tavily_api_key=""))
    result = svc.lookup_strengths("Ozempic", "US")
    assert result.found is False


def test_lookup_viscosity_no_key_configured_returns_not_found():
    svc = LookupService(settings=Settings(anthropic_api_key="", tavily_api_key=""))
    result = svc.lookup_viscosity("Ozempic", "Semaglutide")
    assert result.found is False


def test_get_lookup_service_returns_a_lookup_service():
    assert isinstance(get_lookup_service(), LookupService)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && PYTHONPATH=. DATABASE_URL="sqlite:///:memory:" JWT_SECRET=test CORS_ORIGINS='["http://localhost:3000"]' .venv/bin/pytest tests/test_external_lookup.py -v`
Expected: FAIL — `ImportError: cannot import name 'LookupService'`

- [ ] **Step 3: Write the implementation**

Replace the contents of `backend/app/services/external_lookup.py` with:

```python
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
```

Note: `lookup_strengths`/`lookup_viscosity` only reach the `NotImplementedError` stubs when
a key *is* configured and there's label/search data to process — the two no-key tests above
short-circuit before ever calling them, so they pass against these stubs. The `except Exception`
wrapper also means a stray `NotImplementedError` from a configured-key path is safely caught
and reported as `found=False` until Task 4 lands, but no test in this task exercises that path.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && PYTHONPATH=. DATABASE_URL="sqlite:///:memory:" JWT_SECRET=test CORS_ORIGINS='["http://localhost:3000"]' .venv/bin/pytest tests/test_external_lookup.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/external_lookup.py backend/tests/test_external_lookup.py
git commit -m "feat: LookupService seam with graceful no-key short-circuit"
```

---

### Task 4: Real openFDA fetch, Tavily search, and Claude extraction/synthesis

**Files:**
- Modify: `backend/app/services/external_lookup.py`
- Test: `backend/tests/test_external_lookup.py`

**Interfaces:**
- Consumes: `StrengthLookupResult`, `ViscosityLookupResult`, `cartridge_for_fill` from Task 2/3.
- Produces: working bodies for `_fetch_fda_label`, `_search_tavily`, `_extract_strengths_with_claude`, `_synthesize_viscosity_with_claude`. No new public interface — callers (Task 5's router, and Task 3's `lookup_strengths`/`lookup_viscosity`) are unchanged.

This task's tests exercise the **fully-configured, but network-mocked** path — they inject a
fake `httpx.Client`-like object and a fake Anthropic client via constructor parameters, so no
real network or API key is needed in CI while still testing the four internal helpers'
parsing/mapping logic (the part that can actually have bugs).

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_external_lookup.py`:

```python
import httpx

from app.services.external_lookup import LookupService, StrengthLookupResult, ViscosityLookupResult


class _FakeHTTPResponse:
    def __init__(self, json_body, status_code=200):
        self._json = json_body
        self.status_code = status_code

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=None, response=self)


class _FakeHTTPClient:
    def __init__(self, fda_response=None, tavily_response=None):
        self._fda_response = fda_response
        self._tavily_response = tavily_response

    def get(self, url, params=None, timeout=None):
        return self._fda_response

    def post(self, url, json=None, timeout=None):
        return self._tavily_response


class _FakeAnthropicToolUseBlock:
    def __init__(self, input_dict):
        self.type = "tool_use"
        self.input = input_dict


class _FakeAnthropicMessage:
    def __init__(self, input_dict):
        self.content = [_FakeAnthropicToolUseBlock(input_dict)]


class _FakeAnthropicMessages:
    def __init__(self, response_input):
        self._response_input = response_input

    def create(self, **kwargs):
        return _FakeAnthropicMessage(self._response_input)


class _FakeAnthropicClient:
    def __init__(self, response_input):
        self.messages = _FakeAnthropicMessages(response_input)


def _svc_with_key_settings():
    from app.config import Settings
    return Settings(anthropic_api_key="test-key", tavily_api_key="test-key")


def test_fetch_fda_label_returns_first_result():
    svc = LookupService(settings=_svc_with_key_settings())
    svc._http_client = _FakeHTTPClient(
        fda_response=_FakeHTTPResponse({"results": [{"dosage_forms_and_strengths": "2 mg / 3 mL"}]})
    )
    label = svc._fetch_fda_label("Ozempic")
    assert label == {"dosage_forms_and_strengths": "2 mg / 3 mL"}


def test_fetch_fda_label_returns_none_on_no_results():
    svc = LookupService(settings=_svc_with_key_settings())
    svc._http_client = _FakeHTTPClient(fda_response=_FakeHTTPResponse({"results": []}))
    assert svc._fetch_fda_label("Unknown Brand") is None


def test_fetch_fda_label_returns_none_on_http_error():
    svc = LookupService(settings=_svc_with_key_settings())
    svc._http_client = _FakeHTTPClient(fda_response=_FakeHTTPResponse({}, status_code=404))
    assert svc._fetch_fda_label("Unknown Brand") is None


def test_search_tavily_returns_results_list():
    svc = LookupService(settings=_svc_with_key_settings())
    svc._http_client = _FakeHTTPClient(
        tavily_response=_FakeHTTPResponse({"results": [{"title": "t", "url": "u", "content": "c"}]})
    )
    results = svc._search_tavily("some query")
    assert results == [{"title": "t", "url": "u", "content": "c"}]


def test_search_tavily_returns_empty_on_http_error():
    svc = LookupService(settings=_svc_with_key_settings())
    svc._http_client = _FakeHTTPClient(tavily_response=_FakeHTTPResponse({}, status_code=500))
    assert svc._search_tavily("some query") == []


def test_extract_strengths_with_claude_maps_fill_to_cartridge_deterministically():
    svc = LookupService(settings=_svc_with_key_settings())
    svc._anthropic_client = _FakeAnthropicClient({
        "molecule": "Semaglutide",
        "device": "Pen Injector",
        "strengths": [{"strength": "0.5 mg", "fill_ml": 1.5}, {"strength": "2 mg", "fill_ml": 3.0}],
        "citation": "FDA label 209637",
    })
    result = svc._extract_strengths_with_claude("Ozempic", {"dosage_forms_and_strengths": "..."}, [])
    assert result.found is True
    assert result.molecule == "Semaglutide"
    assert result.strengths == [
        {"strength": "0.5 mg", "cartridge": "1.5 mL", "fill_ml": 1.5},
        {"strength": "2 mg", "cartridge": "3 mL", "fill_ml": 3.0},
    ]
    assert result.citation == "FDA label 209637"


def test_synthesize_viscosity_with_claude_requires_clean_number():
    svc = LookupService(settings=_svc_with_key_settings())
    svc._anthropic_client = _FakeAnthropicClient({"visc_val": 1.4, "citation": "DailyMed SmPC"})
    result = svc._synthesize_viscosity_with_claude("Ozempic", "Semaglutide", [{"title": "t", "content": "c"}])
    assert result == ViscosityLookupResult(found=True, visc_val=1.4, citation="DailyMed SmPC")


def test_synthesize_viscosity_with_claude_null_value_is_not_found():
    svc = LookupService(settings=_svc_with_key_settings())
    svc._anthropic_client = _FakeAnthropicClient({"visc_val": None, "citation": "qualitative only"})
    result = svc._synthesize_viscosity_with_claude("Ozempic", "Semaglutide", [{"title": "t", "content": "c"}])
    assert result.found is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && PYTHONPATH=. DATABASE_URL="sqlite:///:memory:" JWT_SECRET=test CORS_ORIGINS='["http://localhost:3000"]' .venv/bin/pytest tests/test_external_lookup.py -v`
Expected: FAIL — `NotImplementedError` on the four new tests' calls, and `AttributeError` on `svc._http_client`/`svc._anthropic_client` (not yet defined on `__init__`).

- [ ] **Step 3: Write the implementation**

In `backend/app/services/external_lookup.py`, add `import httpx` and `import anthropic` to
the top imports, replace `__init__` to lazily construct real clients, and fill in the four
helper bodies:

```python
import httpx
import anthropic
```

```python
class LookupService:
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
```

(Tests set `svc._http_client`/`svc._anthropic_client` directly to their fakes, bypassing the
lazy real-client construction entirely — so no real client is ever built in CI.)

Replace the four `raise NotImplementedError` stubs:

```python
    def _fetch_fda_label(self, brand: str) -> dict | None:
        resp = self.http_client.get(
            FDA_LABEL_URL,
            params={"search": f'openfda.brand_name:"{brand}" AND openfda.route:"SUBCUTANEOUS"', "limit": 1},
            timeout=HTTP_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
        return results[0] if results else None

    def _search_tavily(self, query: str) -> list[dict]:
        resp = self.http_client.post(
            TAVILY_SEARCH_URL,
            json={"api_key": self.settings.tavily_api_key, "query": query, "max_results": 10},
            timeout=HTTP_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && PYTHONPATH=. DATABASE_URL="sqlite:///:memory:" JWT_SECRET=test CORS_ORIGINS='["http://localhost:3000"]' .venv/bin/pytest tests/test_external_lookup.py -v`
Expected: PASS (13 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/external_lookup.py backend/tests/test_external_lookup.py
git commit -m "feat: real openFDA/Tavily/Claude calls behind LookupService"
```

---

### Task 5: Schemas for the lookup endpoints

**Files:**
- Modify: `backend/app/schemas.py`

**Interfaces:**
- Produces: `ReferenceStrengthLookupIn`, `LookedUpStrength`, `ReferenceStrengthLookupOut`, `ReferenceViscosityLookupIn`, `ReferenceViscosityLookupOut` — all importable from `app.schemas`.

- [ ] **Step 1: Add the schemas**

In `backend/app/schemas.py`, add at the end of the file:

```python
class ReferenceStrengthLookupIn(BaseModel):
    brand: str
    market: str


class LookedUpStrength(BaseModel):
    strength: str
    cartridge: str
    fill_ml: float


class ReferenceStrengthLookupOut(BaseModel):
    found: bool
    brand: str
    molecule: Optional[str] = None
    device: Optional[str] = None
    strengths: list[LookedUpStrength] = []
    citation: Optional[str] = None


class ReferenceViscosityLookupIn(BaseModel):
    brand: str
    molecule: Optional[str] = None


class ReferenceViscosityLookupOut(BaseModel):
    found: bool
    brand: str
    visc_val: Optional[float] = None
    citation: Optional[str] = None
```

- [ ] **Step 2: Verify the module still imports cleanly**

Run: `cd backend && PYTHONPATH=. .venv/bin/python -c "from app.schemas import ReferenceStrengthLookupOut, ReferenceViscosityLookupOut; print('ok')"`
Expected: prints `ok`

- [ ] **Step 3: Commit**

```bash
git add backend/app/schemas.py
git commit -m "feat: schemas for reference-lookup endpoints"
```

---

### Task 6: `POST /reference-lookup/strengths` and `POST /reference-lookup/viscosity`

**Files:**
- Create: `backend/app/routers/reference_lookup.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_reference_lookup.py`

**Interfaces:**
- Consumes: `LookupService`, `StrengthLookupResult`, `ViscosityLookupResult`, `get_lookup_service`, `cartridge_for_fill` from `app.services.external_lookup` (Tasks 2–4); `ReferenceStrengthLookupIn/Out`, `ReferenceViscosityLookupIn/Out`, `LookedUpStrength` from `app.schemas` (Task 5); `ReferenceProduct`, `ReferenceProductMarket` from `app.models`; `get_db` from `app.db`; `get_current_user` from `app.deps`.
- Produces: `router` (FastAPI `APIRouter`), registered in `main.py`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_reference_lookup.py`:

```python
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app.main import app
from app.db import Base, get_db
from app.services.external_lookup import (
    LookupService,
    StrengthLookupResult,
    ViscosityLookupResult,
    get_lookup_service,
)


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


class FakeLookupService(LookupService):
    def __init__(self, strengths_result=None, viscosity_result=None):
        self._strengths_result = strengths_result or StrengthLookupResult(found=False)
        self._viscosity_result = viscosity_result or ViscosityLookupResult(found=False)

    def lookup_strengths(self, brand, market):
        return self._strengths_result

    def lookup_viscosity(self, brand, molecule):
        return self._viscosity_result


def _login(client, email="anaya@pfizer.com"):
    resp = client.post("/auth/login", json={
        "name": "Anaya", "email": email, "title": "R&D Manager", "phone": "+1-555-0100",
    })
    return resp.json()["access_token"]


def test_strengths_lookup_requires_auth(client):
    resp = client.post("/reference-lookup/strengths", json={"brand": "Ozempic", "market": "US"})
    assert resp.status_code == 401


def test_strengths_lookup_miss_returns_found_false(client):
    token = _login(client)
    app.dependency_overrides[get_lookup_service] = lambda: FakeLookupService()
    resp = client.post(
        "/reference-lookup/strengths", json={"brand": "TotallyNewBrand", "market": "US"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["found"] is False


def test_strengths_lookup_hit_creates_new_reference_product_and_market_row(client):
    token = _login(client)
    fake = FakeLookupService(strengths_result=StrengthLookupResult(
        found=True, molecule="Semaglutide", device="Pen Injector",
        strengths=[{"strength": "0.5 mg", "cartridge": "1.5 mL", "fill_ml": 1.5}],
        citation="FDA label 209637",
    ))
    app.dependency_overrides[get_lookup_service] = lambda: fake

    resp = client.post(
        "/reference-lookup/strengths", json={"brand": "BrandNewDrug", "market": "EU"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["found"] is True
    assert body["molecule"] == "Semaglutide"
    assert body["strengths"] == [{"strength": "0.5 mg", "cartridge": "1.5 mL", "fill_ml": 1.5}]

    # second call for the same brand+market is a cache hit — no external call needed
    app.dependency_overrides[get_lookup_service] = lambda: FakeLookupService()  # would return found=False
    resp2 = client.post(
        "/reference-lookup/strengths", json={"brand": "BrandNewDrug", "market": "EU"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp2.json()["found"] is True
    assert resp2.json()["molecule"] == "Semaglutide"


def test_strengths_lookup_hit_does_not_overwrite_existing_base_row(client, seed_reference_product=None):
    token = _login(client)
    # Seed a base row the way migration 0003 would, via the existing reference-products flow:
    from app.db import get_db
    from app.models import ReferenceProduct
    db = next(app.dependency_overrides[get_db]())
    db.add(ReferenceProduct(
        brand="Ozempic", molecule="Semaglutide", device="Pen Injector", dose="variable", visc="water",
        visc_val=1.4, cartridge="3 mL", strengths=["0.25 mg"], visc_ref="ref",
        mech_drive="torsion_spring", mech_dose="variable", mech_label="label", ob_ref="ob", ob_claims=["c"],
        presentations={"0.25 mg": ["1.5 mL", 1.5]}, presentations_ref="pref",
    ))
    db.commit()
    db.close()

    fake = FakeLookupService(strengths_result=StrengthLookupResult(
        found=True, molecule="Wrong Molecule Name", device="Wrong Device",
        strengths=[{"strength": "1 mg", "cartridge": "3 mL", "fill_ml": 3.0}],
        citation="South Korea label",
    ))
    app.dependency_overrides[get_lookup_service] = lambda: fake

    resp = client.post(
        "/reference-lookup/strengths", json={"brand": "Ozempic", "market": "South Korea"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200

    db = next(app.dependency_overrides[get_db]())
    base = db.get(ReferenceProduct, "Ozempic")
    assert base.molecule == "Semaglutide"  # untouched by the market-specific lookup
    db.close()


def test_viscosity_lookup_miss_returns_found_false(client):
    token = _login(client)
    app.dependency_overrides[get_lookup_service] = lambda: FakeLookupService()
    resp = client.post(
        "/reference-lookup/viscosity", json={"brand": "TotallyNewBrand"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["found"] is False


def test_viscosity_lookup_hit_persists_visc_val(client):
    token = _login(client)
    fake = FakeLookupService(viscosity_result=ViscosityLookupResult(
        found=True, visc_val=2.3, citation="DailyMed SmPC",
    ))
    app.dependency_overrides[get_lookup_service] = lambda: fake

    resp = client.post(
        "/reference-lookup/viscosity", json={"brand": "AnotherNewDrug", "molecule": "Somemab"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["found"] is True
    assert resp.json()["visc_val"] == 2.3

    from app.models import ReferenceProduct
    db = next(app.dependency_overrides[get_db]())
    base = db.get(ReferenceProduct, "AnotherNewDrug")
    assert float(base.visc_val) == 2.3
    db.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && PYTHONPATH=. DATABASE_URL="sqlite:///:memory:" JWT_SECRET=test CORS_ORIGINS='["http://localhost:3000"]' .venv/bin/pytest tests/test_reference_lookup.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.routers.reference_lookup'` (and 404s once the module exists but before `main.py` registers it).

- [ ] **Step 3: Write the implementation**

Create `backend/app/routers/reference_lookup.py`:

```python
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import ReferenceProduct, ReferenceProductMarket, User
from app.schemas import (LookedUpStrength, ReferenceStrengthLookupIn, ReferenceStrengthLookupOut,
                          ReferenceViscosityLookupIn, ReferenceViscosityLookupOut)
from app.services.external_lookup import LookupService, get_lookup_service

router = APIRouter(prefix="/reference-lookup", tags=["reference-lookup"])


def _upsert_market_presentations(db: Session, brand: str, market: str, strengths: list[dict]) -> None:
    presentations = {s["strength"]: [s["cartridge"], s["fill_ml"]] for s in strengths}
    row = db.get(ReferenceProductMarket, (brand, market))
    if row is not None:
        row.presentations = presentations
        db.commit()
        return
    try:
        db.add(ReferenceProductMarket(brand=brand, market=market, presentations=presentations))
        db.commit()
    except IntegrityError:
        db.rollback()
        row = db.get(ReferenceProductMarket, (brand, market))
        row.presentations = presentations
        db.commit()


def _create_base_row_if_missing(db: Session, brand: str, molecule: str | None, device: str | None,
                                 strengths: list[dict], citation: str | None) -> None:
    if db.get(ReferenceProduct, brand) is not None:
        return
    presentations = {s["strength"]: [s["cartridge"], s["fill_ml"]] for s in strengths}
    row = ReferenceProduct(
        brand=brand, molecule=molecule or "", device=device or "", dose="", visc="", visc_val=0,
        cartridge=strengths[0]["cartridge"] if strengths else "3 mL",
        strengths=[s["strength"] for s in strengths], visc_ref="",
        mech_drive="", mech_dose="", mech_label="", ob_ref="", ob_claims=[],
        presentations=presentations, presentations_ref=citation or "",
    )
    try:
        db.add(row)
        db.commit()
    except IntegrityError:
        db.rollback()  # created concurrently by another request — nothing more to do


@router.post("/strengths", response_model=ReferenceStrengthLookupOut)
def lookup_strengths(payload: ReferenceStrengthLookupIn, db: Session = Depends(get_db),
                      current_user: User = Depends(get_current_user),
                      svc: LookupService = Depends(get_lookup_service)):
    cached = db.get(ReferenceProductMarket, (payload.brand, payload.market))
    if cached is not None and cached.presentations:
        base = db.get(ReferenceProduct, payload.brand)
        strengths = [
            LookedUpStrength(strength=s, cartridge=v[0], fill_ml=v[1])
            for s, v in cached.presentations.items()
        ]
        return ReferenceStrengthLookupOut(
            found=True, brand=payload.brand,
            molecule=base.molecule if base else None, device=base.device if base else None,
            strengths=strengths, citation=cached.pres_ref,
        )

    result = svc.lookup_strengths(payload.brand, payload.market)
    if not result.found:
        return ReferenceStrengthLookupOut(found=False, brand=payload.brand)

    _create_base_row_if_missing(db, payload.brand, result.molecule, result.device,
                                 result.strengths, result.citation)
    _upsert_market_presentations(db, payload.brand, payload.market, result.strengths)

    return ReferenceStrengthLookupOut(
        found=True, brand=payload.brand, molecule=result.molecule, device=result.device,
        strengths=[LookedUpStrength(**s) for s in result.strengths], citation=result.citation,
    )


@router.post("/viscosity", response_model=ReferenceViscosityLookupOut)
def lookup_viscosity(payload: ReferenceViscosityLookupIn, db: Session = Depends(get_db),
                      current_user: User = Depends(get_current_user),
                      svc: LookupService = Depends(get_lookup_service)):
    base = db.get(ReferenceProduct, payload.brand)
    if base is not None and base.visc_val:
        return ReferenceViscosityLookupOut(
            found=True, brand=payload.brand, visc_val=float(base.visc_val), citation=base.visc_ref,
        )

    result = svc.lookup_viscosity(payload.brand, payload.molecule)
    if not result.found:
        return ReferenceViscosityLookupOut(found=False, brand=payload.brand)

    if base is not None:
        base.visc_val = result.visc_val
        base.visc_ref = result.citation or ""
        db.commit()

    return ReferenceViscosityLookupOut(
        found=True, brand=payload.brand, visc_val=result.visc_val, citation=result.citation,
    )
```

Register it in `backend/app/main.py` — add after the `reference_products_router` block:

```python
from app.routers.reference_lookup import router as reference_lookup_router
app.include_router(reference_lookup_router)
```

Note: `test_viscosity_lookup_hit_persists_visc_val` looks up a brand new to the DB
(`"AnotherNewDrug"`), so `base is None` there and the "persist to an existing base row" branch
isn't hit by that test as written — this matches the spec's decision that a viscosity lookup
only updates an *existing* base row (viscosity lookups don't create a brand-new
`ReferenceProduct` row on their own; only a strengths lookup does that). Adjust the test's
final assertion to instead re-fetch via the `/reference-lookup/viscosity` cache path if the
brand has no base row — see Step 4.

- [ ] **Step 4: Fix the test for the no-existing-base-row case**

Since `lookup_viscosity`'s upsert only fires `if base is not None`, replace the last part of
`test_viscosity_lookup_hit_persists_visc_val` in `backend/tests/test_reference_lookup.py` to
seed a base row first, matching how `test_strengths_lookup_hit_does_not_overwrite_existing_base_row`
does it:

```python
def test_viscosity_lookup_hit_persists_visc_val(client):
    token = _login(client)
    from app.models import ReferenceProduct
    db = next(app.dependency_overrides[get_db]())
    db.add(ReferenceProduct(
        brand="AnotherNewDrug", molecule="Somemab", device="Pen Injector", dose="variable", visc="water",
        visc_val=0, cartridge="3 mL", strengths=[], visc_ref="",
        mech_drive="", mech_dose="", mech_label="", ob_ref="", ob_claims=[],
        presentations={}, presentations_ref="",
    ))
    db.commit()
    db.close()

    fake = FakeLookupService(viscosity_result=ViscosityLookupResult(
        found=True, visc_val=2.3, citation="DailyMed SmPC",
    ))
    app.dependency_overrides[get_lookup_service] = lambda: fake

    resp = client.post(
        "/reference-lookup/viscosity", json={"brand": "AnotherNewDrug", "molecule": "Somemab"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["found"] is True
    assert resp.json()["visc_val"] == 2.3

    db = next(app.dependency_overrides[get_db]())
    base = db.get(ReferenceProduct, "AnotherNewDrug")
    assert float(base.visc_val) == 2.3
    db.close()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && PYTHONPATH=. DATABASE_URL="sqlite:///:memory:" JWT_SECRET=test CORS_ORIGINS='["http://localhost:3000"]' .venv/bin/pytest tests/test_reference_lookup.py -v`
Expected: PASS (7 tests)

- [ ] **Step 6: Run the full backend suite to confirm nothing else broke**

Run: `cd backend && PYTHONPATH=. DATABASE_URL="sqlite:///:memory:" JWT_SECRET=test CORS_ORIGINS='["http://localhost:3000"]' .venv/bin/pytest -v`
Expected: all tests PASS (previous 99 + new ones from this plan).

- [ ] **Step 7: Commit**

```bash
git add backend/app/routers/reference_lookup.py backend/app/main.py backend/tests/test_reference_lookup.py
git commit -m "feat: POST /reference-lookup/strengths and /viscosity endpoints"
```

---

### Task 7: Frontend API client functions

**Files:**
- Modify: `frontend/lib/api.ts`

**Interfaces:**
- Produces: `lookupStrengths(token, brand, market) -> Promise<StrengthLookup>`, `lookupViscosity(token, brand, molecule?) -> Promise<ViscosityLookup>`, plus their exported types `StrengthLookup`/`ViscosityLookup`, `LookedUpStrength`.

- [ ] **Step 1: Add the types and functions**

In `frontend/lib/api.ts`, add near the other reference-data types/functions (after
`listReferenceProducts`):

```typescript
export type LookedUpStrength = { strength: string; cartridge: string; fill_ml: number };
export type StrengthLookup = {
  found: boolean;
  brand: string;
  molecule: string | null;
  device: string | null;
  strengths: LookedUpStrength[];
  citation: string | null;
};
export type ViscosityLookup = {
  found: boolean;
  brand: string;
  visc_val: number | null;
  citation: string | null;
};

export async function lookupStrengths(token: string, brand: string, market: string): Promise<StrengthLookup> {
  const resp = await fetch(`/api/reference-lookup/strengths`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify({ brand, market }),
  });
  if (!resp.ok) throw await parseError(resp, "We couldn't look that up — try again.");
  return resp.json();
}

export async function lookupViscosity(token: string, brand: string, molecule?: string): Promise<ViscosityLookup> {
  const resp = await fetch(`/api/reference-lookup/viscosity`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify({ brand, molecule }),
  });
  if (!resp.ok) throw await parseError(resp, "We couldn't look that up — try again.");
  return resp.json();
}
```

Note: `authHeaders` is defined further down in this file (after `listRequests`) but is a
plain function declaration, so it's hoisted and callable from here — matches the existing
`listReferenceProducts`/`getRequestDetail` functions above it that already call `authHeaders`.

- [ ] **Step 2: Verify the frontend still typechecks**

Run: `cd frontend && npm run build`
Expected: build succeeds (these are unused exports at this point — Task 8 wires them in — so
no typecheck error from being unused; TypeScript doesn't flag unused exports, only unused
locals).

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/api.ts
git commit -m "feat(frontend): lookupStrengths/lookupViscosity API client functions"
```

---

### Task 8: Wizard integration — live strength lookup and viscosity literature search

**Files:**
- Modify: `frontend/app/requests/[id]/page.tsx`

**Interfaces:**
- Consumes: `lookupStrengths`, `lookupViscosity`, `LookedUpStrength` from `frontend/lib/api.ts` (Task 7).

- [ ] **Step 1: Add lookup state and handlers**

In `frontend/app/requests/[id]/page.tsx`, near the other `useState` declarations for the
step-1 form (after the `viscosityVal`/`differentiated`/`device` state), add:

```typescript
  const [strengthLookupLoading, setStrengthLookupLoading] = useState(false);
  const [strengthLookupNotFound, setStrengthLookupNotFound] = useState(false);
  const [viscosityLookup, setViscosityLookup] = useState<{ visc_val: number; citation: string | null } | null>(null);
  const [viscosityLookupLoading, setViscosityLookupLoading] = useState(false);
  const [viscosityLookupNotFound, setViscosityLookupNotFound] = useState(false);
```

Add the handler functions near `reconcileRowsForStrengths` (same component, before the
`return`):

```typescript
  async function handleLiveStrengthLookup() {
    if (!token || !brand || !market) return;
    setStrengthLookupLoading(true);
    setStrengthLookupNotFound(false);
    try {
      const result = await lookupStrengths(token, brand, market);
      if (result.found) {
        setRefProducts((prev) => {
          const existing = prev.find((p) => p.brand === result.brand);
          const merged: ReferenceProduct = {
            brand: result.brand,
            molecule: result.molecule ?? existing?.molecule ?? "",
            device: result.device ?? existing?.device ?? "",
            strengths: result.strengths.map((s) => s.strength),
            visc_val: existing?.visc_val ?? 0,
            visc_ref: existing?.visc_ref ?? "",
            cartridge: result.strengths[0]?.cartridge ?? existing?.cartridge ?? "3 mL",
          };
          return existing ? prev.map((p) => (p.brand === result.brand ? merged : p)) : [...prev, merged];
        });
      } else {
        setStrengthLookupNotFound(true);
      }
    } catch {
      setStrengthLookupNotFound(true);
    } finally {
      setStrengthLookupLoading(false);
    }
  }

  async function handleLiveViscosityLookup() {
    if (!token || !brand) return;
    setViscosityLookupLoading(true);
    setViscosityLookupNotFound(false);
    setViscosityLookup(null);
    try {
      const result = await lookupViscosity(token, brand, currentRef?.molecule);
      if (result.found && result.visc_val != null) {
        setViscosityLookup({ visc_val: result.visc_val, citation: result.citation });
      } else {
        setViscosityLookupNotFound(true);
      }
    } catch {
      setViscosityLookupNotFound(true);
    } finally {
      setViscosityLookupLoading(false);
    }
  }
```

- [ ] **Step 2: Add the import**

At the top of the file, extend the existing `@/lib/api` import to include the new functions
and type:

```typescript
  lookupStrengths,
  lookupViscosity,
```

(added alphabetically among the existing named imports from `@/lib/api`, e.g. next to
`listReferenceProducts`).

- [ ] **Step 3: Wire the "Look up live" button next to the brand/market fields**

In the JSX for the "Reference product" section (the `<div className="flex flex-col gap-4 sm:flex-row">`
wrapping the brand `SelectField` and market `SelectField`), add a button after that flex
container, before the `{currentRef && (...)}` recognized-product paragraph:

```jsx
                  {isDraft && brand && market && !currentRef && (
                    <div className="mt-2">
                      <Button
                        type="button"
                        variant="secondary"
                        loading={strengthLookupLoading}
                        onClick={handleLiveStrengthLookup}
                      >
                        {strengthLookupLoading ? "Looking up…" : "🔍 Look up live"}
                      </Button>
                      {strengthLookupNotFound && (
                        <p className="mt-2 font-body text-xs text-ink-700/70">
                          No data found for this brand/market — enter details manually.
                        </p>
                      )}
                    </div>
                  )}
```

- [ ] **Step 4: Replace the viscosity "Need assistance" button behavior**

Replace the existing viscosity `Button` block:

```jsx
                    {isDraft && currentRef && (
                      <Button
                        type="button"
                        variant="secondary"
                        onClick={() => setViscosityVal(currentRef.visc_val)}
                      >
                        ＋ Need assistance
                      </Button>
                    )}
```

with:

```jsx
                    {isDraft && brand && (
                      <Button
                        type="button"
                        variant="secondary"
                        loading={viscosityLookupLoading}
                        onClick={handleLiveViscosityLookup}
                      >
                        {viscosityLookupLoading ? "Searching…" : "＋ Need assistance"}
                      </Button>
                    )}
```

Immediately after that `<div className="flex items-end gap-3">...</div>` block (which
contains the viscosity `TextField` + this button), add the result/no-result display,
replacing the existing static `{currentRef?.visc_ref && (...)}` paragraph:

```jsx
                  {viscosityLookup && (
                    <p className="mt-2 font-body text-xs text-ink-700/70">
                      Literature suggests <b>{viscosityLookup.visc_val} cP</b>.{" "}
                      <button
                        type="button"
                        className="font-medium text-forest-600 underline-offset-2 hover:underline"
                        onClick={() => setViscosityVal(viscosityLookup.visc_val)}
                      >
                        Use this value
                      </button>
                      {viscosityLookup.citation && (
                        <>
                          {" "}
                          — <i>*{viscosityLookup.citation}</i>
                        </>
                      )}
                    </p>
                  )}
                  {viscosityLookupNotFound && (
                    <p className="mt-2 font-body text-xs text-ink-700/70">
                      No literature value found — enter manually.
                    </p>
                  )}
                  {!viscosityLookup && currentRef?.visc_ref && (
                    <p className="mt-2 font-body text-xs text-ink-700/70">📄 Literature reference: {currentRef.visc_ref}</p>
                  )}
```

This preserves the original seeded-data citation display as a fallback when no live lookup
has run yet, and shows the new italic-with-asterisk citation format (matching the docx's
formatting ask) once a live lookup succeeds. The "Use this value" link keeps the customer in
control of actually setting the field, rather than the lookup silently overwriting it.

- [ ] **Step 5: Verify the frontend build passes**

Run: `cd frontend && npm run build`
Expected: build succeeds (typecheck passes, no unused-variable errors).

- [ ] **Step 6: Manual verification against a live backend**

With no `ANTHROPIC_API_KEY`/`TAVILY_API_KEY` set (matching most dev environments), start the
backend and frontend locally (see Round A/B's verification approach earlier in this project:
`alembic upgrade head` against a throwaway sqlite file, `uvicorn` on a free port, `npm run dev`
pointed at it via `API_URL`), log in as a customer, start a request, and confirm:
- Selecting a brand not in the local list still shows the "🔍 Look up live" button.
- Clicking it with no keys configured shows "No data found... enter manually" (the graceful
  `found: false` path) rather than an error banner.
- Clicking "+ Need assistance" similarly shows "No literature value found" rather than
  silently filling in the old static number.
- For an already-seeded brand (e.g. Ozempic), the existing static "📄 Literature reference"
  line still renders exactly as it did before this change (since `viscosityLookup` is `null`
  until a live lookup is triggered).

- [ ] **Step 7: Commit**

```bash
git add frontend/app/requests/\[id\]/page.tsx
git commit -m "feat(frontend): live strength/viscosity lookup buttons in the wizard"
```

---

## Self-Review Notes

- **Spec coverage:** openFDA fetch (Task 4), Tavily search (Task 4), Claude extraction/synthesis
  (Task 4), deterministic cartridge mapping (Task 2), cache-first (Task 6's `db.get(...)` checks
  before calling `svc`), persistence into existing tables (Task 6's upsert helpers), on-demand
  trigger (Task 8's buttons, no auto-fire), graceful `found:false` everywhere (Task 3's
  short-circuit + Task 4's `except Exception` wrapper + Task 6 never raising on a miss),
  settings/env plumbing (Task 1) — all covered.
- **Type consistency:** `StrengthLookupResult.strengths` is `list[dict]` with keys
  `strength`/`cartridge`/`fill_ml` throughout (Tasks 3, 4, 6); `ReferenceStrengthLookupOut.strengths`
  is `list[LookedUpStrength]` (Pydantic) constructed from those same dicts in Task 6 — consistent.
  Frontend `LookedUpStrength`/`StrengthLookup`/`ViscosityLookup` (Task 7) match the Pydantic
  response shapes from Task 5/6 field-for-field.
- **No placeholders:** every step has literal code, not descriptions of code.
