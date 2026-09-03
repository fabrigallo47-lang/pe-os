"""Credential-free metrics shared across benchmark adapters."""

from __future__ import annotations

import json
import math
import re
import unicodedata
from collections import Counter
from typing import Any, Iterable, Mapping, Sequence


def normalize_text(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value if value is not None else ""))
    text = text.casefold().replace("\u00a0", " ")
    return " ".join(text.split())


def normalize_semantic_label(value: Any) -> str:
    """Normalize presentation differences without guessing domain synonyms."""
    text = normalize_text(value).replace("_", " ")
    text = re.sub(r"[^\w]+", " ", text, flags=re.UNICODE)
    return " ".join(text.split())


def _numeric(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return float(value)
    text = normalize_text(value)
    text = re.sub(r"(?:eur|usd|gbp|chf|\$|€|£)", "", text).strip()
    text = text.replace(" ", "")
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif re.fullmatch(r"[-+]?\d{1,3}(?:,\d{3})*(?:\.\d+)?", text):
        text = text.replace(",", "")
    elif re.fullmatch(r"[-+]?\d+(?:[.,]\d+)?", text):
        text = text.replace(",", ".")
    else:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def values_equal(expected: Any, actual: Any, *, tolerance: float = 1e-6) -> bool:
    if expected is None or actual is None:
        return expected is actual
    if isinstance(expected, bool) or isinstance(actual, bool):
        return expected is actual
    expected_number, actual_number = _numeric(expected), _numeric(actual)
    if expected_number is not None and actual_number is not None:
        return math.isclose(expected_number, actual_number, rel_tol=tolerance, abs_tol=tolerance)
    return normalize_text(expected) == normalize_text(actual)


def tokenize(value: Any) -> list[str]:
    return re.findall(r"\w+", normalize_text(value), flags=re.UNICODE)


def token_f1(expected: Any, actual: Any) -> float:
    gold, predicted = Counter(tokenize(expected)), Counter(tokenize(actual))
    if not gold and not predicted:
        return 1.0
    if not gold or not predicted:
        return 0.0
    overlap = sum((gold & predicted).values())
    if overlap == 0:
        return 0.0
    precision = overlap / sum(predicted.values())
    recall = overlap / sum(gold.values())
    return 2 * precision * recall / (precision + recall)


def _ngram_f1(expected: Any, actual: Any, size: int) -> float:
    def ngrams(value: Any) -> Counter[tuple[str, ...]]:
        tokens = tokenize(value)
        return Counter(tuple(tokens[index:index + size]) for index in range(len(tokens) - size + 1))

    gold, predicted = ngrams(expected), ngrams(actual)
    if not gold and not predicted:
        return 1.0
    if not gold or not predicted:
        return 0.0
    overlap = sum((gold & predicted).values())
    precision = overlap / sum(predicted.values())
    recall = overlap / sum(gold.values())
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


def _lcs_length(left: Sequence[str], right: Sequence[str]) -> int:
    if len(left) < len(right):
        left, right = right, left
    previous = [0] * (len(right) + 1)
    for left_token in left:
        current = [0]
        for index, right_token in enumerate(right, start=1):
            current.append(
                previous[index - 1] + 1
                if left_token == right_token
                else max(previous[index], current[-1])
            )
        previous = current
    return previous[-1]


def rouge_n(case: Mapping[str, Any], prediction: Mapping[str, Any], size: int) -> float:
    actual = prediction.get("answer", "")
    return max(
        (_ngram_f1(candidate, actual, size) for candidate in answer_candidates(case["gold"])),
        default=0.0,
    )


def rouge_l(case: Mapping[str, Any], prediction: Mapping[str, Any]) -> float:
    predicted = tokenize(prediction.get("answer", ""))
    scores = []
    for candidate in answer_candidates(case["gold"]):
        expected = tokenize(candidate)
        if not expected and not predicted:
            scores.append(1.0)
            continue
        if not expected or not predicted:
            scores.append(0.0)
            continue
        common = _lcs_length(expected, predicted)
        precision, recall = common / len(predicted), common / len(expected)
        scores.append(2 * precision * recall / (precision + recall))
    return max(scores, default=0.0)


def levenshtein_distance(left: str, right: str) -> int:
    if len(left) < len(right):
        left, right = right, left
    previous = list(range(len(right) + 1))
    for i, left_char in enumerate(left, start=1):
        current = [i]
        for j, right_char in enumerate(right, start=1):
            current.append(min(
                current[-1] + 1,
                previous[j] + 1,
                previous[j - 1] + (left_char != right_char),
            ))
        previous = current
    return previous[-1]


def normalized_edit_similarity(expected: Any, actual: Any) -> float:
    left, right = normalize_text(expected), normalize_text(actual)
    if not left and not right:
        return 1.0
    denominator = max(len(left), len(right))
    return 1.0 - levenshtein_distance(left, right) / denominator if denominator else 1.0


def answer_candidates(gold: Mapping[str, Any]) -> list[Any]:
    if "answers" in gold:
        return list(gold["answers"])
    if "answer" in gold:
        return [gold["answer"]]
    if gold.get("unanswerable"):
        return [""]
    return []


def answer_exact_match(case: Mapping[str, Any], prediction: Mapping[str, Any]) -> float:
    actual = prediction.get("answer")
    candidates = answer_candidates(case["gold"])
    if not candidates:
        return 0.0
    return float(any(values_equal(candidate, actual) for candidate in candidates))


def answer_f1(case: Mapping[str, Any], prediction: Mapping[str, Any]) -> float:
    actual = prediction.get("answer")
    candidates = answer_candidates(case["gold"])
    if not candidates:
        assertions = case["gold"].get("assertions", [])
        candidates = [item.get("text") if isinstance(item, Mapping) else item for item in assertions]
    return max((token_f1(candidate, actual) for candidate in candidates), default=0.0)


def anls(case: Mapping[str, Any], prediction: Mapping[str, Any]) -> float:
    actual = prediction.get("answer")
    similarities = [normalized_edit_similarity(candidate, actual)
                    for candidate in answer_candidates(case["gold"])]
    best = max(similarities, default=0.0)
    return best if best >= 0.5 else 0.0


def _flatten(value: Any, prefix: str = "$") -> list[tuple[str, Any]]:
    if isinstance(value, Mapping):
        out: list[tuple[str, Any]] = []
        for key in sorted(value):
            out.extend(_flatten(value[key], f"{prefix}.{key}"))
        return out
    if isinstance(value, list):
        out = []
        for index, item in enumerate(value):
            out.extend(_flatten(item, f"{prefix}[{index}]"))
        return out
    return [(prefix, value)]


def structured_accuracy(case: Mapping[str, Any], prediction: Mapping[str, Any]) -> float:
    expected = case["gold"].get("answer")
    actual = prediction.get("answer")
    if expected is None:
        return answer_exact_match(case, prediction)
    expected_items = _flatten(expected)
    actual_map = dict(_flatten(actual))
    if not expected_items:
        return float(not actual_map)
    return sum(values_equal(value, actual_map.get(path)) for path, value in expected_items) / len(expected_items)


def assertion_recall(case: Mapping[str, Any], prediction: Mapping[str, Any]) -> float:
    assertions = case["gold"].get("assertions", [])
    if not assertions:
        return 0.0
    actual = prediction.get("answer")
    rendered = actual if isinstance(actual, str) else json.dumps(actual, ensure_ascii=False, sort_keys=True)
    normalized_answer = normalize_text(rendered)
    earned = total = 0.0
    for item in assertions:
        if isinstance(item, Mapping):
            text = item["text"]
            weight = float(item.get("weight", 1.0))
        else:
            text, weight = str(item), 1.0
        total += weight
        normalized_assertion = normalize_text(text)
        if normalized_assertion and normalized_assertion in normalized_answer:
            earned += weight
        elif token_f1(text, rendered) >= 0.75:
            earned += weight
    return earned / total if total else 0.0


def _bbox(locator: Mapping[str, Any] | None) -> list[float] | None:
    raw = (locator or {}).get("bbox")
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)) or len(raw) != 4:
        return None
    try:
        return [float(value) for value in raw]
    except (TypeError, ValueError):
        return None


