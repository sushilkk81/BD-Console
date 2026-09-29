"""The contract every utilization source implements.

Network access lives here and nowhere else: the math engine, the API layer and the
persistence layer never make an outbound call. A forecast GET never reaches upstream.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from enum import Enum
from decimal import Decimal
from typing import Protocol

from app.forecasting_engine.core.units import (FileVerificationStatus, ProvenanceClass,
                                                SourceKind, SourceMetric)

#: Hard ceiling on rows returned from any one search or import. Bounds memory and
#: keeps a mistyped query from pulling an entire dataset into the request.
MAX_ROWS = 500

#: Outbound HTTP budget, mirroring app/services/external_lookup.py's conventions.
HTTP_TIMEOUT_SECONDS = 10.0
MAX_ATTEMPTS = 3
BACKOFF_BASE_SECONDS = 0.5


@dataclass(frozen=True)
class Observation:
    """One observed datum, before it is persisted.

    `value` of None means suppressed, withheld or not reported by the source. It is
    never coerced to 0: a suppressed small cell and a true zero are different facts.
    """

    source_kind: SourceKind
    geography: str
    coverage: str
    period_label: str
    metric: SourceMetric
    unit: str
    value: Decimal | None
    retrieved_at: dt.datetime
    transformation: str = "none"
    source_url: str | None = None
    source_identifier: str | None = None
    molecule: str | None = None
    brand: str | None = None
    strength: str | None = None
    dosage_form: str | None = None
    currency: str | None = None
    period_start: dt.date | None = None
    period_end: dt.date | None = None
    ambiguous_match: bool = False
    raw_record: dict | None = None

    #: How this figure reached us, which is not the same as who published it.
    provenance_class: ProvenanceClass = ProvenanceClass.USER_SUPPLIED_FILE
    #: The URL actually fetched, when it differs from source_url (the publication URL).
    #: For an archived copy this is the archive URL, so both are on the record.
    retrieval_url: str | None = None
    #: When the archive captured the publisher's file (not when we read it).
    archive_capture_date: dt.datetime | None = None
    #: SHA-256 of the exact bytes ingested, computed here rather than taken on trust.
    content_sha256: str | None = None
    #: Whether those bytes are the copy this integration was verified against.
    file_verification: FileVerificationStatus | None = None


class SourceStatus(str, Enum):
    """Why a search returned what it returned.

    These are deliberately distinct, because they call for different actions and the UI
    must not blur them: AVAILABLE with rows is evidence; NO_MATCHING_RECORDS means we
    asked and the source genuinely has nothing for this query; CONFIGURATION_INCOMPLETE
    means we never asked because this deployment is not set up; API_UNAVAILABLE means we
    asked and could not get an answer. Only the first is a statement about the molecule.
    """

    AVAILABLE = "available"
    NO_MATCHING_RECORDS = "no_matching_records"
    CONFIGURATION_INCOMPLETE = "configuration_incomplete"
    API_UNAVAILABLE = "api_unavailable"


@dataclass(frozen=True)
class SourceSearchResult:
    """What a search returned, including the reason it returned nothing.

    An unavailable source reports WHY. It never degrades into an empty success, which
    would read in the UI as "this molecule has no utilization" rather than "we could
    not ask".
    """

    source_kind: SourceKind
    available: bool
    status: SourceStatus = SourceStatus.AVAILABLE
    observations: list[Observation] = field(default_factory=list)
    unavailable_reason: str | None = None
    warnings: list[str] = field(default_factory=list)
    truncated: bool = False


class SourceAdapter(Protocol):
    """A utilization source. Implementations must not raise into the router."""

    source_kind: SourceKind

    def search(
        self,
        *,
        molecule: str | None,
        brand: str | None,
        geography: str,
        period: str | None,
    ) -> SourceSearchResult:
        ...
