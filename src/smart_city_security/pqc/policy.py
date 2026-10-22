from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True, slots=True)
class AlgorithmSuite:
    suite_id: str
    key_establishment: tuple[str, ...]
    signature: tuple[str, ...]
    aead: str
    status: str = "approved"
    not_after: str | None = None


class CryptographicPolicy:

    def __init__(self, suites: list[AlgorithmSuite]) -> None:
        if not suites:
            raise ValueError("At least one algorithm suite is required")
        self._suites: dict[str, AlgorithmSuite] = {}
        for suite in suites:
            if suite.suite_id in self._suites:
                raise ValueError(f"Duplicate suite: {suite.suite_id}")
            if suite.status not in {"approved", "deprecated", "disabled"}:
                raise ValueError(f"Invalid suite status: {suite.status}")
            self._suites[suite.suite_id] = suite

    def require(self, suite_id: str, *, at: datetime | None = None) -> AlgorithmSuite:
        suite = self._suites.get(suite_id)
        if suite is None or suite.status == "disabled":
            raise ValueError(f"Algorithm suite is not enabled: {suite_id}")
        observed_at = datetime.now(UTC) if at is None else at
        if suite.not_after and observed_at >= datetime.fromisoformat(suite.not_after):
            raise ValueError(f"Algorithm suite expired: {suite_id}")
        return suite

    def negotiation(
        self, offered_suite_ids: list[str], *, allow_deprecated: bool = False
    ) -> AlgorithmSuite:
        for suite_id in offered_suite_ids:
            try:
                suite = self.require(suite_id)
            except ValueError:
                continue
            if suite.status == "approved" or allow_deprecated:
                return suite
        raise ValueError("No mutually acceptable algorithm suite")

    def inventory(self) -> tuple[AlgorithmSuite, ...]:
        return tuple(self._suites.values())


PILOT_HYBRID_SUITE = AlgorithmSuite(
    suite_id="SC-HYBRID-MLKEM768-P256-MLDSA65-ECDSA-AES256GCM-v1",
    key_establishment=("ML-KEM-768", "ECDH-P256"),
    signature=("ML-DSA-65", "ECDSA-P256-SHA256"),
    aead="AES-256-GCM",
)
