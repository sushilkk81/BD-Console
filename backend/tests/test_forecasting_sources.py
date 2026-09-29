"""Source-adapter tests.

Every test here is offline: the CMS API is exercised through httpx.MockTransport, and
the file-ingestion tests read a genuine excerpt of the official CMS download
(tests/fixtures/cms_part_d_dy2024_excerpt.csv — real rows, real column names, real
values, taken verbatim from DSD_PTD_RY26_P04_V10_DY24_BGM.csv).
"""
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from app.forecasting_engine.core.units import (ApiConnectivity, FileVerificationStatus,
                                                ProvenanceClass, PublicationFreshness,
                                                SourceKind, SourceMetric)
from app.forecasting_engine.services.sources import tabular_import
from app.forecasting_engine.services.sources.base import SourceStatus
from app.forecasting_engine.services.sources.cms_part_d import (ALLOWED_HOSTS, ColumnResolutionError,
                                                                 CmsPartDAdapter,
                                                                 CmsPartDFileIngestor,
                                                                 DescriptorError, classify_file,
                                                                 classify_freshness,
                                                                 load_descriptor, probe_api,
                                                                 resolve_columns, validate_descriptor)

FIXTURE = Path(__file__).parent / "fixtures" / "cms_part_d_dy2024_excerpt.csv"

# Values as published by CMS for data year 2024 (Ozempic, manufacturer roll-up row).
OZEMPIC_DOSAGE_UNITS_2024 = Decimal("42324232.836")
OZEMPIC_CLAIMS_2024 = Decimal("10417182")
OZEMPIC_BENES_2024 = Decimal("1952637")
OZEMPIC_SPENDING_2024 = Decimal("12970296347")


@pytest.fixture
def cms_csv() -> str:
    return FIXTURE.read_text(encoding="utf-8-sig")


@pytest.fixture
def dataset() -> dict:
    return validate_descriptor(load_descriptor())


def _adapter(handler, descriptor=None):
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return CmsPartDAdapter(client=client, descriptor=descriptor or load_descriptor())


# --- the shipped descriptor is verified against official sources --------------

def test_the_shipped_descriptor_is_verified_and_carries_its_evidence():
    descriptor = load_descriptor()
    assert descriptor["verified"] is True
    assert descriptor["verification_evidence"], "a verified descriptor must cite its sources"
    dataset = validate_descriptor(descriptor)
    # Identity as published by CMS/HHS.
    assert dataset["api_dataset_uuid"] == "7e0b4365-fd63-4a29-8f5e-e0ac9f66a81b"
    assert dataset["csv_filename"] == "DSD_PTD_RY26_P04_V10_DY24_BGM.csv"
    assert dataset["latest_data_year"] == 2024
    assert dataset["available_data_years"] == [2020, 2021, 2022, 2023, 2024]
    assert dataset["geography"] == "US"
    assert "rebate" in dataset["spending_basis"].lower()


def test_only_the_allowlisted_cms_host_is_reachable():
    assert ALLOWED_HOSTS == frozenset({"data.cms.gov"})


def test_a_descriptor_pointing_off_host_is_rejected(dataset):
    tampered = {"verified": True, "dataset": dict(dataset, api_url="https://example.com/data")}
    with pytest.raises(DescriptorError, match="non-allowlisted host"):
        validate_descriptor(tampered)


def test_an_unverified_descriptor_is_rejected():
    with pytest.raises(DescriptorError, match="not verified"):
        validate_descriptor({"verified": False, "dataset": {}})


# --- column resolution comes from the data, not from guesses -----------------

def test_columns_resolve_from_the_real_cms_header(cms_csv, dataset):
    header = cms_csv.splitlines()[0].split(",")
    resolved = resolve_columns(header, dataset, 2024)
    assert resolved[SourceMetric.DOSAGE_UNITS] == "Tot_Dsg_Unts_2024"
    assert resolved[SourceMetric.CLAIMS] == "Tot_Clms_2024"
    assert resolved[SourceMetric.BENEFICIARIES] == "Tot_Benes_2024"
    assert resolved[SourceMetric.SPENDING] == "Tot_Spndng_2024"


