import itertools

import numpy as np

from odsa_econ.diagnostics import (
    action_loss,
    interval_order_determinacy,
    interval_top_k_membership,
    semantic_loss,
    threshold_action,
    top_k_action,
)


def test_nested_level_monotonicity_and_threshold_crossing() -> None:
    narrow = {"a": 0.10, "b": 0.30, "c": 0.49}
    added = {"a": 0.20, "b": 0.00, "c": 0.02}
    broad = {unit: narrow[unit] + added[unit] for unit in narrow}
    assert all(broad[u] >= narrow[u] for u in narrow)
    assert threshold_action(narrow, 0.50, "above_or_equal") == set()
    assert threshold_action(broad, 0.50, "above_or_equal") == {"c"}
    assert narrow["c"] < 0.50 <= broad["c"]


def test_exact_pairwise_reversal_condition() -> None:
    p_g, p_h = 0.40, 0.30
    m_g, m_h = 0.05, 0.20
    assert 0 < p_g - p_h < m_h - m_g
    assert p_g + m_g < p_h + m_h


def test_top_k_decision_equivalence_with_numeric_difference() -> None:
    left = {"a": 0.8, "b": 0.7, "c": 0.2}
    right = {"a": 0.9, "b": 0.75, "c": 0.4}
    left_set, _ = top_k_action(left, 2, "highest")
    right_set, _ = top_k_action(right, 2, "highest")
    assert left_set == right_set == {"a", "b"}
    assert left != right


def test_semantic_loss_is_zero_for_matching_state_set() -> None:
    probabilities = np.array([[0.2, 0.3, 0.5], [0.4, 0.1, 0.5]])
    states = ["x", "y", "z"]
    result = semantic_loss(probabilities, states, ["y", "z"], ["y", "z"], 1.0, 2.0)
    assert result["cost_weighted_semantic_loss"] == 0


def test_semantic_loss_positive_for_mismatched_state_set_with_support() -> None:
    probabilities = np.array([[0.2, 0.3, 0.5], [0.4, 0.1, 0.5]])
    states = ["x", "y", "z"]
    result = semantic_loss(probabilities, states, ["z"], ["y", "z"], 1.0, 2.0)
    assert result["false_exclusion_mass"] > 0
    assert result["cost_weighted_semantic_loss"] > 0


def test_action_loss_counts_false_inclusion_and_exclusion() -> None:
    result = action_loss({"a", "b"}, {"b", "c"}, 2.0, 3.0, denominator=4)
    assert result["false_inclusion_share"] == 0.25
    assert result["false_exclusion_share"] == 0.25
    assert result["cost_weighted_loss"] == 1.25


def test_interval_dominance_is_determinate() -> None:
    result = interval_order_determinacy({"a": (0.6, 0.7), "b": (0.1, 0.5), "c": (0.65, 0.8)})
    assert result["eligible_pairs"] == 3
    assert result["determinate_pairs"] == 2


def test_interval_top_k_guaranteed_is_subset_of_possible() -> None:
    bounds = {"a": (0.8, 0.9), "b": (0.7, 0.85), "c": (0.2, 0.4), "d": (0.1, 0.3)}
    result = interval_top_k_membership(bounds, 2, "highest")
    assert result["guaranteed"] <= result["possible"]
    assert "a" in result["guaranteed"]


def test_top_k_formula_sufficiency_by_endpoint_enumeration() -> None:
    bounds = {"a": (0.8, 0.9), "b": (0.7, 0.85), "c": (0.2, 0.4)}
    membership = interval_top_k_membership(bounds, 1, "highest")
    for values in itertools.product(*[(lo, hi) for lo, hi in bounds.values()]):
        point = dict(zip(bounds, values, strict=True))
        selected, _ = top_k_action(point, 1, "highest")
        assert membership["guaranteed"] <= selected
        assert selected <= membership["possible"]


def test_interval_top_k_guarantee_is_conservative_at_ties() -> None:
    bounds = {"a": (0.8, 0.8), "b": (0.8, 0.8), "c": (0.1, 0.2)}
    result = interval_top_k_membership(bounds, 1, "highest")
    assert result["guaranteed"] == set()
    assert result["possible"] == {"a", "b"}
