from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass

from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    confusion_matrix,
    precision_recall_fscore_support,
    roc_auc_score,
)


@dataclass(frozen=True, slots=True)
class MLMetrics:
    accuracy: float
    precision: float
    recall: float
    f1: float
    false_positive_rate: float
    false_negative_rate: float
    pr_auc: float | None = None
    roc_auc: float | None = None

    def to_dict(self) -> dict[str, float]:
        return asdict(self)


def calculate_ml_metrics(
    truth: Iterable[bool],
    predictions: Iterable[bool],
    scores: Iterable[float] | None = None,
) -> MLMetrics:
    truth_values = list(truth)
    prediction_values = list(predictions)
    if len(truth_values) != len(prediction_values) or not truth_values:
        raise ValueError("Truth and predictions must be non-empty and equally sized")
    precision, recall, f1, _ = precision_recall_fscore_support(
        truth_values, prediction_values, average="binary", zero_division=0
    )
    tn, fp, fn, tp = confusion_matrix(
        truth_values, prediction_values, labels=[False, True]
    ).ravel()
    fpr = fp / (fp + tn) if fp + tn else 0.0
    fnr = fn / (fn + tp) if fn + tp else 0.0
    score_values = None if scores is None else list(scores)
    if score_values is not None and len(score_values) != len(truth_values):
        raise ValueError("Scores must have the same length as truth")
    has_both_classes = len(set(truth_values)) == 2
    pr_auc = (
        float(average_precision_score(truth_values, score_values))
        if score_values is not None and has_both_classes
        else None
    )
    roc_auc = (
        float(roc_auc_score(truth_values, score_values))
        if score_values is not None and has_both_classes
        else None
    )
    return MLMetrics(
        accuracy=float(accuracy_score(truth_values, prediction_values)),
        precision=float(precision),
        recall=float(recall),
        f1=float(f1),
        false_positive_rate=float(fpr),
        false_negative_rate=float(fnr),
        pr_auc=pr_auc,
        roc_auc=roc_auc,
    )
