from app.config import Settings
from app.services.external_lookup import (
    LookupService,
    cartridge_for_fill,
    get_lookup_service,
)


def test_cartridge_for_fill_at_or_below_1_5ml():
    assert cartridge_for_fill(1.5) == "1.5 mL"
    assert cartridge_for_fill(1.0) == "1.5 mL"
    assert cartridge_for_fill(0.5) == "1.5 mL"


def test_cartridge_for_fill_above_1_5ml():
    assert cartridge_for_fill(1.51) == "3 mL"
    assert cartridge_for_fill(3.0) == "3 mL"


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


import httpx

from app.services.external_lookup import LookupService, ViscosityLookupResult


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