def bbox_iou(left: Sequence[float], right: Sequence[float]) -> float:
    left_x1, left_y1, left_x2, left_y2 = left
    right_x1, right_y1, right_x2, right_y2 = right
    intersection_width = max(0.0, min(left_x2, right_x2) - max(left_x1, right_x1))
    intersection_height = max(0.0, min(left_y2, right_y2) - max(left_y1, right_y1))
    intersection = intersection_width * intersection_height
    left_area = max(0.0, left_x2 - left_x1) * max(0.0, left_y2 - left_y1)
    right_area = max(0.0, right_x2 - right_x1) * max(0.0, right_y2 - right_y1)
    union = left_area + right_area - intersection
    return intersection / union if union else float(left_area == right_area == 0)


def locator_matches(expected: Mapping[str, Any], actual: Mapping[str, Any], *, iou_threshold: float = 0.5) -> bool:
    if expected.get("type") != actual.get("type"):
        return False
    ignored = {"bbox", "index_base"}
    for key, value in expected.items():
        if key not in ignored and actual.get(key) != value:
            return False
    expected_bbox, actual_bbox = _bbox(expected), _bbox(actual)
    if expected_bbox is not None:
        return actual_bbox is not None and bbox_iou(expected_bbox, actual_bbox) >= iou_threshold
    return True