def test_earlier_data_years_in_the_same_file_resolve_too(cms_csv, dataset):
    header = cms_csv.splitlines()[0].split(",")
    assert resolve_columns(header, dataset, 2020)[SourceMetric.DOSAGE_UNITS] == "Tot_Dsg_Unts_2020"


def test_a_renamed_cms_column_fails_loudly_instead_of_guessing(dataset):
    with pytest.raises(ColumnResolutionError, match="not in the data"):
        resolve_columns(["Something_Else", "Tot_Dsg_Unts_2024"], dataset, 2024)


def test_a_year_absent_from_the_data_is_refused(cms_csv, dataset):
    header = cms_csv.splitlines()[0].split(",")
    with pytest.raises(ColumnResolutionError, match="no metric columns"):
        resolve_columns(header, dataset, 1999)


# --- ingesting the official CMS download -------------------------------------

def test_official_csv_yields_the_published_values_for_a_real_molecule(cms_csv):
    result = CmsPartDFileIngestor().ingest(cms_csv, brand="Ozempic", data_year=2024)
    assert result.status is SourceStatus.AVAILABLE
    by_metric = {o.metric: o for o in result.observations}
    assert by_metric[SourceMetric.DOSAGE_UNITS].value == OZEMPIC_DOSAGE_UNITS_2024
    assert by_metric[SourceMetric.CLAIMS].value == OZEMPIC_CLAIMS_2024
    assert by_metric[SourceMetric.BENEFICIARIES].value == OZEMPIC_BENES_2024
    assert by_metric[SourceMetric.SPENDING].value == OZEMPIC_SPENDING_2024


def test_ingested_rows_carry_full_provenance(cms_csv, dataset):
    result = CmsPartDFileIngestor().ingest(cms_csv, brand="Ozempic", data_year=2024)
    obs = next(o for o in result.observations if o.metric is SourceMetric.DOSAGE_UNITS)
    assert obs.source_url == dataset["csv_url"]
    assert obs.source_identifier == dataset["csv_dataset_uuid"]
    assert obs.period_label == "2024"
    assert (obs.period_start.isoformat(), obs.period_end.isoformat()) == ("2024-01-01", "2024-12-31")
    assert "Tot_Dsg_Unts_2024" in obs.transformation
    assert obs.molecule == "Semaglutide" and obs.brand == "Ozempic"
    assert obs.unit == "dosage_units"
    assert obs.retrieved_at is not None


def test_coverage_is_never_presented_as_the_whole_us_market(cms_csv):
    result = CmsPartDFileIngestor().ingest(cms_csv, brand="Ozempic", data_year=2024)
    coverage = result.observations[0].coverage
    assert "Medicare Part D" in coverage
    assert "Not total US market volume" in coverage


def test_spending_is_labelled_gross_and_not_manufacturer_net_revenue(cms_csv):
    result = CmsPartDFileIngestor().ingest(cms_csv, brand="Ozempic", data_year=2024)
    spending = next(o for o in result.observations if o.metric is SourceMetric.SPENDING)
    assert spending.currency == "USD"
    assert spending.unit == "currency"
    assert "rebate" in spending.coverage.lower()
    assert "not manufacturer net revenue" in spending.coverage.lower()


def test_the_overall_rollup_row_is_used_once_and_manufacturer_rows_are_not_added(cms_csv):
    """CMS repeats each brand's totals under 'Overall' and again per manufacturer.
    Emitting both would double every figure."""
    result = CmsPartDFileIngestor().ingest(cms_csv, brand="Ozempic", data_year=2024)
    dosage = [o for o in result.observations if o.metric is SourceMetric.DOSAGE_UNITS]
    assert len(dosage) == 1
    assert any("double" in w for w in result.warnings)


