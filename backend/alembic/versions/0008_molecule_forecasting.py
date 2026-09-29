"""Molecule market intelligence and sales volume forecasting

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-29

Adds reviewed forecast parameter sets, the source evidence behind them, and an
append-only revision history. Forecast rows hang off requests and inherit
requests.org_id for tenancy, so no ownership column is duplicated here.

"""
from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "molecule_source_observations",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("request_id", sa.Integer, sa.ForeignKey("requests.id"), nullable=True),
        sa.Column("source_kind", sa.String(30), nullable=False),
        sa.Column("source_url", sa.Text, nullable=True),
        sa.Column("source_identifier", sa.String(200), nullable=True),
        sa.Column("molecule", sa.String(200), nullable=True),
        sa.Column("brand", sa.String(200), nullable=True),
        sa.Column("geography", sa.String(50), nullable=False),
        sa.Column("coverage", sa.Text, nullable=False),
        sa.Column("period_label", sa.String(50), nullable=False),
        sa.Column("period_start", sa.Date, nullable=True),
        sa.Column("period_end", sa.Date, nullable=True),
        sa.Column("metric", sa.String(30), nullable=False),
        # NULL means suppressed or not reported by the source — never stored as 0.
        sa.Column("value", sa.Numeric(20, 4), nullable=True),
        sa.Column("unit", sa.String(30), nullable=False),
        sa.Column("strength", sa.String(50), nullable=True),
        sa.Column("dosage_form", sa.String(100), nullable=True),
        sa.Column("currency", sa.String(3), nullable=True),
        sa.Column("transformation", sa.Text, nullable=False),
        sa.Column("ambiguous_match", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_record", sa.JSON, nullable=True),
        sa.Column("created_by", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.CheckConstraint("value IS NULL OR value >= 0", name="ck_mso_value_nonneg"),
    )
    op.create_index("ix_mso_request_id", "molecule_source_observations", ["request_id"])
    op.create_index("ix_mso_lookup", "molecule_source_observations",
                    ["source_kind", "geography", "period_label"])

    op.create_table(
        "molecule_forecast_parameters",
        sa.Column("id", sa.Integer, primary_key=True),
        # requests.id is INTEGER (see 0001/0003); matched exactly rather than widened.
        sa.Column("request_id", sa.Integer, sa.ForeignKey("requests.id"), nullable=False),
        sa.Column("sku_row_id", sa.Integer, sa.ForeignKey("sku_rows.id"), nullable=True),
        sa.Column("molecule", sa.String(200), nullable=False),
        sa.Column("brand", sa.String(200), nullable=True),
        sa.Column("geography", sa.String(50), nullable=False),
        sa.Column("indication", sa.String(200), nullable=True),
        sa.Column("strength", sa.String(50), nullable=True),
        sa.Column("dosage_form", sa.String(100), nullable=True),
        sa.Column("forecast_start_year", sa.Integer, nullable=False),
        sa.Column("launch_year", sa.Integer, nullable=False),
        sa.Column("forecast_mode", sa.String(20), nullable=False),
        # BIGINT: a global prevalence population overflows INT4.
        sa.Column("target_population", sa.BigInteger, nullable=True),
        sa.Column("population_basis", sa.String(20), nullable=True),
        sa.Column("treatment_basis", sa.String(20), nullable=True),
        sa.Column("reference_units", sa.BigInteger, nullable=True),
        sa.Column("reference_year", sa.Integer, nullable=True),
        sa.Column("annual_growth_rate", sa.Float, nullable=True),
        sa.Column("reference_coverage_note", sa.Text, nullable=True),
        sa.Column("base_peak_share", sa.Float, nullable=False),
        sa.Column("upside_peak_share", sa.Float, nullable=False),
        sa.Column("ramp_speed", sa.Float, nullable=False),
        sa.Column("inflection_year", sa.Float, nullable=False),
        sa.Column("units_per_patient_per_year", sa.Float, nullable=True),
        sa.Column("units_per_patient_basis", sa.Text, nullable=True),
        sa.Column("units_per_pack", sa.Float, nullable=True),
        sa.Column("active_ingredient_mg_per_unit", sa.Float, nullable=True),
        sa.Column("company_capture_share", sa.Float, nullable=True),
        sa.Column("probability_of_success", sa.Float, nullable=True),
        sa.Column("net_price", sa.Numeric(18, 6), nullable=True),
        sa.Column("price_currency", sa.String(3), nullable=True),
        sa.Column("price_basis", sa.String(20), nullable=True),
        sa.Column("source_observation_id", sa.Integer,
                  sa.ForeignKey("molecule_source_observations.id"), nullable=True),
        sa.Column("override_reason", sa.String(500), nullable=True),
        sa.Column("overridden_source_value", sa.Float, nullable=True),
        sa.Column("model_version", sa.String(20), nullable=False),
        sa.Column("revision", sa.Integer, nullable=False, server_default="1"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.UniqueConstraint("request_id", "sku_row_id", name="uq_mfp_request_sku"),
        sa.CheckConstraint("base_peak_share >= 0 AND base_peak_share <= 1",
                           name="ck_mfp_base_peak_share_unit"),
        sa.CheckConstraint("upside_peak_share >= 0 AND upside_peak_share <= 1",
                           name="ck_mfp_upside_peak_share_unit"),
        sa.CheckConstraint("base_peak_share <= upside_peak_share",
                           name="ck_mfp_base_not_above_upside"),
        sa.CheckConstraint("ramp_speed > 0", name="ck_mfp_ramp_speed_positive"),
        sa.CheckConstraint("inflection_year >= 0.5 AND inflection_year <= 15",
                           name="ck_mfp_inflection_bounds"),
        sa.CheckConstraint("target_population IS NULL OR target_population >= 0",
                           name="ck_mfp_population_nonneg"),
        sa.CheckConstraint("reference_units IS NULL OR reference_units >= 0",
                           name="ck_mfp_reference_units_nonneg"),
        sa.CheckConstraint("annual_growth_rate IS NULL OR annual_growth_rate > -1",
                           name="ck_mfp_growth_above_neg_one"),
        sa.CheckConstraint(
            "units_per_patient_per_year IS NULL OR units_per_patient_per_year > 0",
            name="ck_mfp_units_per_patient_positive"),
        sa.CheckConstraint("units_per_pack IS NULL OR units_per_pack > 0",
                           name="ck_mfp_units_per_pack_positive"),
        sa.CheckConstraint(
            "active_ingredient_mg_per_unit IS NULL OR active_ingredient_mg_per_unit > 0",
            name="ck_mfp_mg_per_unit_positive"),
        sa.CheckConstraint(
            "company_capture_share IS NULL OR "
            "(company_capture_share >= 0 AND company_capture_share <= 1)",
            name="ck_mfp_company_capture_unit"),
        sa.CheckConstraint(
            "probability_of_success IS NULL OR "
            "(probability_of_success >= 0 AND probability_of_success <= 1)",
            name="ck_mfp_pos_unit"),
        sa.CheckConstraint("net_price IS NULL OR net_price >= 0", name="ck_mfp_net_price_nonneg"),
        sa.CheckConstraint("revision >= 1", name="ck_mfp_revision_positive"),
        sa.CheckConstraint(
            "(forecast_mode = 'epidemiology' AND target_population IS NOT NULL "
            " AND population_basis IS NOT NULL AND treatment_basis IS NOT NULL "
            " AND reference_units IS NULL AND reference_year IS NULL) "
            "OR (forecast_mode = 'observed_volume' AND reference_units IS NOT NULL "
            " AND reference_year IS NOT NULL AND annual_growth_rate IS NOT NULL "
            " AND target_population IS NULL AND company_capture_share IS NULL)",
            name="ck_mfp_mode_required_fields"),
        sa.CheckConstraint(
            "(net_price IS NULL AND price_currency IS NULL AND price_basis IS NULL) "
            "OR (net_price IS NOT NULL AND price_currency IS NOT NULL AND price_basis IS NOT NULL)",
            name="ck_mfp_price_triplet_complete"),
    )
    op.create_index("ix_mfp_request_id", "molecule_forecast_parameters", ["request_id"])
    # UNIQUE(request_id, sku_row_id) does not constrain request-level rows, because NULLs
    # compare distinct. This partial index allows at most one request-level row per request.
    op.create_index(
        "uq_mfp_request_level", "molecule_forecast_parameters", ["request_id"], unique=True,
        postgresql_where=sa.text("sku_row_id IS NULL"),
        sqlite_where=sa.text("sku_row_id IS NULL"),
    )

    op.create_table(
        "molecule_forecast_audit",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("parameter_id", sa.Integer,
                  sa.ForeignKey("molecule_forecast_parameters.id"), nullable=False),
        sa.Column("request_id", sa.Integer, sa.ForeignKey("requests.id"), nullable=False),
        sa.Column("revision", sa.Integer, nullable=False),
        sa.Column("payload", sa.JSON, nullable=False),
        sa.Column("change_reason", sa.String(500), nullable=True),
        sa.Column("changed_by", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("parameter_id", "revision", name="uq_mfa_parameter_revision"),
    )
    op.create_index("ix_mfa_parameter_id", "molecule_forecast_audit", ["parameter_id"])


def downgrade() -> None:
    op.drop_index("ix_mfa_parameter_id", table_name="molecule_forecast_audit")
    op.drop_table("molecule_forecast_audit")
    op.drop_index("uq_mfp_request_level", table_name="molecule_forecast_parameters")
    op.drop_index("ix_mfp_request_id", table_name="molecule_forecast_parameters")
    op.drop_table("molecule_forecast_parameters")
    op.drop_index("ix_mso_lookup", table_name="molecule_source_observations")
    op.drop_index("ix_mso_request_id", table_name="molecule_source_observations")
    op.drop_table("molecule_source_observations")