def _field_name(field: Mapping[str, Any]) -> str:
    return normalize_text(field.get("field_type") or field.get("name") or "")


def _field_value(field: Mapping[str, Any]) -> Any:
    return field.get("value", field.get("text"))


def field_match(expected: Mapping[str, Any], actual: Mapping[str, Any]) -> bool:
    if _field_name(expected) != _field_name(actual):
        return False
    if not values_equal(_field_value(expected), _field_value(actual)):
        return False
    if expected.get("line_item_id") is not None and expected.get("line_item_id") != actual.get("line_item_id"):
        return False
    expected_locator = expected.get("locator")
    if expected_locator:
        actual_locator = actual.get("locator")
        return isinstance(actual_locator, Mapping) and locator_matches(expected_locator, actual_locator)
    return True


def _greedy_matches(expected: Sequence[Mapping[str, Any]], actual: Sequence[Mapping[str, Any]], matcher: Any) -> int:
    remaining = set(range(len(actual)))
    matched = 0
    for gold_item in expected:
        for index in sorted(remaining):
            if matcher(gold_item, actual[index]):
                matched += 1
                remaining.remove(index)
                break
    return matched


def field_counts(case: Mapping[str, Any], prediction: Mapping[str, Any]) -> tuple[int, int, int]:
    expected = [item for item in case["gold"].get("fields", []) if isinstance(item, Mapping)]
    actual = [item for item in prediction.get("fields", []) if isinstance(item, Mapping)]
    return _greedy_matches(expected, actual, field_match), len(expected), len(actual)


def field_precision(case: Mapping[str, Any], prediction: Mapping[str, Any]) -> float:
    matched, _, predicted = field_counts(case, prediction)
    return matched / predicted if predicted else float(not case["gold"].get("fields"))


def field_recall(case: Mapping[str, Any], prediction: Mapping[str, Any]) -> float:
    matched, expected, _ = field_counts(case, prediction)
    return matched / expected if expected else 1.0


def field_f1(case: Mapping[str, Any], prediction: Mapping[str, Any]) -> float:
    precision, recall = field_precision(case, prediction), field_recall(case, prediction)
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