def test_a_generic_name_matching_several_brands_is_flagged_not_summed(cms_csv):
    result = CmsPartDFileIngestor().ingest(cms_csv, molecule="Semaglutide", data_year=2024)
    brands = {o.brand for o in result.observations}
    assert brands == {"Ozempic", "Rybelsus", "Wegovy"}
    assert all(o.ambiguous_match for o in result.observations)


def test_an_earlier_data_year_can_be_ingested_from_the_same_file(cms_csv):
    result = CmsPartDFileIngestor().ingest(cms_csv, brand="Ozempic", data_year=2021)
    dosage = next(o for o in result.observations if o.metric is SourceMetric.DOSAGE_UNITS)
    assert dosage.period_label == "2021"
    assert dosage.value != OZEMPIC_DOSAGE_UNITS_2024


def test_a_drug_absent_from_the_file_is_no_matching_records(cms_csv):
    result = CmsPartDFileIngestor().ingest(cms_csv, brand="NotADrug", data_year=2024)
    assert result.status is SourceStatus.NO_MATCHING_RECORDS
    assert result.observations == []
    assert "no rows matching" in result.unavailable_reason


def test_gzipped_cms_bytes_are_accepted(cms_csv):
    import gzip
    decoded = CmsPartDFileIngestor.decode(gzip.compress(cms_csv.encode()))
    assert decoded.splitlines()[0].startswith("Brnd_Name,Gnrc_Name")


def test_an_oversized_file_is_refused():
    from app.forecasting_engine.services.sources import cms_part_d
    with pytest.raises(ValueError, match="exceeds"):
        CmsPartDFileIngestor.decode(b"x" * (cms_part_d.MAX_FILE_BYTES + 1))


def test_a_file_without_the_expected_columns_is_configuration_incomplete():
    result = CmsPartDFileIngestor().ingest("a,b,c\n1,2,3\n", brand="Ozempic", data_year=2024)
    assert result.status is SourceStatus.CONFIGURATION_INCOMPLETE


# --- the live API path -------------------------------------------------------

def test_the_api_path_parses_records_the_same_way(cms_csv, dataset):
    import csv, io
    records = list(csv.DictReader(io.StringIO(cms_csv)))

    def handler(request):
        assert request.url.host == "data.cms.gov"
        return httpx.Response(200, json=records)

    result = _adapter(handler).search(molecule=None, brand="Ozempic", geography="US", period="2024")
    assert result.status is SourceStatus.AVAILABLE
    dosage = next(o for o in result.observations if o.metric is SourceMetric.DOSAGE_UNITS)
    assert dosage.value == OZEMPIC_DOSAGE_UNITS_2024
    assert dosage.source_url == dataset["api_url"]


def test_a_blocked_or_failing_api_reports_api_unavailable_and_points_to_the_csv():
    def handler(request):
        return httpx.Response(403)

    result = _adapter(handler).search(molecule="semaglutide", brand=None, geography="US", period=None)
    assert result.status is SourceStatus.API_UNAVAILABLE
    assert result.observations == []
    assert "DSD_PTD_RY26_P04_V10_DY24_BGM.csv" in result.unavailable_reason


def test_rate_limiting_is_retried_then_succeeds(cms_csv):
    import csv, io
    records = list(csv.DictReader(io.StringIO(cms_csv)))
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "0"})
        return httpx.Response(200, json=records)

    result = _adapter(handler).search(molecule=None, brand="Ozempic", geography="US", period="2024")
    assert calls["n"] == 2
    assert result.status is SourceStatus.AVAILABLE


def test_a_non_us_geography_is_out_of_scope():
    def handler(request):  # pragma: no cover - must never be reached
        raise AssertionError("Part D must not be queried for non-US geographies")

    result = _adapter(handler).search(molecule="semaglutide", brand=None, geography="EU", period=None)
    assert result.status is SourceStatus.NO_MATCHING_RECORDS
    assert "outside its scope" in result.unavailable_reason


