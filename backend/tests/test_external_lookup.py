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
