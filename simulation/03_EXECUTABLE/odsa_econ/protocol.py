from __future__ import annotations

import hashlib
import itertools
import json
import math
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import yaml


class ProtocolError(ValueError):
    """Raised when a protocol violates a frozen design invariant."""


def load_protocol(path: str | Path) -> dict[str, Any]:
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ProtocolError("protocol must be a YAML mapping")
    return payload


def protocol_sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical_cell(cell: dict[str, Any]) -> str:
    return json.dumps(cell, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def cell_seed_words(cell: dict[str, Any]) -> list[int]:
    digest = hashlib.sha256(canonical_cell(cell).encode("utf-8")).digest()
    return [int.from_bytes(digest[i : i + 4], "big") for i in range(0, 16, 4)]


def _validate_probability_vector(values: Iterable[float], *, label: str) -> np.ndarray:
    vector = np.asarray(list(values), dtype=float)
    if vector.ndim != 1 or not np.isfinite(vector).all():
        raise ProtocolError(f"{label} must be a finite one-dimensional vector")
    if (vector < 0).any() or (vector > 1).any():
        raise ProtocolError(f"{label} must contain probabilities in [0, 1]")
    return vector


def _validate_stochastic_matrix(values: Any, *, label: str, size: int) -> np.ndarray:
    matrix = np.asarray(values, dtype=float)
    if matrix.shape != (size, size) or not np.isfinite(matrix).all():
        raise ProtocolError(f"{label} must be a finite {size} by {size} matrix")
    if (matrix < 0).any() or (matrix > 1).any():
        raise ProtocolError(f"{label} entries must be in [0, 1]")
    if not np.allclose(matrix.sum(axis=1), 1.0, atol=1e-12):
        raise ProtocolError(f"{label} rows must sum to one")
    return matrix


def _relation(left: set[str], right: set[str]) -> str:
    if left == right:
        return "equal"
    if left < right:
        return "strict_subset"
    if left > right:
        return "strict_superset"
    if left.isdisjoint(right):
        return "disjoint"
    return "overlap"


def expand_full_grid(protocol: dict[str, Any]) -> list[dict[str, Any]]:
    execution = protocol["execution"]
    reference = dict(execution["reference_cell"])
    seen: dict[str, dict[str, Any]] = {}
    module_order: list[str] = []
    for module_name, module in execution["full_modules"].items():
        module_order.append(str(module_name))
        factors: dict[str, list[Any]] = module["factors"]
        names = list(factors)
        for values in itertools.product(*(factors[name] for name in names)):
            cell = dict(reference)
            cell.update(dict(zip(names, values, strict=True)))
            key = canonical_cell(cell)
            if key not in seen:
                seen[key] = {**cell, "modules": [str(module_name)]}
            else:
                seen[key]["modules"].append(str(module_name))
    cells = sorted(seen.values(), key=lambda row: canonical_cell({k: v for k, v in row.items() if k != "modules"}))
    for index, cell in enumerate(cells, start=1):
        cell["cell_id"] = f"cell_{index:04d}"
    return cells


def validate_protocol(protocol: dict[str, Any]) -> dict[str, Any]:
    required = {
        "schema_version",
        "states",
        "definitions",
        "objectives",
        "cost_profiles",
        "decision_rules",
        "base_state_probabilities",
        "scenario_parameters",
        "execution",
    }
    missing = required - set(protocol)
    if missing:
        raise ProtocolError(f"missing protocol sections: {sorted(missing)}")

    states = [str(value) for value in protocol["states"]]
    if len(states) != 5 or len(set(states)) != len(states):
        raise ProtocolError("the economic protocol requires exactly five unique states")
    state_set = set(states)

    definitions = protocol["definitions"]
    definition_sets: dict[str, set[str]] = {}
    for name, spec in definitions.items():
        positive = set(map(str, spec["states"]))
        if not positive or not positive <= state_set:
            raise ProtocolError(f"definition {name!r} is empty or contains unknown states")
        definition_sets[str(name)] = positive

    order = [str(value) for value in protocol["definition_order"]]
    if set(order) != set(definition_sets):
        raise ProtocolError("definition_order must register every definition exactly once")
    for left, right in zip(order, order[1:], strict=False):
        if not definition_sets[left] < definition_sets[right]:
            raise ProtocolError("definition_order must be strictly nested")

    for contrast in protocol["nested_contrasts"]:
        left = str(contrast["left"])
        right = str(contrast["right"])
        if _relation(definition_sets[left], definition_sets[right]) != "strict_subset":
            raise ProtocolError(f"contrast {left} to {right} is not a strict subset")

    for name, spec in protocol["objectives"].items():
        relevant = set(map(str, spec["relevant_states"]))
        if not relevant or not relevant <= state_set:
            raise ProtocolError(f"objective {name!r} is empty or contains unknown states")

    for name, spec in protocol["cost_profiles"].items():
        fp = float(spec["false_inclusion"])
        fn = float(spec["false_exclusion"])
        if not (math.isfinite(fp) and math.isfinite(fn) and fp > 0 and fn > 0):
            raise ProtocolError(f"cost profile {name!r} must contain positive finite costs")

    base = np.array([float(protocol["base_state_probabilities"][state]) for state in states])
    if (base < 0).any() or not math.isclose(float(base.sum()), 1.0, abs_tol=1e-12):
        raise ProtocolError("base_state_probabilities must be non-negative and sum to one")

    for name, spec in protocol["misclassification_profiles"].items():
        _validate_stochastic_matrix(spec["matrix"], label=f"misclassification profile {name}", size=len(states))
    for name, spec in protocol["unresolved_profiles"].items():
        vector = _validate_probability_vector(spec["state_probabilities"], label=f"unresolved profile {name}")
        if vector.shape != (len(states),):
            raise ProtocolError(f"unresolved profile {name!r} must have {len(states)} entries")

    thresholds = [float(x) for x in protocol["decision_rules"]["threshold_values"]]
    if thresholds != sorted(set(thresholds)) or any(x <= 0 or x >= 1 for x in thresholds):
        raise ProtocolError("threshold_values must be unique, increasing and inside (0, 1)")
    top_k = [int(x) for x in protocol["decision_rules"]["top_k_values"]]
    if top_k != sorted(set(top_k)) or any(x <= 0 for x in top_k):
        raise ProtocolError("top_k_values must be unique positive integers")

    cells = expand_full_grid(protocol)
    declared_cells = int(protocol["execution"]["declared_unique_full_cell_count"])
    if len(cells) != declared_cells:
        raise ProtocolError(f"declared {declared_cells} full cells but expansion produced {len(cells)}")
    reps = int(protocol["execution"]["full_replications_per_cell"])
    declared_rows = int(protocol["execution"]["declared_full_replicate_row_count"])
    if len(cells) * reps != declared_rows:
        raise ProtocolError("declared full replicate-row count is inconsistent")
    if int(protocol["execution"]["full_stream_count"]) * int(protocol["execution"]["full_replications_per_stream"]) != reps:
        raise ProtocolError("stream policy does not reproduce full replications per cell")

    # Validate every scenario over every unit-count and parameter corner without clipping.
    from .dgp import generate_state_probabilities

    for scenario in protocol["scenario_parameters"]["scenarios"]:
        for separation in protocol["scenario_parameters"]["separation_levels"]:
            for heterogeneity in protocol["scenario_parameters"]["added_state_heterogeneity_levels"]:
                for unit_count in (8, 16):
                    matrix = generate_state_probabilities(
                        protocol,
                        scenario=str(scenario),
                        separation_level=str(separation),
                        added_state_heterogeneity_level=str(heterogeneity),
                        unit_count=unit_count,
                    )
                    if matrix.shape != (unit_count, len(states)):
                        raise ProtocolError("DGP returned an unexpected matrix shape")
                    if (matrix < 0).any() or (matrix > 1).any() or not np.allclose(matrix.sum(axis=1), 1.0, atol=1e-12):
                        raise ProtocolError(f"invalid state probabilities for {scenario}/{separation}/{heterogeneity}/{unit_count}")

    return {
        "status": "PASS",
        "schema_version": str(protocol["schema_version"]),
        "state_count": len(states),
        "definition_count": len(definitions),
        "objective_count": len(protocol["objectives"]),
        "cost_profile_count": len(protocol["cost_profiles"]),
        "scenario_count": len(protocol["scenario_parameters"]["scenarios"]),
        "unique_full_cell_count": len(cells),
        "full_replicate_row_count": len(cells) * reps,
        "smoke_cell_count": len(protocol["execution"]["smoke_cells"]),
    }


def verify_freeze(protocol_path: str | Path, freeze_path: str | Path) -> dict[str, Any]:
    freeze = json.loads(Path(freeze_path).read_text(encoding="utf-8"))
    observed = protocol_sha256(protocol_path)
    expected = str(freeze["protocol_sha256"])
    if observed != expected:
        raise ProtocolError(f"protocol freeze mismatch: expected {expected}, observed {observed}")
    return {"status": "PASS", "protocol_sha256": observed}
