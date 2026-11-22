from pathlib import Path

import numpy as np

from odsa_econ.dgp import generate_state_probabilities
from odsa_econ.diagnostics import pairwise_reversal_share
from odsa_econ.protocol import load_protocol

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL = load_protocol(ROOT / "02_FROZEN_PROTOCOL" / "eint_r2_decision_protocol.yml")
STATES = list(PROTOCOL["states"])
INDEX = {state: i for i, state in enumerate(STATES)}


def rates(matrix: np.ndarray, definition: str) -> dict[str, float]:
    columns = [INDEX[state] for state in PROTOCOL["definitions"][definition]["states"]]
    vector = matrix[:, columns].sum(axis=1)
    return {f"u{i:02d}": float(value) for i, value in enumerate(vector)}


def high(scenario: str) -> np.ndarray:
    return generate_state_probabilities(
        PROTOCOL,
        scenario=scenario,
        separation_level="high",
        added_state_heterogeneity_level="high",
        unit_count=16,
    )


def test_null_scenario_has_no_between_unit_variation() -> None:
    matrix = high("null_common")
    assert np.allclose(matrix, matrix[0])


def test_broad_margin_scenario_preserves_narrow_rates() -> None:
    matrix = high("broad_margin_only")
    assert np.ptp(list(rates(matrix, "integrated_planning").values())) == 0
    assert np.ptp(list(rates(matrix, "specialised_planning").values())) == 0
    assert np.ptp(list(rates(matrix, "digitally_enabled_planning").values())) > 0


def test_middle_compensation_preserves_middle_rate() -> None:
    matrix = high("middle_compensation")
    assert np.ptp(list(rates(matrix, "integrated_planning").values())) > 0
    assert np.ptp(list(rates(matrix, "specialised_planning").values())) < 1e-12


def test_prespecified_reversal_scenario_reverses_strict_and_broad_order() -> None:
    matrix = high("strict_to_broad_reversal")
    result = pairwise_reversal_share(
        rates(matrix, "integrated_planning"),
        rates(matrix, "digitally_enabled_planning"),
    )
    assert result["strict_reversal_share"] == 1.0
