from pathlib import Path

import numpy as np

from odsa_econ.dgp import expected_sample_sizes, generate_state_probabilities
from odsa_econ.observation import simulate_observed_unit
from odsa_econ.protocol import load_protocol

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL = load_protocol(ROOT / "02_FROZEN_PROTOCOL" / "eint_r2_decision_protocol.yml")


def test_every_scenario_corner_is_valid_without_clipping() -> None:
    for scenario in PROTOCOL["scenario_parameters"]["scenarios"]:
        for separation in PROTOCOL["scenario_parameters"]["separation_levels"]:
            for heterogeneity in PROTOCOL["scenario_parameters"]["added_state_heterogeneity_levels"]:
                for unit_count in (8, 16):
                    matrix = generate_state_probabilities(
                        PROTOCOL,
                        scenario=scenario,
                        separation_level=separation,
                        added_state_heterogeneity_level=heterogeneity,
                        unit_count=unit_count,
                    )
                    assert np.all(matrix >= 0)
                    assert np.all(matrix <= 1)
                    assert np.allclose(matrix.sum(axis=1), 1.0)


def test_allocation_mean_is_preserved() -> None:
    sizes = expected_sample_sizes(16, 250, "gradient_skewed")
    assert abs(float(np.mean(sizes)) - 250) <= 0.5


def test_observation_conserves_records_and_weights_are_nonnegative() -> None:
    rng = np.random.default_rng(7)
    observed = simulate_observed_unit(
        np.array([0.2, 0.5, 0.05, 0.15, 0.1]),
        1000,
        misclassification_matrix=np.eye(5),
        unresolved_probabilities=np.array([0.05] * 5),
        weight_coefficient_of_variation=0.5,
        rng=rng,
    )
    assert observed.observed_counts.sum() + observed.unresolved_count == 1000
    assert np.all(observed.observed_weight >= 0)
    assert observed.unresolved_weight >= 0
