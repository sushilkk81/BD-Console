"""Forecast persistence.

SQLAlchemy 2.0 Declarative on the application's existing Base, matching app/models.py.
Tenancy is NOT duplicated here: like sku_rows and request_messages, these tables hang
off requests and inherit requests.org_id, so there is no second copy of ownership to
drift out of step with the first.
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

from sqlalchemy import (BigInteger, CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON,
                        Numeric, String, Text, UniqueConstraint, text)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

MOLECULE_MAX_LEN = 200
GEOGRAPHY_MAX_LEN = 50
OVERRIDE_REASON_MAX_LEN = 500


class MoleculeForecastParameter(Base):
    """One reviewed parameter set for one molecule-market configuration.

    Granularity: either ONE request-level row (sku_row_id IS NULL) covering the whole
    request, or one row per SKU for requests whose strengths/presentations forecast
    differently. Never both — mixing the two levels would double-count the same volume
    when the rows are aggregated. The partial unique index below enforces at most one
    request-level row; the service layer rejects adding SKU rows alongside it.
    """

    __tablename__ = "molecule_forecast_parameters"
    __table_args__ = (
        UniqueConstraint("request_id", "sku_row_id", name="uq_mfp_request_sku"),
        # NULLs compare distinct in both PostgreSQL and SQLite, so the constraint above
        # does NOT stop two request-level rows. This partial index does.
        Index(
            "uq_mfp_request_level",
            "request_id",
            unique=True,
            postgresql_where=text("sku_row_id IS NULL"),
            sqlite_where=text("sku_row_id IS NULL"),
        ),
        Index("ix_mfp_request_id", "request_id"),
        CheckConstraint(
            "base_peak_share >= 0 AND base_peak_share <= 1", name="ck_mfp_base_peak_share_unit"),
        CheckConstraint(
            "upside_peak_share >= 0 AND upside_peak_share <= 1", name="ck_mfp_upside_peak_share_unit"),
        CheckConstraint(
            "base_peak_share <= upside_peak_share", name="ck_mfp_base_not_above_upside"),
        CheckConstraint("ramp_speed > 0", name="ck_mfp_ramp_speed_positive"),
        CheckConstraint(
            "inflection_year >= 0.5 AND inflection_year <= 15", name="ck_mfp_inflection_bounds"),
        CheckConstraint(
            "target_population IS NULL OR target_population >= 0", name="ck_mfp_population_nonneg"),
        CheckConstraint(
            "reference_units IS NULL OR reference_units >= 0", name="ck_mfp_reference_units_nonneg"),
        CheckConstraint(
            "annual_growth_rate IS NULL OR annual_growth_rate > -1", name="ck_mfp_growth_above_neg_one"),
        CheckConstraint(
            "units_per_patient_per_year IS NULL OR units_per_patient_per_year > 0",
            name="ck_mfp_units_per_patient_positive"),
        CheckConstraint(
            "units_per_pack IS NULL OR units_per_pack > 0", name="ck_mfp_units_per_pack_positive"),
        CheckConstraint(
            "active_ingredient_mg_per_unit IS NULL OR active_ingredient_mg_per_unit > 0",
            name="ck_mfp_mg_per_unit_positive"),
        CheckConstraint(
            "company_capture_share IS NULL OR "
            "(company_capture_share >= 0 AND company_capture_share <= 1)",
            name="ck_mfp_company_capture_unit"),
        CheckConstraint(
            "probability_of_success IS NULL OR "
            "(probability_of_success >= 0 AND probability_of_success <= 1)",
            name="ck_mfp_pos_unit"),
        CheckConstraint("net_price IS NULL OR net_price >= 0", name="ck_mfp_net_price_nonneg"),
        CheckConstraint("revision >= 1", name="ck_mfp_revision_positive"),
        # Mode-specific required fields, enforced in the database as well as in the
        # request schema so a direct SQL write cannot create an uncomputable row.
        CheckConstraint(
            "(forecast_mode = 'epidemiology' AND target_population IS NOT NULL "
            " AND population_basis IS NOT NULL AND treatment_basis IS NOT NULL "
            " AND reference_units IS NULL AND reference_year IS NULL) "
            "OR (forecast_mode = 'observed_volume' AND reference_units IS NOT NULL "
            " AND reference_year IS NOT NULL AND annual_growth_rate IS NOT NULL "
            " AND target_population IS NULL AND company_capture_share IS NULL)",
            name="ck_mfp_mode_required_fields"),
        CheckConstraint(
            "(net_price IS NULL AND price_currency IS NULL AND price_basis IS NULL) "
            "OR (net_price IS NOT NULL AND price_currency IS NOT NULL AND price_basis IS NOT NULL)",
            name="ck_mfp_price_triplet_complete"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # requests.id is sa.Integer (see alembic 0001/0003) — matching it exactly, not BIGINT.
    request_id: Mapped[int] = mapped_column(ForeignKey("requests.id"), nullable=False)
    sku_row_id: Mapped[Optional[int]] = mapped_column(ForeignKey("sku_rows.id"), nullable=True)

    molecule: Mapped[str] = mapped_column(String(MOLECULE_MAX_LEN), nullable=False)
    brand: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    geography: Mapped[str] = mapped_column(String(GEOGRAPHY_MAX_LEN), nullable=False)
    indication: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    strength: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    dosage_form: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    forecast_start_year: Mapped[int] = mapped_column(Integer, nullable=False)
    launch_year: Mapped[int] = mapped_column(Integer, nullable=False)
    forecast_mode: Mapped[str] = mapped_column(String(20), nullable=False)

    # Epidemiology mode. BIGINT: a global prevalence population overflows INT4.
    target_population: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    population_basis: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    treatment_basis: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    # Observed-volume mode.
    reference_units: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    reference_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    annual_growth_rate: Mapped[Optional[float]] = mapped_column(nullable=True)
    reference_coverage_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    base_peak_share: Mapped[float] = mapped_column(nullable=False)
    upside_peak_share: Mapped[float] = mapped_column(nullable=False)
    ramp_speed: Mapped[float] = mapped_column(nullable=False)
    inflection_year: Mapped[float] = mapped_column(nullable=False)

    units_per_patient_per_year: Mapped[Optional[float]] = mapped_column(nullable=True)
    units_per_patient_basis: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    units_per_pack: Mapped[Optional[float]] = mapped_column(nullable=True)
    active_ingredient_mg_per_unit: Mapped[Optional[float]] = mapped_column(nullable=True)
    company_capture_share: Mapped[Optional[float]] = mapped_column(nullable=True)
    probability_of_success: Mapped[Optional[float]] = mapped_column(nullable=True)

    # Money is NUMERIC end to end, never float.
    net_price: Mapped[Optional[float]] = mapped_column(Numeric(18, 6), nullable=True)
    price_currency: Mapped[Optional[str]] = mapped_column(String(3), nullable=True)
    price_basis: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    source_observation_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("molecule_source_observations.id"), nullable=True)
    override_reason: Mapped[Optional[str]] = mapped_column(String(OVERRIDE_REASON_MAX_LEN), nullable=True)
    #: The source value an override replaced, retained verbatim so the override is reversible.
    overridden_source_value: Mapped[Optional[float]] = mapped_column(nullable=True)

    model_version: Mapped[str] = mapped_column(String(20), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    source_observation: Mapped[Optional["MoleculeSourceObservation"]] = relationship()


class MoleculeSourceObservation(Base):
    """One observed utilization datum, with everything needed to find it again.

    A suppressed or unreported value stays NULL. It is never stored as 0, because a
    suppressed small cell and a genuine zero mean opposite things.
    """

    __tablename__ = "molecule_source_observations"
    __table_args__ = (
        Index("ix_mso_request_id", "request_id"),
        Index("ix_mso_lookup", "source_kind", "geography", "period_label"),
        CheckConstraint("value IS NULL OR value >= 0", name="ck_mso_value_nonneg"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    #: NULL for a search result that has not been attached to a request yet.
    request_id: Mapped[Optional[int]] = mapped_column(ForeignKey("requests.id"), nullable=True)

    source_kind: Mapped[str] = mapped_column(String(30), nullable=False)
    source_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_identifier: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    molecule: Mapped[Optional[str]] = mapped_column(String(MOLECULE_MAX_LEN), nullable=True)
    brand: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    geography: Mapped[str] = mapped_column(String(GEOGRAPHY_MAX_LEN), nullable=False)
    #: Exactly whose utilization this covers, in words, e.g. "Medicare Part D enrolled
    #: beneficiaries only — not the total US market".
    coverage: Mapped[str] = mapped_column(Text, nullable=False)
    period_label: Mapped[str] = mapped_column(String(50), nullable=False)
    period_start: Mapped[Optional[dt.date]] = mapped_column(nullable=True)
    period_end: Mapped[Optional[dt.date]] = mapped_column(nullable=True)
    metric: Mapped[str] = mapped_column(String(30), nullable=False)
    value: Mapped[Optional[float]] = mapped_column(Numeric(20, 4), nullable=True)
    unit: Mapped[str] = mapped_column(String(30), nullable=False)
    strength: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    dosage_form: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    currency: Mapped[Optional[str]] = mapped_column(String(3), nullable=True)
    #: What was done to the source number to get `value`, or "none".
    transformation: Mapped[str] = mapped_column(Text, nullable=False, default="none")
    ambiguous_match: Mapped[bool] = mapped_column(nullable=False, default=False)
    retrieved_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    raw_record: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)

    #: How the figure reached us. `source_url` stays the publisher's canonical URL; these
    #: record the retrieval separately so an archived copy is never presented as live
    #: access to the publisher.
    provenance_class: Mapped[str] = mapped_column(
        String(40), nullable=False, default="user_supplied_file",
        server_default="user_supplied_file")
    retrieval_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    archive_capture_date: Mapped[Optional[dt.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True)
    content_sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    file_verification: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)


class MoleculeForecastAudit(Base):
    """Append-only history. One row per accepted revision, holding the full parameter
    payload as it stood AFTER that revision, so any past forecast can be recomputed."""

    __tablename__ = "molecule_forecast_audit"
    __table_args__ = (
        UniqueConstraint("parameter_id", "revision", name="uq_mfa_parameter_revision"),
        Index("ix_mfa_parameter_id", "parameter_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    parameter_id: Mapped[int] = mapped_column(
        ForeignKey("molecule_forecast_parameters.id"), nullable=False)
    request_id: Mapped[int] = mapped_column(ForeignKey("requests.id"), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    change_reason: Mapped[Optional[str]] = mapped_column(String(OVERRIDE_REASON_MAX_LEN), nullable=True)
    changed_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    changed_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CmsDatasetRelease(Base):
    """One CMS file release this deployment has seen, and how far it got in validation.

    This is what lets a NEW legitimate CMS release enter a documented workflow instead of
    requiring someone to edit a hardcoded digest. A file whose checksum is unknown is
    recorded here as `pending`; it is promoted to `validated` only by passing the
    provenance, schema, units and duplicate checks in
    services/sources/cms_release_registry.py. Superseded releases are kept, never
    overwritten, so a past forecast can still be traced to the file it used.
    """

    __tablename__ = "cms_dataset_releases"
    __table_args__ = (
        UniqueConstraint("source_kind", "data_year", "content_sha256",
                         name="uq_cdr_source_year_digest"),
        Index("ix_cdr_active", "source_kind", "is_active"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_kind: Mapped[str] = mapped_column(String(30), nullable=False)
    dataset_uuid: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    publication_url: Mapped[str] = mapped_column(Text, nullable=False)
    release_label: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    data_year: Mapped[int] = mapped_column(Integer, nullable=False)
    #: Publication date as stated by the publisher, not the date we read the file.
    published_on: Mapped[Optional[dt.date]] = mapped_column(nullable=True)

    #: Checksum IDENTIFIES a file. It does not verify the source — see validation_status.
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    row_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    resolved_columns: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    provenance_class: Mapped[str] = mapped_column(String(40), nullable=False)
    retrieval_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    archive_capture_date: Mapped[Optional[dt.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True)

    #: pending | validated | rejected | superseded
    validation_status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    validation_report: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=False)

    first_seen_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    validated_at: Mapped[Optional[dt.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True)
    validated_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)


class CmsMetadataCheck(Base):
    """One run of the recurring metadata check for new CMS releases.

    Freshness is derived from these rows. If the newest successful check is older than the
    expected interval — or there has never been one — freshness is reported as stale or
    unknown rather than continuing to claim the data is current.
    """

    __tablename__ = "cms_metadata_checks"
    __table_args__ = (Index("ix_cmc_checked_at", "source_kind", "checked_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source_kind: Mapped[str] = mapped_column(String(30), nullable=False)
    checked_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: ok | unreachable | error
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    metadata_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    latest_data_year_seen: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    latest_release_label: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    published_on_seen: Mapped[Optional[dt.date]] = mapped_column(nullable=True)
    new_release_detected: Mapped[bool] = mapped_column(nullable=False, default=False)
    detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    raw_metadata: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
