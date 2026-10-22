from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True, slots=True)
class OperatorFeedback:
    alert_id: str
    operator_id: str
    verdict: str
    comment: str = ""
    recorded_at: str = ""

    def __post_init__(self) -> None:
        if self.verdict not in {"true_positive", "false_positive", "uncertain"}:
            raise ValueError("invalid feedback verdict")


class FeedbackStore:
    def __init__(self) -> None:
        self.items: list[OperatorFeedback] = []

    def record(
        self, alert_id: str, operator_id: str, verdict: str, comment: str = ""
    ) -> OperatorFeedback:
        feedback = OperatorFeedback(
            alert_id,
            operator_id,
            verdict,
            comment,
            datetime.now(UTC).isoformat(),
        )
        self.items.append(feedback)
        return feedback
