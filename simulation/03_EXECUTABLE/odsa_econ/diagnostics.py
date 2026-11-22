from __future__ import annotations

import itertools
import math
from typing import Iterable, Mapping, Sequence

import numpy as np


def definition_rate(state_values: Sequence[float], state_index: Mapping[str, int], positive_states: Iterable[str]) -> float:
    indices = [state_index[str(state)] for state in positive_states]
    return float(np.asarray(state_values, dtype=float)[indices].sum())


def rate_bounds(observed_state_weight: Sequence[float], unresolved_weight: float, state_index: Mapping[str, int], positive_states: Iterable[str]) -> tuple[float, float, float]:
    observed = np.asarray(observed_state_weight, dtype=float)
    denominator_complete = float(observed.sum())
    total = denominator_complete + float(unresolved_weight)
    positive = definition_rate(observed, state_index, positive_states)
    complete_case = positive / denominator_complete if denominator_complete > 0 else float("nan")
    if total <= 0:
        return float("nan"), float("nan"), complete_case
    return positive / total, (positive + float(unresolved_weight)) / total, complete_case


def threshold_action(values: Mapping[str, float], threshold: float, direction: str) -> set[str]:
    if direction == "above_or_equal":
        return {unit for unit, value in values.items() if math.isfinite(value) and value >= threshold}
    if direction == "below":
        return {unit for unit, value in values.items() if math.isfinite(value) and value < threshold}
    raise ValueError(f"unknown threshold direction {direction!r}")


def _ordered_units(values: Mapping[str, float], direction: str) -> list[str]:
    finite = [(str(unit), float(value)) for unit, value in values.items() if math.isfinite(float(value))]
    if direction == "highest":
        return [unit for unit, _ in sorted(finite, key=lambda item: (-item[1], item[0]))]
    if direction == "lowest":
        return [unit for unit, _ in sorted(finite, key=lambda item: (item[1], item[0]))]
    raise ValueError(f"unknown top-k direction {direction!r}")


def top_k_action(values: Mapping[str, float], k: int, direction: str) -> tuple[set[str], bool]:
    if k <= 0:
        raise ValueError("k must be positive")
    ordered = _ordered_units(values, direction)
    selected = set(ordered[: min(k, len(ordered))])
    finite_values = {str(unit): float(value) for unit, value in values.items() if math.isfinite(float(value))}
    boundary_tie = False
    if 0 < k < len(ordered):
        boundary_tie = math.isclose(
            finite_values[ordered[k - 1]], finite_values[ordered[k]], rel_tol=0.0, abs_tol=1e-15
        )
    return selected, boundary_tie


def action_loss(selected: set[str], benchmark: set[str], false_inclusion_cost: float, false_exclusion_cost: float, denominator: int | None = None) -> dict[str, float]:
    fp = len(selected - benchmark)
    fn = len(benchmark - selected)
    scale = float(denominator if denominator is not None else max(len(selected | benchmark), 1))
    return {
        "false_inclusion_count": float(fp),
        "false_exclusion_count": float(fn),
        "false_inclusion_share": fp / scale,
        "false_exclusion_share": fn / scale,
        "cost_weighted_loss": (false_inclusion_cost * fp + false_exclusion_cost * fn) / scale,
        "symmetric_difference_share": len(selected ^ benchmark) / scale,
        "jaccard_overlap": 1.0 if not (selected | benchmark) else len(selected & benchmark) / len(selected | benchmark),
    }


def semantic_loss(probabilities: np.ndarray, state_names: Sequence[str], definition_states: Iterable[str], objective_states: Iterable[str], false_inclusion_cost: float, false_exclusion_cost: float) -> dict[str, float]:
    index = {state: i for i, state in enumerate(state_names)}
    d = set(map(str, definition_states))
    q = set(map(str, objective_states))
    fp_states = d - q
    fn_states = q - d
    fp = float(sum(probabilities[:, index[state]].sum() for state in fp_states) / probabilities.shape[0]) if fp_states else 0.0
    fn = float(sum(probabilities[:, index[state]].sum() for state in fn_states) / probabilities.shape[0]) if fn_states else 0.0
    return {
        "false_inclusion_mass": fp,
        "false_exclusion_mass": fn,
        "cost_weighted_semantic_loss": false_inclusion_cost * fp + false_exclusion_cost * fn,
    }


