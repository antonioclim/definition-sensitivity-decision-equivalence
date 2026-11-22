from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass(frozen=True)
class ObservedUnit:
    observed_counts: np.ndarray
    observed_weight: np.ndarray
    unresolved_count: int
    unresolved_weight: float
    true_count: int


def _gamma_weight_sum(count: int, coefficient_of_variation: float, rng: np.random.Generator) -> float:
    if count <= 0:
        return 0.0
    if coefficient_of_variation == 0:
        return float(count)
    shape_per_record = 1.0 / (coefficient_of_variation**2)
    scale = coefficient_of_variation**2
    return float(rng.gamma(shape=count * shape_per_record, scale=scale))


def simulate_observed_unit(
    probabilities: np.ndarray,
    sample_size: int,
    *,
    misclassification_matrix: np.ndarray,
    unresolved_probabilities: np.ndarray,
    weight_coefficient_of_variation: float,
    rng: np.random.Generator,
) -> ObservedUnit:
    true_counts = rng.multinomial(int(sample_size), probabilities)
    state_count = len(probabilities)
    observed_counts = np.zeros(state_count, dtype=int)
    observed_weight = np.zeros(state_count, dtype=float)
    unresolved_count = 0
    unresolved_weight = 0.0

    for true_state, true_count in enumerate(true_counts):
        unresolved = int(rng.binomial(int(true_count), float(unresolved_probabilities[true_state])))
        retained = int(true_count) - unresolved
        unresolved_count += unresolved
        unresolved_weight += _gamma_weight_sum(unresolved, weight_coefficient_of_variation, rng)
        if retained:
            flows = rng.multinomial(retained, misclassification_matrix[true_state])
            for observed_state, flow_count in enumerate(flows):
                observed_counts[observed_state] += int(flow_count)
                observed_weight[observed_state] += _gamma_weight_sum(
                    int(flow_count), weight_coefficient_of_variation, rng
                )

    if int(observed_counts.sum()) + unresolved_count != int(sample_size):
        raise RuntimeError("observation flow does not conserve records")
    return ObservedUnit(
        observed_counts=observed_counts,
        observed_weight=observed_weight,
        unresolved_count=unresolved_count,
        unresolved_weight=unresolved_weight,
        true_count=int(sample_size),
    )


def observed_profile_specs(protocol: dict[str, Any], cell: dict[str, Any]) -> tuple[np.ndarray, np.ndarray, float]:
    matrix = np.asarray(
        protocol["misclassification_profiles"][cell["misclassification_profile"]]["matrix"],
        dtype=float,
    )
    unresolved = np.asarray(
        protocol["unresolved_profiles"][cell["unresolved_profile"]]["state_probabilities"],
        dtype=float,
    )
    cv = float(protocol["weight_profiles"][cell["weight_profile"]]["coefficient_of_variation"])
    return matrix, unresolved, cv
