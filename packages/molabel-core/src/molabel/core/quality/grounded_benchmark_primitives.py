"""Reusable artifact primitives and scorers for grounded benchmark families.

This module is intentionally benchmark-agnostic. It adds typed artifact
contracts, validators, and metric helpers for benchmark families that need
more than scalar label equality:

* calibration and abstention-aware classification,
* multi-label thresholding and hierarchy validation,
* evidence groups and QA-with-evidence bundles,
* ranked retrieval outputs and qrels,
* span-native extraction artifacts,
* grounded generation outputs,
* and document/table anchors.
"""

from __future__ import annotations

import math
import re
import string
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field, model_validator

from molabel.core.utils.canonical import canonical_label_value


def _safe_ratio(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _extract_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        numeric = float(value)
    elif isinstance(value, str):
        text = value.strip().rstrip("%")
        if not text:
            return None
        try:
            numeric = float(text)
        except ValueError:
            return None
        if value.strip().endswith("%"):
            numeric = numeric / 100.0
    else:
        return None
    return numeric


def normalize_answer_text(value: Any) -> str:
    """Normalize free-text answers for answer EM/F1 and extraction comparison."""

    text = str(value or "").strip().lower()
    if not text:
        return ""
    punctuation_to_space = str.maketrans({ch: " " for ch in string.punctuation})
    text = text.translate(punctuation_to_space)
    text = re.sub(r"\b(a|an|the)\b", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def answer_exact_match(predicted: Any, gold: Any) -> float:
    """Return normalized answer exact match."""

    return float(normalize_answer_text(predicted) == normalize_answer_text(gold))


def answer_token_f1(predicted: Any, gold: Any) -> float:
    """Return token-level F1 over normalized answers."""

    pred_tokens = normalize_answer_text(predicted).split()
    gold_tokens = normalize_answer_text(gold).split()
    if not pred_tokens and not gold_tokens:
        return 1.0
    if not pred_tokens or not gold_tokens:
        return 0.0
    pred_counts = Counter(pred_tokens)
    gold_counts = Counter(gold_tokens)
    overlap = sum((pred_counts & gold_counts).values())
    precision = _safe_ratio(overlap, len(pred_tokens))
    recall = _safe_ratio(overlap, len(gold_tokens))
    return _safe_ratio(2 * precision * recall, precision + recall)


class GroundedArtifactValidationIssue(BaseModel):
    """A reusable validation issue for grounded benchmark artifacts."""

    path: str
    message: str
    severity: Literal["error", "warning"] = "error"
    code: str | None = None


class GroundedArtifactValidationResult(BaseModel):
    """Validation result for any grounded artifact."""

    artifact_type: str
    is_valid: bool
    issues: list[GroundedArtifactValidationIssue] = Field(default_factory=list)
    diagnostics: dict[str, Any] = Field(default_factory=dict)


class GroundedClassificationArtifact(BaseModel):
    """Prediction contract for abstention-aware classification."""

    label: str | None = None
    confidence: float | None = None
    abstained: bool = False
    routed_to_review: bool = False
    parser_failed: bool = False
    scores: dict[str, float] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


def normalize_classification_artifact(
    value: Any,
    *,
    label_field: str | None = None,
    confidence_field: str = "confidence",
    abstain_field: str | None = None,
    review_route_field: str | None = None,
    scores_field: str | None = None,
    parser_failed_field: str = "parser_failed",
    abstain_values: Sequence[Any] | None = None,
) -> GroundedClassificationArtifact:
    """Coerce a classification payload into a typed artifact."""

    abstain_tokens = {canonical_label_value(item) for item in abstain_values or []}
    if isinstance(value, GroundedClassificationArtifact):
        artifact = value
    elif isinstance(value, Mapping):
        label_value = value.get(label_field) if label_field else value.get("label")
        confidence_value = value.get(confidence_field)
        routed_value = (
            value.get(review_route_field)
            if review_route_field is not None
            else value.get("routed_to_review", value.get("route_to_review", False))
        )
        abstained_value = (
            value.get(abstain_field)
            if abstain_field is not None
            else value.get("abstained", False)
        )
        scores_raw = (
            value.get(scores_field) if scores_field else value.get("scores", {})
        )
        scores = {
            str(key): float(parsed)
            for key, raw in dict(scores_raw or {}).items()
            if (parsed := _extract_float(raw)) is not None
        }
        artifact = GroundedClassificationArtifact(
            label=None if label_value is None else str(label_value),
            confidence=_extract_float(confidence_value),
            abstained=bool(abstained_value),
            routed_to_review=bool(routed_value),
            parser_failed=bool(value.get(parser_failed_field)),
            scores=scores,
            metadata={
                key: raw
                for key, raw in value.items()
                if key
                not in {
                    label_field,
                    confidence_field,
                    abstain_field,
                    review_route_field,
                    scores_field,
                    parser_failed_field,
                    "label",
                    "confidence",
                    "abstained",
                    "routed_to_review",
                    "route_to_review",
                    "scores",
                }
            },
        )
    elif value is None:
        artifact = GroundedClassificationArtifact()
    else:
        artifact = GroundedClassificationArtifact(label=str(value))

    if (
        artifact.label is not None
        and canonical_label_value(artifact.label) in abstain_tokens
    ):
        artifact.abstained = True
        artifact.label = None
    return artifact


def build_classification_diagnostics(
    *,
    predictions: Mapping[str, Mapping[str, Any]],
    gold: Mapping[str, Mapping[str, Any]],
    label_field: str,
    confidence_field: str = "confidence",
    abstain_field: str | None = None,
    review_route_field: str | None = None,
    review_required_field: str | None = None,
    abstain_gold_field: str | None = None,
    abstain_values: Sequence[Any] | None = None,
    low_confidence_threshold: float = 0.5,
    calibration_bin_count: int = 5,
) -> dict[str, Any]:
    """Build reusable calibration, abstention, and routing diagnostics."""

    rows: list[tuple[str, GroundedClassificationArtifact, Any, bool, bool]] = []
    for record_id, gold_labels in gold.items():
        predicted_artifact = normalize_classification_artifact(
            predictions.get(record_id, {}),
            label_field=label_field,
            confidence_field=confidence_field,
            abstain_field=abstain_field,
            review_route_field=review_route_field,
            abstain_values=abstain_values,
        )
        gold_value = gold_labels.get(label_field)
        gold_requires_review = False
        if review_required_field:
            gold_requires_review = bool(gold_labels.get(review_required_field))
        gold_should_abstain = False
        if abstain_gold_field:
            gold_should_abstain = bool(gold_labels.get(abstain_gold_field))
        rows.append(
            (
                str(record_id),
                predicted_artifact,
                gold_value,
                gold_requires_review,
                gold_should_abstain,
            )
        )

    total_records = len(rows)
    answered_rows = [row for row in rows if not row[1].abstained]
    answered_correct = sum(
        int(normalize_answer_text(row[1].label) == normalize_answer_text(row[2]))
        for row in answered_rows
    )
    abstain_rows = [row for row in rows if row[1].abstained]
    routed_rows = [row for row in rows if row[1].routed_to_review or row[1].abstained]

    confidence_rows = [
        row for row in rows if row[1].confidence is not None and not row[1].abstained
    ]
    sorted_confidence_rows = sorted(
        confidence_rows,
        key=lambda item: float(item[1].confidence or 0.0),
        reverse=True,
    )
    selective_curve: list[dict[str, Any]] = []
    if sorted_confidence_rows:
        running_correct = 0
        for index, row in enumerate(sorted_confidence_rows, start=1):
            running_correct += int(
                normalize_answer_text(row[1].label) == normalize_answer_text(row[2])
            )
            coverage = _safe_ratio(index, total_records)
            risk = 1.0 - _safe_ratio(running_correct, index)
            selective_curve.append(
                {
                    "coverage": coverage,
                    "risk": risk,
                    "threshold": float(row[1].confidence or 0.0),
                    "answered_count": index,
                }
            )

    calibration_bins: list[dict[str, Any]] = []
    ece = 0.0
    if confidence_rows:
        for bin_index in range(calibration_bin_count):
            start = bin_index / calibration_bin_count
            end = (bin_index + 1) / calibration_bin_count
            bin_rows = [
                row
                for row in confidence_rows
                if start <= float(row[1].confidence or 0.0) < end
                or (bin_index == calibration_bin_count - 1 and row[1].confidence == 1.0)
            ]
            if not bin_rows:
                continue
            mean_confidence = _mean(
                [float(row[1].confidence or 0.0) for row in bin_rows]
            )
            accuracy = _safe_ratio(
                sum(
                    int(
                        normalize_answer_text(row[1].label)
                        == normalize_answer_text(row[2])
                    )
                    for row in bin_rows
                ),
                len(bin_rows),
            )
            gap = abs(mean_confidence - accuracy)
            ece += gap * _safe_ratio(len(bin_rows), len(confidence_rows))
            calibration_bins.append(
                {
                    "start": start,
                    "end": end,
                    "count": len(bin_rows),
                    "mean_confidence": mean_confidence,
                    "accuracy": accuracy,
                    "gap": gap,
                }
            )

    low_confidence_rows = [
        row
        for row in rows
        if row[1].confidence is not None
        and float(row[1].confidence or 0.0) <= low_confidence_threshold
    ]
    incorrect_rows = [
        row
        for row in rows
        if normalize_answer_text(row[1].label) != normalize_answer_text(row[2])
    ]
    routed_low_confidence = sum(
        int(row[1].routed_to_review or row[1].abstained) for row in low_confidence_rows
    )
    incorrect_routed = sum(
        int(row[1].routed_to_review or row[1].abstained) for row in incorrect_rows
    )
    review_required_total = sum(int(row[3]) for row in rows)
    review_required_routed = sum(
        int(row[3] and (row[1].routed_to_review or row[1].abstained)) for row in rows
    )
    gold_abstain_total = sum(int(row[4]) for row in rows)
    gold_abstain_predicted = sum(int(row[4] and row[1].abstained) for row in rows)

    return {
        "record_count": total_records,
        "answered_count": len(answered_rows),
        "answered_accuracy": _safe_ratio(answered_correct, len(answered_rows)),
        "coverage_rate": _safe_ratio(len(answered_rows), total_records),
        "abstain_count": len(abstain_rows),
        "abstain_rate": _safe_ratio(len(abstain_rows), total_records),
        "abstain_precision": _safe_ratio(gold_abstain_predicted, len(abstain_rows)),
        "abstain_recall": _safe_ratio(gold_abstain_predicted, gold_abstain_total),
        "calibration_available": bool(confidence_rows),
        "expected_calibration_error": ece,
        "calibration_bins": calibration_bins,
        "selective_curve": selective_curve,
        "low_confidence_threshold": low_confidence_threshold,
        "low_confidence_count": len(low_confidence_rows),
        "low_confidence_routed_count": routed_low_confidence,
        "low_confidence_routed_rate": _safe_ratio(
            routed_low_confidence, len(low_confidence_rows)
        ),
        "incorrect_count": len(incorrect_rows),
        "incorrect_routed_count": incorrect_routed,
        "incorrect_capture_recall": _safe_ratio(incorrect_routed, len(incorrect_rows)),
        "routed_count": len(routed_rows),
        "review_routing_precision": _safe_ratio(
            review_required_routed, len(routed_rows)
        ),
        "review_routing_recall": _safe_ratio(
            review_required_routed, review_required_total
        ),
    }


class GroundedLabelSetArtifact(BaseModel):
    """Multi-label prediction with explicit parser-failure state."""

    labels: list[str] = Field(default_factory=list)
    scores: dict[str, float] = Field(default_factory=dict)
    parser_failed: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


def normalize_label_set_artifact(value: Any) -> GroundedLabelSetArtifact:
    """Normalize a multi-label payload into labels plus score metadata."""

    if isinstance(value, GroundedLabelSetArtifact):
        return value
    if value is None:
        return GroundedLabelSetArtifact()
    if isinstance(value, Mapping):
        labels_raw = value.get("labels")
        scores_raw = value.get("scores")
        if labels_raw is None and "label_scores" in value:
            scores_raw = value.get("label_scores")
        labels = []
        if isinstance(labels_raw, (list, set, tuple)):
            labels = [str(item) for item in labels_raw]
        elif labels_raw not in {None, ""}:
            labels = [str(labels_raw)]
        scores = {
            str(key): float(parsed)
            for key, raw in dict(scores_raw or {}).items()
            if (parsed := _extract_float(raw)) is not None
        }
        return GroundedLabelSetArtifact(
            labels=labels,
            scores=scores,
            parser_failed=bool(value.get("parser_failed")),
            metadata={
                key: raw
                for key, raw in value.items()
                if key not in {"labels", "scores", "label_scores", "parser_failed"}
            },
        )
    if isinstance(value, (list, set, tuple)):
        return GroundedLabelSetArtifact(labels=[str(item) for item in value])
    return GroundedLabelSetArtifact(labels=[str(value)])


def validate_label_hierarchy(
    labels: Sequence[str],
    hierarchy: Mapping[str, Sequence[str]],
) -> GroundedArtifactValidationResult:
    """Validate parent-child label hierarchy constraints."""

    label_set = {str(label) for label in labels}
    issues: list[GroundedArtifactValidationIssue] = []
    for child, parents in hierarchy.items():
        if child not in label_set:
            continue
        missing_parents = sorted(
            parent for parent in parents if parent not in label_set
        )
        if missing_parents:
            issues.append(
                GroundedArtifactValidationIssue(
                    path=f"labels.{child}",
                    message=(
                        "Missing required parent labels: " + ", ".join(missing_parents)
                    ),
                    code="missing_parent_label",
                )
            )
    return GroundedArtifactValidationResult(
        artifact_type="label_hierarchy",
        is_valid=not issues,
        issues=issues,
        diagnostics={"label_count": len(label_set)},
    )


def threshold_label_scores(
    scores: Mapping[str, Any],
    *,
    threshold: float,
    hierarchy: Mapping[str, Sequence[str]] | None = None,
) -> list[str]:
    """Convert label scores into a thresholded label set."""

    labels = sorted(
        str(label)
        for label, raw in scores.items()
        if (parsed := _extract_float(raw)) is not None and parsed >= threshold
    )
    if hierarchy:
        expanded = set(labels)
        for child, parents in hierarchy.items():
            if child in expanded:
                expanded.update(str(parent) for parent in parents)
        labels = sorted(expanded)
    return labels


def sweep_label_thresholds(
    *,
    gold_artifacts: Mapping[str, GroundedLabelSetArtifact],
    predicted_artifacts: Mapping[str, GroundedLabelSetArtifact],
    thresholds: Sequence[float],
    hierarchy: Mapping[str, Sequence[str]] | None = None,
) -> list[dict[str, Any]]:
    """Evaluate micro-F1 over a threshold sweep."""

    results: list[dict[str, Any]] = []
    for threshold in thresholds:
        thresholded_predictions = {
            record_id: GroundedLabelSetArtifact(
                labels=threshold_label_scores(
                    artifact.scores,
                    threshold=threshold,
                    hierarchy=hierarchy,
                )
                if artifact.scores
                else list(dict.fromkeys(artifact.labels)),
                scores=artifact.scores,
                parser_failed=artifact.parser_failed,
                metadata=dict(artifact.metadata),
            )
            for record_id, artifact in predicted_artifacts.items()
        }
        score = score_multilabel_micro_f1(
            predictions=thresholded_predictions,
            gold=gold_artifacts,
        )
        results.append(
            {
                "threshold": threshold,
                "micro_f1": score["value"],
                "details": score["details"],
            }
        )
    return results


def validate_label_set_artifact(
    artifact: GroundedLabelSetArtifact,
    *,
    vocabulary: Sequence[str] | None = None,
    hierarchy: Mapping[str, Sequence[str]] | None = None,
) -> GroundedArtifactValidationResult:
    """Validate duplicate labels, vocabulary, and hierarchy."""

    issues: list[GroundedArtifactValidationIssue] = []
    duplicates = sorted(
        label for label, count in Counter(artifact.labels).items() if count > 1
    )
    for label in duplicates:
        issues.append(
            GroundedArtifactValidationIssue(
                path="labels",
                message=f"Duplicate label: {label}",
                code="duplicate_label",
            )
        )
    if vocabulary is not None:
        vocab = {str(label) for label in vocabulary}
        invalid = sorted(label for label in artifact.labels if label not in vocab)
        for label in invalid:
            issues.append(
                GroundedArtifactValidationIssue(
                    path="labels",
                    message=f"Unknown label: {label}",
                    code="unknown_label",
                )
            )
    if hierarchy:
        issues.extend(validate_label_hierarchy(artifact.labels, hierarchy).issues)
    return GroundedArtifactValidationResult(
        artifact_type="label_set",
        is_valid=not any(issue.severity == "error" for issue in issues),
        issues=issues,
        diagnostics={
            "parser_failed": artifact.parser_failed,
            "label_count": len(set(artifact.labels)),
            "empty_label_set": not artifact.labels and not artifact.parser_failed,
        },
    )


def score_multilabel_micro_f1(
    *,
    predictions: Mapping[str, GroundedLabelSetArtifact],
    gold: Mapping[str, GroundedLabelSetArtifact],
) -> dict[str, Any]:
    """Score micro-F1 over multi-label predictions."""

    tp = 0
    fp = 0
    fn = 0
    parser_failure_count = 0
    valid_empty_count = 0
    for record_id, gold_artifact in gold.items():
        predicted_artifact = predictions.get(record_id, GroundedLabelSetArtifact())
        gold_set = set(gold_artifact.labels)
        predicted_set = set(predicted_artifact.labels)
        if predicted_artifact.parser_failed:
            parser_failure_count += 1
        elif not predicted_set:
            valid_empty_count += 1
        tp += len(gold_set & predicted_set)
        fp += len(predicted_set - gold_set)
        fn += len(gold_set - predicted_set)
    precision = _safe_ratio(tp, tp + fp)
    recall = _safe_ratio(tp, tp + fn)
    return {
        "value": _safe_ratio(2 * precision * recall, precision + recall),
        "details": {
            "true_positive": tp,
            "false_positive": fp,
            "false_negative": fn,
            "precision": precision,
            "recall": recall,
            "parser_failure_count": parser_failure_count,
            "valid_empty_count": valid_empty_count,
        },
    }


class GroundedDocumentAnchor(BaseModel):
    """Hierarchical anchor into a document source."""

    anchor_type: Literal["document"] = "document"
    document_id: str
    page_number: int | None = None
    section_path: list[str] = Field(default_factory=list)
    paragraph_id: str | None = None
    sentence_id: str | None = None
    text: str | None = None
    lossless: bool = True
    warning: str | None = None


class GroundedTableCellAnchor(BaseModel):
    """Stable table-cell grounding anchor."""

    anchor_type: Literal["table_cell"] = "table_cell"
    document_id: str
    table_id: str
    row_id: str
    column_id: str
    page_number: int | None = None
    section_path: list[str] = Field(default_factory=list)
    cell_text: str | None = None
    lossless: bool = True
    warning: str | None = None


GroundedAnchor = GroundedDocumentAnchor | GroundedTableCellAnchor


def normalize_grounded_anchor(value: Any) -> GroundedAnchor:
    """Coerce a document/table anchor payload into a typed anchor."""

    if isinstance(value, (GroundedDocumentAnchor, GroundedTableCellAnchor)):
        return value
    if not isinstance(value, Mapping):
        return GroundedDocumentAnchor(document_id=str(value))
    anchor_type = value.get("anchor_type", "document")
    if anchor_type == "table_cell":
        return GroundedTableCellAnchor.model_validate(value)
    return GroundedDocumentAnchor.model_validate(value)


def validate_grounded_anchor(value: Any) -> GroundedArtifactValidationResult:
    """Validate document/table grounding anchors and surface lossy warnings."""

    anchor = normalize_grounded_anchor(value)
    issues: list[GroundedArtifactValidationIssue] = []
    if isinstance(anchor, GroundedDocumentAnchor) and not anchor.document_id:
        issues.append(
            GroundedArtifactValidationIssue(
                path="document_id",
                message="Document anchors require document_id",
                code="missing_document_id",
            )
        )
    if isinstance(anchor, GroundedTableCellAnchor):
        for key in ("document_id", "table_id", "row_id", "column_id"):
            if not getattr(anchor, key):
                issues.append(
                    GroundedArtifactValidationIssue(
                        path=key,
                        message=f"Table-cell anchors require {key}",
                        code=f"missing_{key}",
                    )
                )
    if not anchor.lossless or anchor.warning:
        issues.append(
            GroundedArtifactValidationIssue(
                path="anchor",
                message=anchor.warning or "Grounding could not be preserved losslessly",
                severity="warning",
                code="lossy_grounding",
            )
        )
    return GroundedArtifactValidationResult(
        artifact_type="grounding_anchor",
        is_valid=not any(issue.severity == "error" for issue in issues),
        issues=issues,
        diagnostics={"anchor_type": anchor.anchor_type},
    )


class GroundedEvidenceGroup(BaseModel):
    """One acceptable bundle of evidence atoms or anchors."""

    group_id: str | None = None
    atoms: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _sort_atoms(self) -> GroundedEvidenceGroup:
        self.atoms = [str(atom) for atom in self.atoms]
        return self


class GroundedEvidenceAnnotation(BaseModel):
    """Grouped evidence output with optional decision label."""

    decision: str | None = None
    groups: list[GroundedEvidenceGroup] = Field(default_factory=list)
    faithfulness_score: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class GroundedFaithfulnessResult(BaseModel):
    """Reusable faithfulness hook return value."""

    score: float
    details: dict[str, Any] = Field(default_factory=dict)


class GroundedFaithfulnessHook(Protocol):
    """Protocol for rationale/evidence faithfulness evaluators."""

    def evaluate(
        self,
        *,
        prediction: Any,
        gold: Any,
        context: dict[str, Any] | None = None,
    ) -> GroundedFaithfulnessResult: ...


def normalize_evidence_annotation(value: Any) -> GroundedEvidenceAnnotation:
    """Normalize flat or grouped evidence payloads."""

    if isinstance(value, GroundedEvidenceAnnotation):
        return value
    if value is None:
        return GroundedEvidenceAnnotation()
    if isinstance(value, Mapping):
        groups_raw = value.get("groups")
        if groups_raw is None and "evidence_groups" in value:
            groups_raw = value.get("evidence_groups")
        if groups_raw is None and "evidence_atoms" in value:
            groups_raw = [{"atoms": list(value.get("evidence_atoms") or [])}]
        groups = []
        for index, group in enumerate(groups_raw or []):
            if isinstance(group, Mapping):
                groups.append(
                    GroundedEvidenceGroup(
                        group_id=(
                            None
                            if group.get("group_id") is None
                            else str(group["group_id"])
                        ),
                        atoms=[str(atom) for atom in group.get("atoms", [])],
                    )
                )
            elif isinstance(group, (list, set, tuple)):
                groups.append(
                    GroundedEvidenceGroup(
                        group_id=f"group-{index}",
                        atoms=[str(atom) for atom in group],
                    )
                )
            else:
                groups.append(
                    GroundedEvidenceGroup(group_id=f"group-{index}", atoms=[str(group)])
                )
        return GroundedEvidenceAnnotation(
            decision=(
                None
                if value.get("decision", value.get("verdict")) is None
                else str(value.get("decision", value.get("verdict")))
            ),
            groups=groups,
            faithfulness_score=_extract_float(value.get("faithfulness_score")),
            metadata={
                key: raw
                for key, raw in value.items()
                if key
                not in {
                    "decision",
                    "verdict",
                    "groups",
                    "evidence_groups",
                    "evidence_atoms",
                    "faithfulness_score",
                }
            },
        )
    if isinstance(value, (list, set, tuple)):
        return GroundedEvidenceAnnotation(
            groups=[
                GroundedEvidenceGroup(
                    group_id="group-0", atoms=[str(item) for item in value]
                )
            ]
        )
    return GroundedEvidenceAnnotation(
        groups=[GroundedEvidenceGroup(group_id="group-0", atoms=[str(value)])]
    )


def validate_evidence_annotation(
    value: Any,
) -> GroundedArtifactValidationResult:
    """Validate grouped evidence completeness and integrity."""

    artifact = normalize_evidence_annotation(value)
    issues: list[GroundedArtifactValidationIssue] = []
    for index, group in enumerate(artifact.groups):
        if not group.atoms:
            issues.append(
                GroundedArtifactValidationIssue(
                    path=f"groups.{index}",
                    message="Evidence groups must not be empty",
                    code="empty_evidence_group",
                )
            )
        duplicates = [atom for atom, count in Counter(group.atoms).items() if count > 1]
        for atom in duplicates:
            issues.append(
                GroundedArtifactValidationIssue(
                    path=f"groups.{index}.atoms",
                    message=f"Duplicate evidence atom: {atom}",
                    code="duplicate_evidence_atom",
                )
            )
    return GroundedArtifactValidationResult(
        artifact_type="evidence_annotation",
        is_valid=not any(issue.severity == "error" for issue in issues),
        issues=issues,
        diagnostics={
            "group_count": len(artifact.groups),
            "atom_count": sum(len(group.atoms) for group in artifact.groups),
        },
    )


def score_grouped_evidence(
    *,
    prediction: GroundedEvidenceAnnotation,
    gold: GroundedEvidenceAnnotation,
) -> dict[str, Any]:
    """Score grouped evidence against multiple acceptable gold groups."""

    if not gold.groups:
        return {
            "precision": 1.0 if not prediction.groups else 0.0,
            "recall": 1.0 if not prediction.groups else 0.0,
            "f1": 1.0 if not prediction.groups else 0.0,
            "exact_match": float(not prediction.groups),
            "completeness": float(not prediction.groups),
            "integrity_ok": validate_evidence_annotation(prediction).is_valid,
            "matched_gold_group_id": None,
        }

    best_precision = 0.0
    best_recall = 0.0
    best_f1 = 0.0
    best_exact = 0.0
    best_complete = 0.0
    matched_gold_group_id: str | None = None
    for gold_group in gold.groups:
        gold_atoms = set(gold_group.atoms)
        for predicted_group in prediction.groups or [GroundedEvidenceGroup(atoms=[])]:
            predicted_atoms = set(predicted_group.atoms)
            overlap = len(gold_atoms & predicted_atoms)
            precision = _safe_ratio(overlap, len(predicted_atoms))
            recall = _safe_ratio(overlap, len(gold_atoms))
            f1 = _safe_ratio(2 * precision * recall, precision + recall)
            exact = float(predicted_atoms == gold_atoms)
            complete = float(gold_atoms.issubset(predicted_atoms))
            if (f1, recall, precision, exact) > (
                best_f1,
                best_recall,
                best_precision,
                best_exact,
            ):
                best_precision = precision
                best_recall = recall
                best_f1 = f1
                best_exact = exact
                best_complete = complete
                matched_gold_group_id = gold_group.group_id

    return {
        "precision": best_precision,
        "recall": best_recall,
        "f1": best_f1,
        "exact_match": best_exact,
        "completeness": best_complete,
        "integrity_ok": validate_evidence_annotation(prediction).is_valid,
        "matched_gold_group_id": matched_gold_group_id,
    }


class GroundedSupportingFact(BaseModel):
    """A canonical supporting-fact reference for QA-with-evidence."""

    document_id: str
    fact_id: str


class GroundedQaWithEvidenceArtifact(BaseModel):
    """Answer plus supporting-facts bundle."""

    answer: str | None = None
    acceptable_answers: list[str] = Field(default_factory=list)
    supporting_facts: list[GroundedSupportingFact] = Field(default_factory=list)
    unanswerable: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


def _normalize_supporting_fact(value: Any) -> GroundedSupportingFact:
    if isinstance(value, GroundedSupportingFact):
        return value
    if isinstance(value, Mapping):
        return GroundedSupportingFact(
            document_id=str(value.get("document_id", value.get("page_id", ""))),
            fact_id=str(
                value.get("fact_id", value.get("sentence_id", value.get("id", "")))
            ),
        )
    if isinstance(value, str) and "::" in value:
        document_id, fact_id = value.split("::", 1)
        return GroundedSupportingFact(document_id=document_id, fact_id=fact_id)
    return GroundedSupportingFact(document_id="default", fact_id=str(value))


def normalize_qa_with_evidence_artifact(value: Any) -> GroundedQaWithEvidenceArtifact:
    """Normalize answer + supporting-facts payloads."""

    if isinstance(value, GroundedQaWithEvidenceArtifact):
        return value
    if value is None:
        return GroundedQaWithEvidenceArtifact()
    if isinstance(value, Mapping):
        acceptable_answers = value.get("acceptable_answers")
        if acceptable_answers is None and value.get("answers") is not None:
            acceptable_answers = value.get("answers")
        return GroundedQaWithEvidenceArtifact(
            answer=None if value.get("answer") is None else str(value.get("answer")),
            acceptable_answers=[str(item) for item in acceptable_answers or []],
            supporting_facts=[
                _normalize_supporting_fact(item)
                for item in value.get("supporting_facts", value.get("evidence", []))
                or []
            ],
            unanswerable=bool(value.get("unanswerable", value.get("is_null", False))),
            metadata={
                key: raw
                for key, raw in value.items()
                if key
                not in {
                    "answer",
                    "acceptable_answers",
                    "answers",
                    "supporting_facts",
                    "evidence",
                    "unanswerable",
                    "is_null",
                }
            },
        )
    return GroundedQaWithEvidenceArtifact(answer=str(value))


def supporting_fact_exact_match(predicted: Any, gold: Any) -> float:
    """Exact match over supporting fact sets."""

    predicted_artifact = normalize_qa_with_evidence_artifact(predicted)
    gold_artifact = normalize_qa_with_evidence_artifact(gold)
    predicted_set = {
        (fact.document_id, fact.fact_id) for fact in predicted_artifact.supporting_facts
    }
    gold_set = {
        (fact.document_id, fact.fact_id) for fact in gold_artifact.supporting_facts
    }
    return float(predicted_set == gold_set)


def supporting_fact_f1(predicted: Any, gold: Any) -> float:
    """Set F1 over supporting facts."""

    predicted_artifact = normalize_qa_with_evidence_artifact(predicted)
    gold_artifact = normalize_qa_with_evidence_artifact(gold)
    predicted_set = {
        (fact.document_id, fact.fact_id) for fact in predicted_artifact.supporting_facts
    }
    gold_set = {
        (fact.document_id, fact.fact_id) for fact in gold_artifact.supporting_facts
    }
    if not predicted_set and not gold_set:
        return 1.0
    overlap = len(predicted_set & gold_set)
    precision = _safe_ratio(overlap, len(predicted_set))
    recall = _safe_ratio(overlap, len(gold_set))
    return _safe_ratio(2 * precision * recall, precision + recall)


def score_qa_with_evidence(predicted: Any, gold: Any) -> dict[str, Any]:
    """Score answer quality, evidence quality, and their joint behavior."""

    predicted_artifact = normalize_qa_with_evidence_artifact(predicted)
    gold_artifact = normalize_qa_with_evidence_artifact(gold)

    acceptable_answers = gold_artifact.acceptable_answers or (
        [gold_artifact.answer] if gold_artifact.answer is not None else []
    )
    if gold_artifact.unanswerable:
        answer_em = float(predicted_artifact.unanswerable)
        answer_f1_value = answer_em
    else:
        answer_em = max(
            (
                answer_exact_match(predicted_artifact.answer, answer)
                for answer in acceptable_answers
            ),
            default=0.0,
        )
        answer_f1_value = max(
            (
                answer_token_f1(predicted_artifact.answer, answer)
                for answer in acceptable_answers
            ),
            default=0.0,
        )
    support_em = supporting_fact_exact_match(predicted_artifact, gold_artifact)
    support_f1_value = supporting_fact_f1(predicted_artifact, gold_artifact)
    return {
        "answer_exact_match": answer_em,
        "answer_token_f1": answer_f1_value,
        "supporting_fact_exact_match": support_em,
        "supporting_fact_f1": support_f1_value,
        "joint_exact_match": answer_em * support_em,
        "joint_f1": answer_f1_value * support_f1_value,
        "unanswerable_gold": gold_artifact.unanswerable,
        "unanswerable_predicted": predicted_artifact.unanswerable,
    }


class GroundedRankedResult(BaseModel):
    """One ranked retrieval result."""

    result_id: str
    score: float | None = None
    rank: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class GroundedRankingArtifact(BaseModel):
    """Ranked retrieval output plus reproducibility metadata."""

    results: list[GroundedRankedResult] = Field(default_factory=list)
    expected_depth: int | None = None
    corpus_snapshot_id: str | None = None
    corpus_hash: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class GroundedQrelsArtifact(BaseModel):
    """Canonical qrels structure."""

    qrels: dict[str, float] = Field(default_factory=dict)


def normalize_ranking_artifact(value: Any) -> GroundedRankingArtifact:
    """Normalize ranked results into a typed ranking artifact."""

    if isinstance(value, GroundedRankingArtifact):
        return value
    if value is None:
        return GroundedRankingArtifact()
    if isinstance(value, Mapping):
        results_raw = value.get("results", value.get("ranking", []))
        results: list[GroundedRankedResult] = []
        for index, item in enumerate(results_raw or []):
            if isinstance(item, Mapping):
                results.append(
                    GroundedRankedResult(
                        result_id=str(
                            item.get("result_id", item.get("doc_id", item.get("id")))
                        ),
                        score=_extract_float(item.get("score")),
                        rank=(
                            int(item.get("rank"))
                            if item.get("rank") is not None
                            else index + 1
                        ),
                        metadata={
                            key: raw
                            for key, raw in item.items()
                            if key not in {"result_id", "doc_id", "id", "score", "rank"}
                        },
                    )
                )
            else:
                results.append(
                    GroundedRankedResult(result_id=str(item), rank=index + 1)
                )
        return GroundedRankingArtifact(
            results=results,
            expected_depth=(
                int(value["expected_depth"])
                if value.get("expected_depth") is not None
                else None
            ),
            corpus_snapshot_id=(
                None
                if value.get("corpus_snapshot_id") is None
                else str(value.get("corpus_snapshot_id"))
            ),
            corpus_hash=(
                None
                if value.get("corpus_hash") is None
                else str(value.get("corpus_hash"))
            ),
            metadata={
                key: raw
                for key, raw in value.items()
                if key
                not in {
                    "results",
                    "ranking",
                    "expected_depth",
                    "corpus_snapshot_id",
                    "corpus_hash",
                }
            },
        )
    if isinstance(value, (list, tuple)):
        return GroundedRankingArtifact(
            results=[
                GroundedRankedResult(result_id=str(item), rank=index + 1)
                for index, item in enumerate(value)
            ]
        )
    return GroundedRankingArtifact(
        results=[GroundedRankedResult(result_id=str(value), rank=1)]
    )


def ingest_qrels(value: Any) -> GroundedQrelsArtifact:
    """Normalize qrels from mappings or list-like relevance payloads."""

    if isinstance(value, GroundedQrelsArtifact):
        return value
    if value is None:
        return GroundedQrelsArtifact()
    if isinstance(value, Mapping):
        if "qrels" in value:
            return ingest_qrels(value["qrels"])
        return GroundedQrelsArtifact(
            qrels={
                str(result_id): float(parsed)
                for result_id, raw in value.items()
                if (parsed := _extract_float(raw)) is not None
            }
        )
    qrels: dict[str, float] = {}
    for item in value:
        if isinstance(item, Mapping):
            result_id = str(item.get("result_id", item.get("doc_id", item.get("id"))))
            relevance = _extract_float(item.get("relevance", item.get("score", 1.0)))
            qrels[result_id] = 1.0 if relevance is None else float(relevance)
        else:
            qrels[str(item)] = 1.0
    return GroundedQrelsArtifact(qrels=qrels)


def validate_grounded_ranking_artifact(
    value: Any,
    *,
    fixed_depth: int | None = None,
    require_corpus_metadata: bool = False,
) -> GroundedArtifactValidationResult:
    """Validate duplicates, depth, and reproducibility metadata for rankings."""

    artifact = normalize_ranking_artifact(value)
    issues: list[GroundedArtifactValidationIssue] = []
    ids = [result.result_id for result in artifact.results]
    duplicates = sorted(
        result_id for result_id, count in Counter(ids).items() if count > 1
    )
    for result_id in duplicates:
        issues.append(
            GroundedArtifactValidationIssue(
                path="results",
                message=f"Duplicate ranked result id: {result_id}",
                code="duplicate_result_id",
            )
        )
    expected_depth = fixed_depth if fixed_depth is not None else artifact.expected_depth
    if expected_depth is not None and len(artifact.results) != expected_depth:
        issues.append(
            GroundedArtifactValidationIssue(
                path="results",
                message=(
                    "Ranking depth "
                    f"{len(artifact.results)} does not match expected "
                    f"{expected_depth}"
                ),
                code="unexpected_ranking_depth",
            )
        )
    if require_corpus_metadata:
        if not artifact.corpus_snapshot_id:
            issues.append(
                GroundedArtifactValidationIssue(
                    path="corpus_snapshot_id",
                    message="Missing corpus snapshot metadata",
                    severity="warning",
                    code="missing_corpus_snapshot",
                )
            )
        if not artifact.corpus_hash:
            issues.append(
                GroundedArtifactValidationIssue(
                    path="corpus_hash",
                    message="Missing corpus hash metadata",
                    severity="warning",
                    code="missing_corpus_hash",
                )
            )
    return GroundedArtifactValidationResult(
        artifact_type="ranking",
        is_valid=not any(issue.severity == "error" for issue in issues),
        issues=issues,
        diagnostics={
            "result_count": len(artifact.results),
            "has_corpus_snapshot_id": bool(artifact.corpus_snapshot_id),
            "has_corpus_hash": bool(artifact.corpus_hash),
        },
    )


def score_ranking(
    *,
    prediction: GroundedRankingArtifact,
    qrels: GroundedQrelsArtifact,
    metric_type: Literal["mrr", "ndcg_at_k", "recall_at_k", "precision_at_k", "map"],
    k: int | None = None,
) -> dict[str, Any]:
    """Score one ranking prediction against qrels."""

    relevant = {
        result_id: score
        for result_id, score in qrels.qrels.items()
        if float(score) > 0.0
    }
    ranked_ids = [result.result_id for result in prediction.results]
    if k is not None:
        ranked_ids = ranked_ids[:k]
    if metric_type == "mrr":
        reciprocal_rank = 0.0
        for index, result_id in enumerate(ranked_ids, start=1):
            if result_id in relevant:
                reciprocal_rank = 1.0 / index
                break
        return {
            "value": reciprocal_rank,
            "details": {"relevant_count": len(relevant), "cutoff": k},
        }
    if metric_type == "recall_at_k":
        hits = sum(int(result_id in relevant) for result_id in ranked_ids)
        return {
            "value": _safe_ratio(hits, len(relevant)),
            "details": {"hits": hits, "relevant_count": len(relevant), "cutoff": k},
        }
    if metric_type == "precision_at_k":
        hits = sum(int(result_id in relevant) for result_id in ranked_ids)
        return {
            "value": _safe_ratio(hits, len(ranked_ids)),
            "details": {"hits": hits, "cutoff": k, "returned_count": len(ranked_ids)},
        }
    if metric_type == "map":
        running_hits = 0
        precision_sum = 0.0
        for index, result_id in enumerate(ranked_ids, start=1):
            if result_id not in relevant:
                continue
            running_hits += 1
            precision_sum += running_hits / index
        return {
            "value": _safe_ratio(precision_sum, len(relevant)),
            "details": {"relevant_count": len(relevant), "cutoff": k},
        }

    dcg = 0.0
    for index, result_id in enumerate(ranked_ids, start=1):
        relevance = relevant.get(result_id, 0.0)
        if relevance <= 0.0:
            continue
        dcg += (2**relevance - 1) / math.log2(index + 1)
    ideal_scores = sorted(relevant.values(), reverse=True)
    if k is not None:
        ideal_scores = ideal_scores[:k]
    idcg = sum(
        (2**score - 1) / math.log2(index + 1)
        for index, score in enumerate(ideal_scores, start=1)
    )
    return {
        "value": _safe_ratio(dcg, idcg),
        "details": {"dcg": dcg, "idcg": idcg, "cutoff": k},
    }


class GroundedSpanSegment(BaseModel):
    """One contiguous character/token span segment."""

    char_start: int | None = None
    char_end: int | None = None
    token_start: int | None = None
    token_end: int | None = None
    text: str | None = None


class GroundedSpan(BaseModel):
    """One extraction span that may be discontiguous."""

    span_id: str | None = None
    segments: list[GroundedSpanSegment] = Field(default_factory=list)
    normalized_value: str | None = None


class GroundedSpanAnnotation(BaseModel):
    """Span-native extraction artifact."""

    source_text: str | None = None
    source_tokens: list[str] = Field(default_factory=list)
    spans: list[GroundedSpan] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


def normalize_span_annotation(value: Any) -> GroundedSpanAnnotation:
    """Normalize contiguous or discontiguous span payloads."""

    if isinstance(value, GroundedSpanAnnotation):
        return value
    if value is None:
        return GroundedSpanAnnotation()
    if isinstance(value, Mapping):
        spans_raw = value.get("spans", [])
        spans: list[GroundedSpan] = []
        for index, span_value in enumerate(spans_raw):
            if isinstance(span_value, Mapping):
                segments_raw = span_value.get("segments")
                if segments_raw is None:
                    segments_raw = [span_value]
                spans.append(
                    GroundedSpan(
                        span_id=(
                            None
                            if span_value.get("span_id") is None
                            else str(span_value.get("span_id"))
                        ),
                        segments=[
                            GroundedSpanSegment.model_validate(segment)
                            for segment in segments_raw
                        ],
                        normalized_value=(
                            None
                            if span_value.get("normalized_value") is None
                            else str(span_value.get("normalized_value"))
                        ),
                    )
                )
            else:
                spans.append(
                    GroundedSpan(
                        span_id=f"span-{index}",
                        segments=[GroundedSpanSegment(text=str(span_value))],
                    )
                )
        return GroundedSpanAnnotation(
            source_text=(
                None
                if value.get("source_text") is None
                else str(value.get("source_text"))
            ),
            source_tokens=[
                str(token) for token in value.get("source_tokens", []) or []
            ],
            spans=spans,
            metadata={
                key: raw
                for key, raw in value.items()
                if key not in {"source_text", "source_tokens", "spans"}
            },
        )
    if isinstance(value, (list, tuple)):
        return normalize_span_annotation({"spans": list(value)})
    return GroundedSpanAnnotation(
        spans=[
            GroundedSpan(
                span_id="span-0", segments=[GroundedSpanSegment(text=str(value))]
            )
        ]
    )


def _segment_char_positions(segment: GroundedSpanSegment) -> set[int]:
    if segment.char_start is None or segment.char_end is None:
        return set()
    return set(range(segment.char_start, segment.char_end))


def _segment_token_positions(segment: GroundedSpanSegment) -> set[int]:
    if segment.token_start is None or segment.token_end is None:
        return set()
    return set(range(segment.token_start, segment.token_end))


def validate_span_annotation(value: Any) -> GroundedArtifactValidationResult:
    """Validate offsets resolve into source text/tokens and ordering is stable."""

    artifact = normalize_span_annotation(value)
    issues: list[GroundedArtifactValidationIssue] = []
    for span_index, span in enumerate(artifact.spans):
        previous_end = -1
        previous_token_end = -1
        for segment_index, segment in enumerate(span.segments):
            path = f"spans.{span_index}.segments.{segment_index}"
            if (
                segment.char_start is not None
                and segment.char_end is not None
                and segment.char_end <= segment.char_start
            ):
                issues.append(
                    GroundedArtifactValidationIssue(
                        path=path,
                        message="Character offsets must satisfy end > start",
                        code="invalid_char_offsets",
                    )
                )
            if (
                segment.token_start is not None
                and segment.token_end is not None
                and segment.token_end <= segment.token_start
            ):
                issues.append(
                    GroundedArtifactValidationIssue(
                        path=path,
                        message="Token offsets must satisfy end > start",
                        code="invalid_token_offsets",
                    )
                )
            if (
                segment.char_start is not None
                and segment.char_end is not None
                and artifact.source_text is not None
                and (
                    segment.char_start < 0
                    or segment.char_end > len(artifact.source_text)
                )
            ):
                issues.append(
                    GroundedArtifactValidationIssue(
                        path=path,
                        message="Character offsets do not resolve into source text",
                        code="char_offsets_out_of_range",
                    )
                )
            if (
                segment.token_start is not None
                and segment.token_end is not None
                and artifact.source_tokens
                and (
                    segment.token_start < 0
                    or segment.token_end > len(artifact.source_tokens)
                )
            ):
                issues.append(
                    GroundedArtifactValidationIssue(
                        path=path,
                        message="Token offsets do not resolve into source tokens",
                        code="token_offsets_out_of_range",
                    )
                )
            if segment.char_start is not None and segment.char_start < previous_end:
                issues.append(
                    GroundedArtifactValidationIssue(
                        path=path,
                        message="Span segments must be ordered and non-overlapping",
                        code="unordered_char_segments",
                    )
                )
            if (
                segment.token_start is not None
                and segment.token_start < previous_token_end
            ):
                issues.append(
                    GroundedArtifactValidationIssue(
                        path=path,
                        message="Token segments must be ordered and non-overlapping",
                        code="unordered_token_segments",
                    )
                )
            if segment.char_end is not None:
                previous_end = segment.char_end
            if segment.token_end is not None:
                previous_token_end = segment.token_end
    return GroundedArtifactValidationResult(
        artifact_type="span_annotation",
        is_valid=not any(issue.severity == "error" for issue in issues),
        issues=issues,
        diagnostics={"span_count": len(artifact.spans)},
    )


def score_span_exact_match(predicted: Any, gold: Any) -> float:
    """Exact match over normalized multi-span outputs."""

    predicted_artifact = normalize_span_annotation(predicted)
    gold_artifact = normalize_span_annotation(gold)
    predicted_value = canonical_label_value(predicted_artifact.model_dump(mode="json"))
    gold_value = canonical_label_value(gold_artifact.model_dump(mode="json"))
    return float(predicted_value == gold_value)


def score_span_overlap_f1(predicted: Any, gold: Any) -> float:
    """Partial-overlap span F1 using char offsets when available, else token offsets."""

    predicted_artifact = normalize_span_annotation(predicted)
    gold_artifact = normalize_span_annotation(gold)
    predicted_positions: set[int] = set()
    gold_positions: set[int] = set()
    predicted_token_positions: set[int] = set()
    gold_token_positions: set[int] = set()
    for span in predicted_artifact.spans:
        for segment in span.segments:
            predicted_positions.update(_segment_char_positions(segment))
            predicted_token_positions.update(_segment_token_positions(segment))
    for span in gold_artifact.spans:
        for segment in span.segments:
            gold_positions.update(_segment_char_positions(segment))
            gold_token_positions.update(_segment_token_positions(segment))
    if predicted_positions or gold_positions:
        overlap = len(predicted_positions & gold_positions)
        precision = _safe_ratio(overlap, len(predicted_positions))
        recall = _safe_ratio(overlap, len(gold_positions))
        return _safe_ratio(2 * precision * recall, precision + recall)
    overlap = len(predicted_token_positions & gold_token_positions)
    precision = _safe_ratio(overlap, len(predicted_token_positions))
    recall = _safe_ratio(overlap, len(gold_token_positions))
    if precision or recall:
        return _safe_ratio(2 * precision * recall, precision + recall)
    predicted_values = {
        normalize_answer_text(span.normalized_value or segment.text or "")
        for span in predicted_artifact.spans
        for segment in span.segments
    }
    gold_values = {
        normalize_answer_text(span.normalized_value or segment.text or "")
        for span in gold_artifact.spans
        for segment in span.segments
    }
    overlap = len(predicted_values & gold_values)
    precision = _safe_ratio(overlap, len(predicted_values))
    recall = _safe_ratio(overlap, len(gold_values))
    return _safe_ratio(2 * precision * recall, precision + recall)


class GroundedGenerationClaim(BaseModel):
    """One grounded generation claim or content unit."""

    claim_id: str | None = None
    text: str
    anchor_ids: list[str] = Field(default_factory=list)


class GroundedGenerationArtifact(BaseModel):
    """Grounded generation output with claim-level grounding."""

    text: str = ""
    claims: list[GroundedGenerationClaim] = Field(default_factory=list)
    structured_output: dict[str, Any] = Field(default_factory=dict)
    available_anchor_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


def normalize_grounded_generation_artifact(value: Any) -> GroundedGenerationArtifact:
    """Normalize grounded generation payloads."""

    if isinstance(value, GroundedGenerationArtifact):
        return value
    if value is None:
        return GroundedGenerationArtifact()
    if isinstance(value, Mapping):
        return GroundedGenerationArtifact(
            text=str(value.get("text", "")),
            claims=[
                GroundedGenerationClaim(
                    claim_id=(
                        None
                        if claim.get("claim_id") is None
                        else str(claim.get("claim_id"))
                    ),
                    text=str(claim.get("text", "")),
                    anchor_ids=[
                        str(item) for item in claim.get("anchor_ids", []) or []
                    ],
                )
                for claim in value.get("claims", []) or []
            ],
            structured_output=dict(value.get("structured_output", {}) or {}),
            available_anchor_ids=[
                str(item) for item in value.get("available_anchor_ids", []) or []
            ],
            metadata={
                key: raw
                for key, raw in value.items()
                if key
                not in {"text", "claims", "structured_output", "available_anchor_ids"}
            },
        )
    return GroundedGenerationArtifact(text=str(value))


def validate_grounded_generation_artifact(
    value: Any,
    *,
    required_fields: Sequence[str] | None = None,
) -> GroundedArtifactValidationResult:
    """Validate grounded generation structure and unsupported content."""

    artifact = normalize_grounded_generation_artifact(value)
    issues: list[GroundedArtifactValidationIssue] = []
    known_anchor_ids = set(artifact.available_anchor_ids)
    for index, claim in enumerate(artifact.claims):
        if not claim.text.strip():
            issues.append(
                GroundedArtifactValidationIssue(
                    path=f"claims.{index}.text",
                    message="Claims must contain text",
                    code="empty_claim",
                )
            )
        for anchor_id in claim.anchor_ids:
            if known_anchor_ids and anchor_id not in known_anchor_ids:
                issues.append(
                    GroundedArtifactValidationIssue(
                        path=f"claims.{index}.anchor_ids",
                        message=f"Unknown anchor id: {anchor_id}",
                        code="unknown_anchor_id",
                    )
                )
    for field_name in required_fields or []:
        if field_name not in artifact.structured_output:
            issues.append(
                GroundedArtifactValidationIssue(
                    path=f"structured_output.{field_name}",
                    message=f"Missing required structured field: {field_name}",
                    code="missing_required_field",
                )
            )
    return GroundedArtifactValidationResult(
        artifact_type="grounded_generation",
        is_valid=not any(issue.severity == "error" for issue in issues),
        issues=issues,
        diagnostics={
            "claim_count": len(artifact.claims),
            "available_anchor_count": len(artifact.available_anchor_ids),
        },
    )


def score_grounded_generation(
    predicted: Any,
    gold: Any,
    *,
    required_fields: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Score grounded generation using source coverage and unsupported-content rate."""

    predicted_artifact = normalize_grounded_generation_artifact(predicted)
    gold_artifact = normalize_grounded_generation_artifact(gold)
    validation = validate_grounded_generation_artifact(
        predicted_artifact,
        required_fields=required_fields,
    )
    gold_claim_keys = {
        claim.claim_id or normalize_answer_text(claim.text)
        for claim in gold_artifact.claims
    }
    predicted_claim_keys = {
        claim.claim_id or normalize_answer_text(claim.text)
        for claim in predicted_artifact.claims
    }
    covered_gold_claims = len(gold_claim_keys & predicted_claim_keys)
    unsupported_claims = [
        claim
        for claim in predicted_artifact.claims
        if not claim.anchor_ids
        or (
            predicted_artifact.available_anchor_ids
            and any(
                anchor_id not in set(predicted_artifact.available_anchor_ids)
                for anchor_id in claim.anchor_ids
            )
        )
    ]
    source_coverage = _safe_ratio(covered_gold_claims, len(gold_claim_keys))
    unsupported_rate = _safe_ratio(
        len(unsupported_claims), len(predicted_artifact.claims)
    )
    grounded_score = (source_coverage + (1.0 - unsupported_rate)) / 2.0
    if not validation.is_valid:
        grounded_score = min(grounded_score, 0.0)
    return {
        "source_coverage": source_coverage,
        "unsupported_content_rate": unsupported_rate,
        "grounded_generation_score": grounded_score,
        "validation": validation.model_dump(mode="json"),
    }


def score_anls(predicted: Any, gold: Any, *, threshold: float = 0.5) -> float:
    """Compute the DocVQA-style ANLS score."""

    predicted_text = normalize_answer_text(predicted)
    gold_text = normalize_answer_text(gold)
    if not predicted_text and not gold_text:
        return 1.0
    if not predicted_text or not gold_text:
        return 0.0

    rows = len(predicted_text) + 1
    cols = len(gold_text) + 1
    distance = [[0] * cols for _ in range(rows)]
    for row in range(rows):
        distance[row][0] = row
    for col in range(cols):
        distance[0][col] = col
    for row in range(1, rows):
        for col in range(1, cols):
            substitution_cost = (
                0 if predicted_text[row - 1] == gold_text[col - 1] else 1
            )
            distance[row][col] = min(
                distance[row - 1][col] + 1,
                distance[row][col - 1] + 1,
                distance[row - 1][col - 1] + substitution_cost,
            )
    normalized_distance = _safe_ratio(
        distance[-1][-1], max(len(predicted_text), len(gold_text))
    )
    similarity = 1.0 - normalized_distance
    return similarity if similarity >= threshold else 0.0
