"""The unit and mode vocabulary shared by the math engine, the API schemas and the
source adapters.

Keeping these as enums rather than free strings is what lets the engine refuse to
aggregate incompatible things: a claim count is not a dosage unit, a beneficiary is
not an annual treated patient, and gross spending is not manufacturer net revenue.
"""
from __future__ import annotations

import re
from enum import Enum


class ForecastMode(str, Enum):
    """The two mutually exclusive input modes. A parameter set is one or the other."""

    EPIDEMIOLOGY = "epidemiology"
    OBSERVED_VOLUME = "observed_volume"


class PopulationBasis(str, Enum):
    """Whether target_population counts people living with the disease (prevalence)
    or newly diagnosed in the year (incidence).

    Never inferred and never mixed: the two answer different questions and combining
    them silently is one of the easiest ways to produce a wrong patient number.
    """

    PREVALENCE = "prevalence"
    INCIDENCE = "incidence"


class TreatmentBasis(str, Enum):
    """Whether a treated patient represents ongoing chronic therapy across the year or
    one discrete annual treatment course. Drives how units_per_patient_per_year is read."""

    CHRONIC = "chronic"
    ANNUAL_COURSE = "annual_course"


class VolumeMetric(str, Enum):
    """Metrics the engine can project. Each is returned only when its conversion
    inputs exist; otherwise it is explicitly null, never zero."""

    PATIENTS = "patients"
    DOSAGE_UNITS = "dosage_units"
    PACKS = "packs"
    API_KG = "api_kg"
    REVENUE = "revenue"


class PriceBasis(str, Enum):
    """The unit a net price is quoted in. Revenue multiplies a volume by a price in
    the SAME unit; there is no implicit conversion between these."""

    PER_DOSAGE_UNIT = "per_dosage_unit"
    PER_PACK = "per_pack"
    PER_API_KG = "per_api_kg"


PRICE_BASIS_METRIC: dict[PriceBasis, VolumeMetric] = {
    PriceBasis.PER_DOSAGE_UNIT: VolumeMetric.DOSAGE_UNITS,
    PriceBasis.PER_PACK: VolumeMetric.PACKS,
    PriceBasis.PER_API_KG: VolumeMetric.API_KG,
}


class SourceMetric(str, Enum):
    """What an observed source row actually counts.

    CLAIMS and THIRTY_DAY_FILLS are prescription events, not patients and not dosage
    units. BENEFICIARIES are distinct people in the source's covered population, which
    is not the same as annual treated patients nationally. SPENDING is gross payment
    at the source's own price basis, never manufacturer net revenue.
    """

    CLAIMS = "claims"
    THIRTY_DAY_FILLS = "thirty_day_fills"
    DOSAGE_UNITS = "dosage_units"
    PACKS = "packs"
    BENEFICIARIES = "beneficiaries"
    SPENDING = "spending"


#: Source metrics that may seed observed-volume mode's reference_units directly.
#: Claims, fills, beneficiaries and spending are deliberately absent: converting any
#: of them into dosage units needs an explicit, documented factor from the user.
BASELINE_ELIGIBLE_METRICS = frozenset({SourceMetric.DOSAGE_UNITS, SourceMetric.PACKS})


class SourceKind(str, Enum):
    """Where an observation came from. Drives how much the UI trusts it on sight."""

    CMS_PART_D = "cms_part_d"
    FILE_IMPORT = "file_import"
    MANUAL_ENTRY = "manual_entry"


_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")


def is_valid_currency_code(code: str) -> bool:
    """ISO-4217 shape check only. Deliberately not a closed list of codes — the point
    is to force the caller to state a currency, not to police which ones exist."""
    return bool(_CURRENCY_RE.match(code))


class ProvenanceClass(str, Enum):
    """How a figure actually reached this application.

    This is deliberately NOT the same as which publisher produced it. A CMS file
    retrieved from a web archive is an ARCHIVED_CMS_PUBLICATION: the publisher is CMS,
    but the retrieval was not live CMS access, and claiming otherwise would overstate
    what we can attest to.
    """

    LIVE_CMS_API = "live_cms_api"
    ARCHIVED_CMS_PUBLICATION = "archived_cms_publication"
    USER_SUPPLIED_FILE = "user_supplied_file"
    MANUAL_ENTRY = "manual_entry"


class FileVerificationStatus(str, Enum):
    """Does the ingested file match the copy whose contents were verified?"""

    VERIFIED = "verified"          # checksum matches the descriptor's recorded digest
    UNRECOGNISED = "unrecognised"  # parsed fine, but this exact file was not the one verified
    MISMATCH = "mismatch"          # claims to be the verified file but the digest differs


class PublicationFreshness(str, Enum):
    """Is the reporting year the newest CMS has published, as far as we know?"""

    CURRENT = "current"
    SUPERSEDED = "superseded"
    UNKNOWN = "unknown"


class ApiConnectivity(str, Enum):
    """Can this deployment reach the live CMS API right now?

    Kept strictly separate from file verification and publication freshness: a
    deployment can hold a verified, current file and still have no API connectivity,
    and none of those three facts implies either of the others.
    """

    REACHABLE = "reachable"
    BLOCKED = "blocked"
    ERROR = "error"
    NOT_CHECKED = "not_checked"