def test_a_data_year_the_dataset_does_not_carry_is_refused():
    def handler(request):  # pragma: no cover - must never be reached
        raise AssertionError("no request should be issued for an unavailable year")

    result = _adapter(handler).search(molecule="semaglutide", brand=None, geography="US",
                                      period="1999")
    assert result.status is SourceStatus.CONFIGURATION_INCOMPLETE
    assert "1999" in result.unavailable_reason


def test_an_api_answer_with_no_matching_drug_is_distinguished_from_an_outage(cms_csv):
    import csv, io
    records = list(csv.DictReader(io.StringIO(cms_csv)))

    def handler(request):
        return httpx.Response(200, json=records)

    result = _adapter(handler).search(molecule=None, brand="NotADrug", geography="US", period="2024")
    assert result.status is SourceStatus.NO_MATCHING_RECORDS
    assert "no rows matching" in result.unavailable_reason


def test_an_unverified_descriptor_reports_configuration_incomplete():
    def handler(request):  # pragma: no cover - must never be reached
        raise AssertionError("no request may be issued against an unverified descriptor")

    adapter = _adapter(handler, descriptor={"verified": False, "dataset": {}})
    result = adapter.search(molecule="semaglutide", brand=None, geography="US", period=None)
    assert result.status is SourceStatus.CONFIGURATION_INCOMPLETE


# --- user-supplied file import (unchanged path) ------------------------------

def test_import_rejects_unknown_columns():
    observations, errors = tabular_import.parse_csv(
        "geography,coverage,period_label,metric,unit,value,mystery\n"
        "EU,extract,2024,dosage_units,dosage_units,10,x\n")
    assert observations == []
    assert "unknown column" in errors[0]


def test_import_rejects_a_missing_required_field():
    observations, errors = tabular_import.parse_csv(
        "geography,coverage,period_label,metric,unit,value\n"
        ",extract,2024,dosage_units,dosage_units,10\n")
    assert observations == []
    assert "missing required value" in errors[0]


def test_import_rejects_a_negative_value():
    observations, errors = tabular_import.parse_csv(
        "geography,coverage,period_label,metric,unit,value\n"
        "EU,extract,2024,dosage_units,dosage_units,-5\n")
    assert observations == []
    assert "negative" in errors[0]


def test_import_rejects_a_payload_over_the_size_limit():
    oversized = "x" * (tabular_import.MAX_PAYLOAD_BYTES + 1)
    with pytest.raises(tabular_import.ImportError_, match="exceeds"):
        tabular_import.parse_csv(oversized)


def test_import_truncates_at_the_row_ceiling_and_says_so():
    header = "geography,coverage,period_label,metric,unit,value\n"
    body = "EU,extract,2024,dosage_units,dosage_units,1\n" * (tabular_import.MAX_ROWS + 10)
    observations, errors = tabular_import.parse_csv(header + body)
    assert len(observations) == tabular_import.MAX_ROWS
    assert any("truncated" in e for e in errors)


def test_json_rows_take_the_same_validation_path_as_csv():
    observations, errors = tabular_import.parse_rows([
        {"geography": "EU", "coverage": "extract", "period_label": "2024",
         "metric": "dosage_units", "unit": "dosage_units", "value": "10"}])
    assert errors == []
    assert observations[0].source_kind is SourceKind.FILE_IMPORT
    assert observations[0].value == 10


# --- retrieval provenance: archived publication vs live access ---------------

ARCHIVE_URL = ("https://web.archive.org/web/20260923112137id_/https://data.cms.gov/sites/"
               "default/files/2026-06/98218f98-166c-4723-8438-c344a4ef96a6/"
               "DSD_PTD_RY26_P04_V10_DY24_BGM.csv")


