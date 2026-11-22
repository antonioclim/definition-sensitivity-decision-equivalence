from __future__ import annotations

import math
from typing import Any

import numpy as np


class DGPError(ValueError):
    """Raised when a scenario would require silent clipping or renormalisation."""


def _unit_latent(unit_count: int) -> np.ndarray:
    if unit_count < 2:
        raise DGPError("unit_count must be at least two")
    return np.linspace(-1.0, 1.0, unit_count, dtype=float)


def generate_state_probabilities(
    protocol: dict[str, Any],
    *,
    scenario: str,
    separation_level: str,
    added_state_heterogeneity_level: str,
    unit_count: int,
) -> np.ndarray:
    states = [str(x) for x in protocol["states"]]
    base = {str(k): float(v) for k, v in protocol["base_state_probabilities"].items()}
    separation = float(protocol["scenario_parameters"]["separation_levels"][separation_level])
    heterogeneity = float(protocol["scenario_parameters"]["added_state_heterogeneity_levels"][added_state_heterogeneity_level])
    z = _unit_latent(int(unit_count))
    centred_quadratic = z**2 - float(np.mean(z**2))

    da = np.zeros_like(z)
    du = np.zeros_like(z)
    dv = np.zeros_like(z)

    if scenario == "null_common":
        pass
    elif scenario == "aligned_diffusion":
        da = separation * z
        du = 0.75 * heterogeneity * z
        dv = 1.25 * heterogeneity * z
    elif scenario == "broad_margin_only":
        dv = heterogeneity * z
    elif scenario == "middle_compensation":
        da = separation * z
        du = -separation * z
        dv = 0.50 * heterogeneity * z
    elif scenario == "strict_to_broad_reversal":
        da = separation * z
        du = -0.25 * separation * z
        dv = -(separation + 0.75 * heterogeneity) * z
    elif scenario == "mixed_nonmonotone":
        da = separation * z
        du = -0.80 * separation * z + 0.50 * heterogeneity * centred_quadratic
        dv = -0.35 * separation * z + heterogeneity * np.sin(math.pi * z)
    else:
        raise DGPError(f"unknown scenario {scenario!r}")

    integrated = base["integrated_system"] + da
    specialised = base["specialised_software"] + du
    broad_added = base["standard_software"] + base["platform"] + dv
    platform_fraction = base["platform"] / (base["standard_software"] + base["platform"])
    platform = broad_added * platform_fraction
    standard = broad_added - platform
    manual = 1.0 - integrated - specialised - broad_added

    matrix_by_name = {
        "manual": manual,
        "standard_software": standard,
        "platform": platform,
        "specialised_software": specialised,
        "integrated_system": integrated,
    }
    matrix = np.column_stack([matrix_by_name[state] for state in states])
    if not np.isfinite(matrix).all():
        raise DGPError("scenario generated non-finite probabilities")
    minimum = float(matrix.min())
    maximum = float(matrix.max())
    if minimum < -1e-12 or maximum > 1 + 1e-12:
        raise DGPError(f"scenario requires clipping: min={minimum}, max={maximum}")
    matrix[np.abs(matrix) < 1e-15] = 0.0
    if not np.allclose(matrix.sum(axis=1), 1.0, atol=1e-12):
        raise DGPError("scenario probabilities do not sum to one")
    return matrix


def expected_sample_sizes(unit_count: int, base_sample_size: int, allocation_profile: str) -> np.ndarray:
    if base_sample_size <= 1:
        raise DGPError("base_sample_size must exceed one")
    if allocation_profile == "balanced":
        multipliers = np.ones(unit_count, dtype=float)
    elif allocation_profile == "gradient_skewed":
        multipliers = np.linspace(0.5, 1.5, unit_count, dtype=float)
        multipliers /= float(np.mean(multipliers))
    else:
        raise DGPError(f"unknown allocation profile {allocation_profile!r}")
    sizes = np.rint(base_sample_size * multipliers).astype(int)
    if (sizes < 2).any():
        raise DGPError("allocation generated a sample size below two")
    return sizes