def _fact_items(container: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """Use explicit facts when supplied, otherwise project legacy fields to facts."""
    key = "facts" if "facts" in container else "fields"
    return [item for item in container.get(key, []) if isinstance(item, Mapping)]


def _fact_concepts(fact: Mapping[str, Any]) -> set[str]:
    raw = [
        fact.get("fact_id"), fact.get("concept_id"), fact.get("predicate"),
        fact.get("field_type"), fact.get("name"),
    ]
    aliases = fact.get("aliases", [])
    if isinstance(aliases, Sequence) and not isinstance(aliases, (str, bytes)):
        raw.extend(aliases)
    return {normalized for value in raw if value is not None
            if (normalized := normalize_semantic_label(value))}


def _fact_locator_matches(expected: Mapping[str, Any], actual: Mapping[str, Any]) -> bool:
    expected_locator, actual_locator = expected.get("locator"), actual.get("locator")
    if not isinstance(expected_locator, Mapping) or not isinstance(actual_locator, Mapping):
        return False
    if expected.get("input_id") is not None and actual.get("input_id") != expected.get("input_id"):
        return False
    return locator_matches(expected_locator, actual_locator)


def _fact_qualifier_pairs(
    expected: Mapping[str, Any], actual: Mapping[str, Any],
) -> list[tuple[Any, Any, bool]]:
    pairs: list[tuple[Any, Any, bool]] = []
    for key in ("subject", "unit", "line_item_id"):
        if expected.get(key) is not None:
            semantic = key in {"subject", "unit"}
            pairs.append((expected[key], actual.get(key), semantic))
    expected_qualifiers = expected.get("qualifiers", {})
    actual_qualifiers = actual.get("qualifiers", {})
    if isinstance(expected_qualifiers, Mapping):
        actual_map = actual_qualifiers if isinstance(actual_qualifiers, Mapping) else {}
        flattened_actual = dict(_flatten(actual_map, "$"))
        for path, value in _flatten(expected_qualifiers, "$"):
            pairs.append((value, flattened_actual.get(path), False))
    return pairs


def _fact_qualifier_score(expected: Mapping[str, Any], actual: Mapping[str, Any]) -> float:
    pairs = _fact_qualifier_pairs(expected, actual)
    if not pairs:
        return 1.0
    correct = 0
    for expected_value, actual_value, semantic in pairs:
        if semantic:
            correct += normalize_semantic_label(expected_value) == normalize_semantic_label(actual_value)
        else:
            correct += values_equal(expected_value, actual_value)
    return correct / len(pairs)


def _fact_identity_score(expected: Mapping[str, Any], actual: Mapping[str, Any]) -> float | None:
    expected_subject = normalize_semantic_label(expected.get("subject"))
    actual_subject = normalize_semantic_label(actual.get("subject"))
    subjects_compatible = not expected_subject or not actual_subject or expected_subject == actual_subject
    concept_match = bool(_fact_concepts(expected) & _fact_concepts(actual)) and subjects_compatible
    locator_match = _fact_locator_matches(expected, actual)
    if not concept_match and not locator_match:
        return None

    # Matching is based on semantic identity or source position. Value and
    # qualifiers only break ties between repeated concepts; their correctness is
    # measured separately below.
    score = 100.0 if concept_match else 60.0
    if locator_match:
        score += 30.0
    if values_equal(_field_value(expected), _field_value(actual)):
        score += 5.0
    score += _fact_qualifier_score(expected, actual)
    return score


def _fact_alignment(
    expected: Sequence[Mapping[str, Any]], actual: Sequence[Mapping[str, Any]],
) -> dict[int, int]:
    """Return a deterministic maximum-cardinality semantic alignment."""
    candidates: dict[int, list[tuple[int, float]]] = {}
    for expected_index, expected_fact in enumerate(expected):
        edges = []
        for actual_index, actual_fact in enumerate(actual):
            score = _fact_identity_score(expected_fact, actual_fact)
            if score is not None:
                edges.append((actual_index, score))
        candidates[expected_index] = sorted(edges, key=lambda item: (-item[1], item[0]))

    actual_owner: dict[int, int] = {}

    def assign(expected_index: int, seen: set[int]) -> bool:
        for actual_index, _ in candidates[expected_index]:
            if actual_index in seen:
                continue
            seen.add(actual_index)
            previous = actual_owner.get(actual_index)
            if previous is None or assign(previous, seen):
                actual_owner[actual_index] = expected_index
                return True
        return False

    order = sorted(candidates, key=lambda index: (len(candidates[index]), index))
    for expected_index in order:
        assign(expected_index, set())
    return {expected_index: actual_index for actual_index, expected_index in actual_owner.items()}


def _aligned_facts(
    case: Mapping[str, Any], prediction: Mapping[str, Any],
) -> tuple[list[Mapping[str, Any]], list[Mapping[str, Any]], dict[int, int]]:
    expected = _fact_items(case["gold"])
    actual = _fact_items(prediction)
    return expected, actual, _fact_alignment(expected, actual)


def _fact_is_correct(expected: Mapping[str, Any], actual: Mapping[str, Any]) -> bool:
    return values_equal(_field_value(expected), _field_value(actual)) and math.isclose(
        _fact_qualifier_score(expected, actual), 1.0
    )


def information_recall(case: Mapping[str, Any], prediction: Mapping[str, Any]) -> float:
    """Recall of correctly extracted semantic facts, independent of output shape."""
    expected, actual, alignment = _aligned_facts(case, prediction)
    if not expected:
        return 1.0
    correct = sum(
        _fact_is_correct(expected[index], actual[actual_index])
        for index, actual_index in alignment.items()
    )
    return correct / len(expected)


def fact_value_accuracy(case: Mapping[str, Any], prediction: Mapping[str, Any]) -> float:
    expected, actual, alignment = _aligned_facts(case, prediction)
    if not expected:
        return 1.0
    if not alignment:
        return 0.0
    return sum(
        values_equal(_field_value(expected[index]), _field_value(actual[actual_index]))
        for index, actual_index in alignment.items()
    ) / len(alignment)


def fact_qualifier_accuracy(case: Mapping[str, Any], prediction: Mapping[str, Any]) -> float:
    expected, actual, alignment = _aligned_facts(case, prediction)
    if not expected:
        return 1.0
    if not alignment:
        return 0.0
    return sum(
        _fact_qualifier_score(expected[index], actual[actual_index])
        for index, actual_index in alignment.items()
    ) / len(alignment)


def fact_grounding_accuracy(case: Mapping[str, Any], prediction: Mapping[str, Any]) -> float:
    expected, actual, alignment = _aligned_facts(case, prediction)
    grounded = [
        index for index, fact in enumerate(expected)
        if fact.get("input_id") is not None or isinstance(fact.get("locator"), Mapping)
    ]
    if not grounded:
        return 1.0
    correct = 0
    for expected_index in grounded:
        actual_index = alignment.get(expected_index)
        if actual_index is None:
            continue
        expected_fact, actual_fact = expected[expected_index], actual[actual_index]
        input_matches = (
            expected_fact.get("input_id") is None
            or expected_fact.get("input_id") == actual_fact.get("input_id")
        )
        locator = expected_fact.get("locator")
        locator_ok = not isinstance(locator, Mapping) or _fact_locator_matches(expected_fact, actual_fact)
        correct += input_matches and locator_ok
    return correct / len(grounded)


def fact_precision(case: Mapping[str, Any], prediction: Mapping[str, Any]) -> float:
    expected, actual, alignment = _aligned_facts(case, prediction)
    correct = sum(
        _fact_is_correct(expected[index], actual[actual_index])
        for index, actual_index in alignment.items()
    )
    if case["gold"].get("coverage", "exhaustive") == "subset":
        # Unannotated facts are unknown, not false positives.
        return correct / len(alignment) if alignment else float(not expected)
    return correct / len(actual) if actual else float(not expected)


def fact_f1(case: Mapping[str, Any], prediction: Mapping[str, Any]) -> float:
    precision, recall = fact_precision(case, prediction), information_recall(case, prediction)
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


def evidence_f1(case: Mapping[str, Any], prediction: Mapping[str, Any]) -> float:
    expected = [item for item in case.get("evidence", []) if isinstance(item, Mapping)]
    actual = [item for item in prediction.get("evidence", []) if isinstance(item, Mapping)]

    def matches(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
        return left.get("input_id") == right.get("input_id") and locator_matches(
            left.get("locator", {}), right.get("locator", {})
        )

    matched = _greedy_matches(expected, actual, matches)
    precision = matched / len(actual) if actual else float(not expected)
    recall = matched / len(expected) if expected else 1.0
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


def content_similarity(case: Mapping[str, Any], prediction: Mapping[str, Any]) -> float:
    return normalized_edit_similarity(case["gold"].get("content", ""), prediction.get("content", ""))


def _element_match(expected: Mapping[str, Any], actual: Mapping[str, Any]) -> bool:
    if normalize_text(expected.get("type")) != normalize_text(actual.get("type")):
        return False
    expected_content = expected.get("text") or expected.get("html") or expected.get("latex") or ""
    actual_content = actual.get("text") or actual.get("html") or actual.get("latex") or ""
    if normalized_edit_similarity(expected_content, actual_content) < 0.8:
        return False
    locator = expected.get("locator")
    return not locator or (isinstance(actual.get("locator"), Mapping)
                           and locator_matches(locator, actual["locator"]))


def element_f1(case: Mapping[str, Any], prediction: Mapping[str, Any]) -> float:
    expected = [item for item in case["gold"].get("elements", []) if isinstance(item, Mapping)]
    actual = [item for item in prediction.get("elements", []) if isinstance(item, Mapping)]
    matched = _greedy_matches(expected, actual, _element_match)
    precision = matched / len(actual) if actual else float(not expected)
    recall = matched / len(expected) if expected else 1.0
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


def media_f1(case: Mapping[str, Any], prediction: Mapping[str, Any]) -> float:
    expected = case["gold"].get("media", [])
    actual = prediction.get("media", [])

    def matches(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
        left_type = normalize_text(left.get("media_type") or left.get("type"))
        right_type = normalize_text(right.get("media_type") or right.get("type"))
        if left_type != right_type:
            return False
        if left.get("locator"):
            return isinstance(right.get("locator"), Mapping) and locator_matches(left["locator"], right["locator"])
        return True

    matched = _greedy_matches(expected, actual, matches)
    precision = matched / len(actual) if actual else float(not expected)
    recall = matched / len(expected) if expected else 1.0
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


def status_accuracy(case: Mapping[str, Any], prediction: Mapping[str, Any]) -> float:
    expected = case["gold"].get("expected_status", "success")
    return float(expected == prediction.get("status"))


METRICS = {
    "answer_exact_match": answer_exact_match,
    "answer_f1": answer_f1,
    "rouge1": lambda case, prediction: rouge_n(case, prediction, 1),
    "rouge2": lambda case, prediction: rouge_n(case, prediction, 2),
    "rouge_l": rouge_l,
    "anls": anls,
    "structured_accuracy": structured_accuracy,
    "assertion_recall": assertion_recall,
    "field_precision": field_precision,
    "field_recall": field_recall,
    "field_f1": field_f1,
    "information_recall": information_recall,
    "fact_recall": information_recall,
    "fact_precision": fact_precision,
    "fact_f1": fact_f1,
    "fact_value_accuracy": fact_value_accuracy,
    "fact_qualifier_accuracy": fact_qualifier_accuracy,
    "fact_grounding_accuracy": fact_grounding_accuracy,
    "evidence_f1": evidence_f1,
    "content_similarity": content_similarity,
    "element_f1": element_f1,
    "media_f1": media_f1,
    "status_accuracy": status_accuracy,
}


def score_metric(name: str, case: Mapping[str, Any], prediction: Mapping[str, Any]) -> float | None:
    metric = METRICS.get(name)
    if metric is None:
        return None
    return max(0.0, min(1.0, float(metric(case, prediction))))