def test_an_archived_copy_records_both_urls_and_is_not_called_live_access(cms_csv, dataset):
    import datetime as dt

    captured = dt.datetime(2026, 9, 23, 11, 21, 37, tzinfo=dt.timezone.utc)
    result = CmsPartDFileIngestor().ingest(
        cms_csv, brand="Ozempic", data_year=2024,
        retrieval_url=ARCHIVE_URL, archive_capture_date=captured)
    obs = next(o for o in result.observations if o.metric is SourceMetric.DOSAGE_UNITS)

    # The publisher's canonical URL is preserved...
    assert obs.source_url == dataset["csv_url"]
    assert obs.source_url.startswith("https://data.cms.gov/")
    # ...and the URL actually fetched is recorded separately, with its capture date.
    assert obs.retrieval_url == ARCHIVE_URL
    assert obs.archive_capture_date == captured
    # Labelled for what it is.
    assert obs.provenance_class is ProvenanceClass.ARCHIVED_CMS_PUBLICATION
    assert obs.provenance_class is not ProvenanceClass.LIVE_CMS_API
    assert any("Archived CMS publication" in w for w in result.warnings)


def test_an_upload_without_a_retrieval_url_is_not_labelled_an_archive(cms_csv):
    result = CmsPartDFileIngestor().ingest(cms_csv, brand="Ozempic", data_year=2024)
    obs = result.observations[0]
    assert obs.provenance_class is ProvenanceClass.USER_SUPPLIED_FILE
    assert obs.retrieval_url is None


def test_the_live_api_path_is_labelled_live_access(cms_csv):
    import csv, io
    records = list(csv.DictReader(io.StringIO(cms_csv)))

    def handler(request):
        return httpx.Response(200, json=records)

    result = _adapter(handler).search(molecule=None, brand="Ozempic", geography="US", period="2024")
    assert all(o.provenance_class is ProvenanceClass.LIVE_CMS_API for o in result.observations)


def test_the_checksum_is_computed_from_the_ingested_bytes(cms_csv):
    import hashlib

    result = CmsPartDFileIngestor().ingest(cms_csv, brand="Ozempic", data_year=2024)
    expected = hashlib.sha256(cms_csv.encode("utf-8")).hexdigest()
    assert all(o.content_sha256 == expected for o in result.observations)


# --- the three independent statuses ------------------------------------------

def test_file_verification_recognises_the_copy_that_was_verified(dataset):
    digest = dataset["verified_file"]["content_sha256"]
    assert classify_file(digest, dataset) is FileVerificationStatus.VERIFIED
    assert classify_file(digest.upper(), dataset) is FileVerificationStatus.VERIFIED


def test_file_verification_flags_a_different_copy_without_calling_it_an_error(cms_csv, dataset):
    """The excerpt is a real CMS file but not the full copy that was checked by hand."""
    result = CmsPartDFileIngestor().ingest(cms_csv, brand="Ozempic", data_year=2024)
    assert result.status is SourceStatus.AVAILABLE           # still perfectly usable
    assert result.observations[0].file_verification is FileVerificationStatus.UNRECOGNISED
    assert any("not the copy this integration was verified against" in w for w in result.warnings)


def test_publication_freshness_is_separate_from_file_verification(dataset):
    assert classify_freshness(2024, dataset) is PublicationFreshness.CURRENT
    assert classify_freshness(2021, dataset) is PublicationFreshness.SUPERSEDED
    assert classify_freshness(2024, dict(dataset, latest_data_year=None)) is \
        PublicationFreshness.UNKNOWN


def test_an_older_reporting_year_is_superseded_but_still_verified(cms_csv, dataset):
    """Freshness and file verification are independent: one can be stale while the other passes."""
    result = CmsPartDFileIngestor().ingest(cms_csv, brand="Ozempic", data_year=2021)
    assert result.status is SourceStatus.AVAILABLE
    assert classify_freshness(2021, dataset) is PublicationFreshness.SUPERSEDED