def pairwise_reversal_share(left: Mapping[str, float], right: Mapping[str, float], tolerance: float = 1e-15) -> dict[str, float]:
    units = sorted(set(left) & set(right))
    total = 0
    strict_reversal = 0
    disagreement = 0
    for a, b in itertools.combinations(units, 2):
        ld = left[a] - left[b]
        rd = right[a] - right[b]
        if not (math.isfinite(ld) and math.isfinite(rd)):
            continue
        total += 1
        ls = 0 if abs(ld) <= tolerance else 1 if ld > 0 else -1
        rs = 0 if abs(rd) <= tolerance else 1 if rd > 0 else -1
        if ls != rs:
            disagreement += 1
        if ls * rs == -1:
            strict_reversal += 1
    return {
        "eligible_pairs": float(total),
        "disagreement_share": disagreement / total if total else float("nan"),
        "strict_reversal_share": strict_reversal / total if total else float("nan"),
    }


def interval_order_determinacy(bounds: Mapping[str, tuple[float, float]]) -> dict[str, float]:
    units = sorted(bounds)
    total = 0
    determinate = 0
    overlap = 0
    for a, b in itertools.combinations(units, 2):
        la, ua = bounds[a]
        lb, ub = bounds[b]
        if not all(math.isfinite(x) for x in (la, ua, lb, ub)):
            continue
        total += 1
        if la > ub or lb > ua:
            determinate += 1
        else:
            overlap += 1
    return {
        "eligible_pairs": float(total),
        "determinate_pairs": float(determinate),
        "overlapping_pairs": float(overlap),
        "determinate_share": determinate / total if total else float("nan"),
    }


def threshold_interval_classification(bounds: Mapping[str, tuple[float, float]], threshold: float, direction: str) -> dict[str, set[str]]:
    definite: set[str] = set()
    definite_not: set[str] = set()
    ambiguous: set[str] = set()
    for unit, (lower, upper) in bounds.items():
        if direction == "above_or_equal":
            if lower >= threshold:
                definite.add(unit)
            elif upper < threshold:
                definite_not.add(unit)
            else:
                ambiguous.add(unit)
        elif direction == "below":
            if upper < threshold:
                definite.add(unit)
            elif lower >= threshold:
                definite_not.add(unit)
            else:
                ambiguous.add(unit)
        else:
            raise ValueError(f"unknown threshold direction {direction!r}")
    return {"definite": definite, "definite_not": definite_not, "ambiguous": ambiguous}


def interval_top_k_membership(bounds: Mapping[str, tuple[float, float]], k: int, direction: str) -> dict[str, set[str]]:
    if k <= 0:
        raise ValueError("k must be positive")
    guaranteed: set[str] = set()
    possible: set[str] = set()
    for unit, (lower, upper) in bounds.items():
        if direction == "highest":
            definitely_above = sum(1 for other, (_, other_upper) in bounds.items() if other != unit and other_upper >= lower)
            certainly_above = sum(1 for other, (other_lower, _) in bounds.items() if other != unit and other_lower > upper)
        elif direction == "lowest":
            definitely_above = sum(1 for other, (other_lower, _) in bounds.items() if other != unit and other_lower <= upper)
            certainly_above = sum(1 for other, (_, other_upper) in bounds.items() if other != unit and other_upper < lower)
        else:
            raise ValueError(f"unknown top-k direction {direction!r}")
        if definitely_above <= k - 1:
            guaranteed.add(unit)
        if certainly_above <= k - 1:
            possible.add(unit)
    return {"guaranteed": guaranteed, "possible": possible, "ambiguous": possible - guaranteed}


def set_churn(left: set[str], right: set[str], k: int | None = None) -> dict[str, float]:
    denominator = float(k if k is not None else max(len(left), len(right), 1))
    return {
        "entry_count": float(len(right - left)),
        "exit_count": float(len(left - right)),
        "symmetric_difference_share": len(left ^ right) / denominator,
        "churn": 1.0 - len(left & right) / denominator,
        "jaccard_overlap": 1.0 if not (left | right) else len(left & right) / len(left | right),
    }