# --- API connectivity, reported on its own -----------------------------------

AKAMAI_403_BODY = (
    "<HTML><HEAD>\n<TITLE>Access Denied</TITLE>\n</HEAD><BODY>\n<H1>Access Denied</H1>\n"
    "You don't have permission to access \"http&#58;&#47;&#47;data&#46;cms&#46;gov&#47;"
    "data&#45;api&#47;v1&#47;dataset&#47;data\" on this server.<P>\n"
    "Reference&#32;&#35;18&#46;65c90b17&#46;1790672781&#46;a9b10530\n</BODY></HTML>"
)


def test_a_403_is_reported_blocked_with_the_akamai_reference_extracted():
    """The edge HTML-escapes its reference number; support needs it verbatim."""
    def handler(request):
        return httpx.Response(403, text=AKAMAI_403_BODY)

    report = probe_api(client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert report.status is ApiConnectivity.BLOCKED
    assert report.http_status == 403
    assert report.akamai_reference == "18.65c90b17.1790672781.a9b10530"
    assert "not an authentication failure" in report.detail


def test_the_support_summary_carries_everything_cms_would_ask_for():
    def handler(request):
        return httpx.Response(403, text=AKAMAI_403_BODY)

    summary = probe_api(client=httpx.Client(transport=httpx.MockTransport(handler))).support_summary()
    assert "data.cms.gov/data-api" in summary
    assert "403" in summary
    assert "18.65c90b17.1790672781.a9b10530" in summary
    assert "UTC timestamp" in summary


def test_a_reachable_api_is_reported_reachable():
    def handler(request):
        return httpx.Response(200, json=[])

    report = probe_api(client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert report.status is ApiConnectivity.REACHABLE
    assert report.akamai_reference is None


def test_a_transport_failure_is_an_error_not_a_block():
    def handler(request):
        raise httpx.ConnectError("no route to host")

    report = probe_api(client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert report.status is ApiConnectivity.ERROR
    assert report.http_status is None


# --- release validation: checksum identity vs source verification -------------

def _registry():
    from app.forecasting_engine.services.sources import cms_release_registry
    return cms_release_registry


def test_a_checksum_match_is_identity_not_verification(cms_csv, dataset):
    """A digest says 'same bytes as before'. Whether the file is fit to forecast from is
    a separate set of checks, which is what validate_release runs."""
    registry = _registry()
    report, facts = registry.validate_release(
        cms_csv, dataset, 2024, provenance_class=ProvenanceClass.USER_SUPPLIED_FILE)
    assert report.passed
    assert {c.name for c in report.checks} == {"provenance", "schema", "units", "duplicates"}
    # The digest is recorded as a fact about the file, not as the reason it passed.
    assert len(facts["content_sha256"]) == 64
    assert facts["row_count"] == 10


def test_a_new_release_validates_on_its_own_merits_without_a_known_digest(cms_csv, dataset):
    """The excerpt's digest is not the one in the descriptor, yet it validates."""
    registry = _registry()
    assert classify_file(
        __import__("hashlib").sha256(cms_csv.encode()).hexdigest(), dataset
    ) is FileVerificationStatus.UNRECOGNISED
    report, _ = registry.validate_release(
        cms_csv, dataset, 2024, provenance_class=ProvenanceClass.USER_SUPPLIED_FILE)
    assert report.passed


def test_validation_fails_when_the_schema_does_not_resolve(dataset):
    registry = _registry()
    report, _ = registry.validate_release(
        "a,b,c\\n1,2,3\\n", dataset, 2024, provenance_class=ProvenanceClass.USER_SUPPLIED_FILE)
    assert not report.passed
    assert any(c.name == "schema" and not c.passed for c in report.checks)


def test_validation_fails_when_rollup_rows_are_absent(cms_csv, dataset):
    registry = _registry()
    lines = cms_csv.splitlines()
    without_rollup = [lines[0]] + [l for l in lines[1:] if ",Overall," not in l]
    report, _ = registry.validate_release(
        "\\n".join(without_rollup) + "\\n", dataset, 2024,
        provenance_class=ProvenanceClass.USER_SUPPLIED_FILE)
    assert not report.passed
    assert any(c.name == "duplicates" and not c.passed for c in report.checks)


def test_validation_fails_when_archived_provenance_has_no_retrieval_url(cms_csv, dataset):
    registry = _registry()
    report, _ = registry.validate_release(
        cms_csv, dataset, 2024,
        provenance_class=ProvenanceClass.ARCHIVED_CMS_PUBLICATION, retrieval_url=None)
    assert not report.passed
    assert any(c.name == "provenance" and not c.passed for c in report.checks)


def test_validation_fails_when_the_publication_url_is_off_host(cms_csv, dataset):
    registry = _registry()
    report, _ = registry.validate_release(
        cms_csv, dict(dataset, csv_url="https://example.com/file.csv"), 2024,
        provenance_class=ProvenanceClass.USER_SUPPLIED_FILE)
    assert not report.passed
    assert any(c.name == "provenance" and not c.passed for c in report.checks)


def test_the_validation_report_is_serialisable_and_lists_every_check(cms_csv, dataset):
    registry = _registry()
    report, _ = registry.validate_release(
        cms_csv, dataset, 2024, provenance_class=ProvenanceClass.USER_SUPPLIED_FILE)
    as_dict = report.as_dict()
    assert as_dict["passed"] is True
    assert len(as_dict["checks"]) == 4
    assert all(set(c) == {"name", "passed", "detail"} for c in as_dict["checks"])


# --- the recurring metadata check --------------------------------------------

def test_the_metadata_check_reads_the_published_reporting_year():
    import datetime as dt

    from app.forecasting_engine.services.sources import cms_metadata_check

    payload = {"name": "Medicare Part D Spending by Drug",
               "rowsUpdatedAt": 1783656331,
               "metadata": {"custom_fields": {"Common Core": {
                   "Temporal Applicability": "2024-01-01/2024-12-31"}}}}
    year, published = cms_metadata_check._parse_temporal_end_year(payload)
    assert year == 2024
    assert isinstance(published, dt.date)


def test_freshness_is_unknown_without_any_successful_check(dataset):
    from app.forecasting_engine.services.sources import cms_metadata_check

    assert cms_metadata_check.freshness_for(2024, dataset, None) is PublicationFreshness.UNKNOWN


def test_freshness_is_unknown_when_the_last_check_is_stale(dataset):
    import datetime as dt

    from app.forecasting_engine.models.db_models import CmsMetadataCheck
    from app.forecasting_engine.services.sources import cms_metadata_check

    stale = CmsMetadataCheck(
        source_kind="cms_part_d", status="ok", latest_data_year_seen=2024,
        checked_at=dt.datetime.now(dt.timezone.utc)
        - dt.timedelta(days=cms_metadata_check.STALE_AFTER_DAYS + 1))
    assert cms_metadata_check.freshness_for(2024, dataset, stale) is PublicationFreshness.UNKNOWN


def test_freshness_tracks_the_year_the_check_actually_saw(dataset):
    import datetime as dt

    from app.forecasting_engine.models.db_models import CmsMetadataCheck
    from app.forecasting_engine.services.sources import cms_metadata_check

    recent = CmsMetadataCheck(
        source_kind="cms_part_d", status="ok", latest_data_year_seen=2025,
        checked_at=dt.datetime.now(dt.timezone.utc))
    assert cms_metadata_check.freshness_for(2024, dataset, recent) is \
        PublicationFreshness.SUPERSEDED
    assert cms_metadata_check.freshness_for(2025, dataset, recent) is \
        PublicationFreshness.CURRENT
