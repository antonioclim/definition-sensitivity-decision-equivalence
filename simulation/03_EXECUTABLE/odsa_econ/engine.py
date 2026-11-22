from __future__ import annotations

import csv
import hashlib
import json
import math
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from .dgp import expected_sample_sizes, generate_state_probabilities
from .diagnostics import (
    action_loss,
    definition_rate,
    interval_order_determinacy,
    interval_top_k_membership,
    pairwise_reversal_share,
    rate_bounds,
    semantic_loss,
    set_churn,
    threshold_action,
    threshold_interval_classification,
    top_k_action,
)
from .observation import observed_profile_specs, simulate_observed_unit
from .protocol import cell_seed_words


@dataclass
class RunningStat:
    n: int = 0
    undefined: int = 0
    total: float = 0.0
    total_sq: float = 0.0
    minimum: float = math.inf
    maximum: float = -math.inf

    def add(self, value: float) -> None:
        if not math.isfinite(float(value)):
            self.undefined += 1
            return
        value = float(value)
        self.n += 1
        self.total += value
        self.total_sq += value * value
        self.minimum = min(self.minimum, value)
        self.maximum = max(self.maximum, value)

    def result(self) -> dict[str, float | int]:
        if self.n == 0:
            return {
                "n_defined": 0,
                "n_undefined": self.undefined,
                "mean": float("nan"),
                "sd": float("nan"),
                "mcse": float("nan"),
                "minimum": float("nan"),
                "maximum": float("nan"),
            }
        mean = self.total / self.n
        variance = max((self.total_sq - self.n * mean * mean) / (self.n - 1), 0.0) if self.n > 1 else 0.0
        sd = math.sqrt(variance)
        return {
            "n_defined": self.n,
            "n_undefined": self.undefined,
            "mean": mean,
            "sd": sd,
            "mcse": sd / math.sqrt(self.n),
            "minimum": self.minimum,
            "maximum": self.maximum,
        }


@dataclass
class MetricAggregator:
    stats: dict[tuple[str, ...], RunningStat] = field(default_factory=lambda: defaultdict(RunningStat))

    def add(self, key: Iterable[Any], value: float) -> None:
        self.stats[tuple(map(str, key))].add(float(value))

    def rows(self, cell_id: str, metric_scope: str, stream_id: str = "pooled") -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for key in sorted(self.stats):
            rows.append(
                {
                    "cell_id": cell_id,
                    "stream_id": stream_id,
                    "metric_scope": metric_scope,
                    "metric_family": key[0],
                    "metric_name": key[1],
                    "definition": key[2],
                    "objective": key[3],
                    "rule": key[4],
                    "parameter": key[5],
                    "cost_profile": key[6],
                    **self.stats[key].result(),
                }
            )
        return rows


def _deterministic_row(
    cell_id: str,
    family: str,
    name: str,
    value: float,
    definition: str = "NA",
    objective: str = "NA",
    rule: str = "NA",
    parameter: Any = "NA",
    cost_profile: str = "NA",
) -> dict[str, Any]:
    return {
        "cell_id": cell_id,
        "stream_id": "deterministic",
        "metric_scope": "deterministic_population",
        "metric_family": family,
        "metric_name": name,
        "definition": definition,
        "objective": objective,
        "rule": rule,
        "parameter": str(parameter),
        "cost_profile": cost_profile,
        "n_defined": 1,
        "n_undefined": 0,
        "mean": float(value),
        "sd": 0.0,
        "mcse": 0.0,
        "minimum": float(value),
        "maximum": float(value),
    }


def _record_metric(
    agg: MetricAggregator,
    family: str,
    name: str,
    value: float,
    definition: str = "NA",
    objective: str = "NA",
    rule: str = "NA",
    parameter: Any = "NA",
    cost_profile: str = "NA",
) -> None:
    agg.add((family, name, definition, objective, rule, parameter, cost_profile), value)


def _unit_mapping(values: np.ndarray) -> dict[str, float]:
    return {f"unit_{i + 1:02d}": float(value) for i, value in enumerate(values)}


def _state_set(protocol: dict[str, Any], section: str, name: str) -> list[str]:
    key = "states" if section == "definitions" else "relevant_states"
    return list(map(str, protocol[section][name][key]))


def _population_rates(protocol: dict[str, Any], probabilities: np.ndarray, section: str) -> dict[str, dict[str, float]]:
    states = [str(x) for x in protocol["states"]]
    index = {state: i for i, state in enumerate(states)}
    result: dict[str, dict[str, float]] = {}
    for name in protocol[section]:
        positive = _state_set(protocol, section, str(name))
        result[str(name)] = _unit_mapping(
            np.array([definition_rate(row, index, positive) for row in probabilities], dtype=float)
        )
    return result


def _weighted_observed_rates(
    protocol: dict[str, Any], observed_units: list[Any]
) -> tuple[dict[str, dict[str, float]], dict[str, dict[str, tuple[float, float]]]]:
    states = [str(x) for x in protocol["states"]]
    index = {state: i for i, state in enumerate(states)}
    rates: dict[str, dict[str, float]] = {}
    bounds: dict[str, dict[str, tuple[float, float]]] = {}
    for definition in protocol["definition_order"]:
        positive = _state_set(protocol, "definitions", definition)
        rates[definition] = {}
        bounds[definition] = {}
        for i, observed in enumerate(observed_units):
            lower, upper, complete_case = rate_bounds(
                observed.observed_weight,
                observed.unresolved_weight,
                index,
                positive,
            )
            unit = f"unit_{i + 1:02d}"
            rates[definition][unit] = complete_case
            bounds[definition][unit] = (lower, upper)
    return rates, bounds


def _base_set_metrics(selected: set[str], benchmark: set[str], unit_count: int) -> dict[str, float]:
    return action_loss(selected, benchmark, 1.0, 1.0, denominator=unit_count)


def _append_action_rows(
    rows: list[dict[str, Any]],
    *,
    cell_id: str,
    stage: str,
    selected: set[str],
    benchmark: set[str],
    unit_count: int,
    definition: str,
    objective: str,
    rule: str,
    parameter: Any,
    cost_profiles: dict[str, Any],
) -> None:
    base = _base_set_metrics(selected, benchmark, unit_count)
    for metric in ("false_inclusion_share", "false_exclusion_share", "symmetric_difference_share", "jaccard_overlap"):
        rows.append(_deterministic_row(cell_id, "action_loss", f"{stage}_{metric}", base[metric], definition, objective, rule, parameter))
    for cost_profile, costs in cost_profiles.items():
        loss = action_loss(
            selected,
            benchmark,
            float(costs["false_inclusion"]),
            float(costs["false_exclusion"]),
            denominator=unit_count,
        )
        rows.append(_deterministic_row(cell_id, "action_loss", f"{stage}_cost_weighted_loss", loss["cost_weighted_loss"], definition, objective, rule, parameter, cost_profile))


def deterministic_population_metrics(protocol: dict[str, Any], cell: dict[str, Any]) -> tuple[list[dict[str, Any]], np.ndarray, dict[str, dict[str, float]], dict[str, dict[str, float]]]:
    probabilities = generate_state_probabilities(
        protocol,
        scenario=str(cell["scenario"]),
        separation_level=str(cell["separation_level"]),
        added_state_heterogeneity_level=str(cell["added_state_heterogeneity_level"]),
        unit_count=int(cell["unit_count"]),
    )
    population_definitions = _population_rates(protocol, probabilities, "definitions")
    population_objectives = _population_rates(protocol, probabilities, "objectives")
    cell_id = str(cell.get("cell_id", cell.get("smoke_id", "cell")))
    unit_count = int(cell["unit_count"])
    rows: list[dict[str, Any]] = []

    for definition in protocol["definition_order"]:
        vector = np.array(list(population_definitions[definition].values()), dtype=float)
        rows.append(_deterministic_row(cell_id, "level", "population_mean", float(np.mean(vector)), definition))
        rows.append(_deterministic_row(cell_id, "level", "population_minimum", float(np.min(vector)), definition))
        rows.append(_deterministic_row(cell_id, "level", "population_maximum", float(np.max(vector)), definition))

    for contrast in protocol["nested_contrasts"]:
        left = str(contrast["left"])
        right = str(contrast["right"])
        name = f"{left}__to__{right}"
        left_values = population_definitions[left]
        right_values = population_definitions[right]
        reversal = pairwise_reversal_share(left_values, right_values)
        mean_delta = float(np.mean([right_values[u] - left_values[u] for u in left_values]))
        rows.append(_deterministic_row(cell_id, "contrast", "population_mean_level_delta", mean_delta, name))
        rows.append(_deterministic_row(cell_id, "contrast", "population_strict_reversal_share", reversal["strict_reversal_share"], name))
        rows.append(_deterministic_row(cell_id, "contrast", "population_pairwise_disagreement_share", reversal["disagreement_share"], name))

        for threshold in protocol["decision_rules"]["threshold_values"]:
            for direction in protocol["decision_rules"]["threshold_directions"]:
                left_set = threshold_action(left_values, float(threshold), str(direction))
                right_set = threshold_action(right_values, float(threshold), str(direction))
                change = set_churn(left_set, right_set)
                rows.append(_deterministic_row(cell_id, "cross_definition_action", "population_threshold_symmetric_difference_share", change["symmetric_difference_share"], name, rule=f"threshold_{direction}", parameter=threshold))
        for k in protocol["decision_rules"]["top_k_values"]:
            if int(k) > unit_count:
                continue
            for direction in protocol["decision_rules"]["top_k_directions"]:
                left_set, left_tie = top_k_action(left_values, int(k), str(direction))
                right_set, right_tie = top_k_action(right_values, int(k), str(direction))
                change = set_churn(left_set, right_set, int(k))
                rows.append(_deterministic_row(cell_id, "cross_definition_action", "population_top_k_churn", change["churn"], name, rule=f"top_k_{direction}", parameter=k))
                rows.append(_deterministic_row(cell_id, "cross_definition_action", "population_top_k_jaccard", change["jaccard_overlap"], name, rule=f"top_k_{direction}", parameter=k))
                rows.append(_deterministic_row(cell_id, "tie_audit", "population_cross_definition_boundary_tie", float(left_tie or right_tie), name, rule=f"top_k_{direction}", parameter=k))

    for objective, objective_values in population_objectives.items():
        objective_states = _state_set(protocol, "objectives", objective)
        for definition in protocol["definition_order"]:
            definition_states = _state_set(protocol, "definitions", definition)
            base_semantic = semantic_loss(
                probabilities,
                [str(x) for x in protocol["states"]],
                definition_states,
                objective_states,
                1.0,
                1.0,
            )
            rows.append(_deterministic_row(cell_id, "semantic", "false_inclusion_mass", base_semantic["false_inclusion_mass"], definition, objective))
            rows.append(_deterministic_row(cell_id, "semantic", "false_exclusion_mass", base_semantic["false_exclusion_mass"], definition, objective))
            for cost_profile, costs in protocol["cost_profiles"].items():
                semantic = semantic_loss(
                    probabilities,
                    [str(x) for x in protocol["states"]],
                    definition_states,
                    objective_states,
                    float(costs["false_inclusion"]),
                    float(costs["false_exclusion"]),
                )
                rows.append(_deterministic_row(cell_id, "semantic", "cost_weighted_semantic_loss", semantic["cost_weighted_semantic_loss"], definition, objective, cost_profile=cost_profile))

            for threshold in protocol["decision_rules"]["threshold_values"]:
                for direction in protocol["decision_rules"]["threshold_directions"]:
                    benchmark = threshold_action(objective_values, float(threshold), str(direction))
                    selected = threshold_action(population_definitions[definition], float(threshold), str(direction))
                    _append_action_rows(
                        rows,
                        cell_id=cell_id,
                        stage="population",
                        selected=selected,
                        benchmark=benchmark,
                        unit_count=unit_count,
                        definition=definition,
                        objective=objective,
                        rule=f"threshold_{direction}",
                        parameter=threshold,
                        cost_profiles=protocol["cost_profiles"],
                    )

            for k in protocol["decision_rules"]["top_k_values"]:
                if int(k) > unit_count:
                    continue
                for direction in protocol["decision_rules"]["top_k_directions"]:
                    benchmark, benchmark_tie = top_k_action(objective_values, int(k), str(direction))
                    selected, selected_tie = top_k_action(population_definitions[definition], int(k), str(direction))
                    rows.append(_deterministic_row(cell_id, "tie_audit", "population_objective_or_definition_boundary_tie", float(benchmark_tie or selected_tie), definition, objective, f"top_k_{direction}", k))
                    _append_action_rows(
                        rows,
                        cell_id=cell_id,
                        stage="population",
                        selected=selected,
                        benchmark=benchmark,
                        unit_count=unit_count,
                        definition=definition,
                        objective=objective,
                        rule=f"top_k_{direction}",
                        parameter=k,
                        cost_profiles=protocol["cost_profiles"],
                    )

    # Prespecified comparator ablation.
    for contrast in protocol["nested_contrasts"]:
        left = str(contrast["left"])
        right = str(contrast["right"])
        name = f"{left}__to__{right}"
        mean_delta = abs(float(np.mean([population_definitions[right][u] - population_definitions[left][u] for u in population_definitions[left]])))
        rank_reversal = pairwise_reversal_share(population_definitions[left], population_definitions[right])["strict_reversal_share"]
        for objective in population_objectives:
            semantic = semantic_loss(
                probabilities,
                [str(x) for x in protocol["states"]],
                _state_set(protocol, "definitions", right),
                _state_set(protocol, "objectives", objective),
                1.0,
                1.0,
            )
            semantic_mismatch = float(semantic["cost_weighted_semantic_loss"] > 0)
            for epsilon in protocol["decision_rules"]["level_materiality_values"]:
                material = float(mean_delta >= float(epsilon))
                rows.append(_deterministic_row(cell_id, "ablation", "generic_level_materiality_detected", material, name, objective, "mean_level", epsilon))
                rows.append(_deterministic_row(cell_id, "ablation", "rank_reversal_detected", float(rank_reversal > 0), name, objective, "pairwise_order", epsilon))
                rows.append(_deterministic_row(cell_id, "ablation", "semantic_mismatch_detected", semantic_mismatch, name, objective, "state_objective", epsilon))
                for threshold in protocol["decision_rules"]["threshold_values"]:
                    left_set = threshold_action(population_definitions[left], float(threshold), "above_or_equal")
                    right_set = threshold_action(population_definitions[right], float(threshold), "above_or_equal")
                    action_diff = float(left_set != right_set)
                    parameter = f"epsilon={epsilon};tau={threshold}"
                    rows.append(_deterministic_row(cell_id, "ablation", "action_disagreement_without_material_level_change", float(action_diff and not material), name, objective, "threshold_above_or_equal", parameter))
                    rows.append(_deterministic_row(cell_id, "ablation", "material_level_change_without_action_disagreement", float(material and not action_diff), name, objective, "threshold_above_or_equal", parameter))
                    rows.append(_deterministic_row(cell_id, "ablation", "decision_equivalence_despite_numerical_difference", float(mean_delta > 0 and not action_diff), name, objective, "threshold_above_or_equal", parameter))
                    rows.append(_deterministic_row(cell_id, "ablation", "rank_stability_with_semantic_mismatch", float(rank_reversal == 0 and semantic_mismatch), name, objective, "threshold_above_or_equal", parameter))

    return rows, probabilities, population_definitions, population_objectives


def _record_observed_set_metrics(
    agg: MetricAggregator,
    *,
    selected: set[str],
    benchmark: set[str],
    unit_count: int,
    definition: str,
    objective: str,
    rule: str,
    parameter: Any,
    cost_profiles: dict[str, Any],
) -> None:
    base = _base_set_metrics(selected, benchmark, unit_count)
    for metric in ("false_inclusion_share", "false_exclusion_share", "symmetric_difference_share", "jaccard_overlap"):
        _record_metric(agg, "action_loss", f"observed_{metric}", base[metric], definition, objective, rule, parameter)
    for cost_profile, costs in cost_profiles.items():
        loss = action_loss(
            selected,
            benchmark,
            float(costs["false_inclusion"]),
            float(costs["false_exclusion"]),
            denominator=unit_count,
        )
        _record_metric(agg, "action_loss", "observed_cost_weighted_loss", loss["cost_weighted_loss"], definition, objective, rule, parameter, cost_profile)


def simulate_observed_replicate(
    protocol: dict[str, Any],
    cell: dict[str, Any],
    probabilities: np.ndarray,
    population_definitions: dict[str, dict[str, float]],
    population_objectives: dict[str, dict[str, float]],
    rng: np.random.Generator,
) -> tuple[MetricAggregator, dict[str, Any]]:
    sample_sizes = expected_sample_sizes(
        int(cell["unit_count"]), int(cell["base_sample_size"]), str(cell["allocation_profile"])
    )
    matrix, unresolved, weight_cv = observed_profile_specs(protocol, cell)
    observed_units = [
        simulate_observed_unit(
            probabilities[i],
            int(sample_sizes[i]),
            misclassification_matrix=matrix,
            unresolved_probabilities=unresolved,
            weight_coefficient_of_variation=weight_cv,
            rng=rng,
        )
        for i in range(int(cell["unit_count"]))
    ]
    observed_definitions, observed_bounds = _weighted_observed_rates(protocol, observed_units)
    agg = MetricAggregator()
    unit_count = int(cell["unit_count"])
    total_sample = sum(observed.true_count for observed in observed_units)
    unresolved_count = sum(observed.unresolved_count for observed in observed_units)
    _record_metric(agg, "observation", "unresolved_record_share", unresolved_count / total_sample)

    for definition in protocol["definition_order"]:
        pop_vector = np.array(list(population_definitions[definition].values()), dtype=float)
        obs_vector = np.array(list(observed_definitions[definition].values()), dtype=float)
        _record_metric(agg, "level", "observed_mean", float(np.nanmean(obs_vector)), definition)
        _record_metric(agg, "level", "observed_mean_absolute_error", float(np.nanmean(np.abs(obs_vector - pop_vector))), definition)
        determinacy = interval_order_determinacy(observed_bounds[definition])
        _record_metric(agg, "partial_order", "determinate_share", determinacy["determinate_share"], definition)
        for threshold in protocol["decision_rules"]["threshold_values"]:
            for direction in protocol["decision_rules"]["threshold_directions"]:
                classification = threshold_interval_classification(observed_bounds[definition], float(threshold), str(direction))
                _record_metric(agg, "partial_order", "threshold_ambiguous_share", len(classification["ambiguous"]) / unit_count, definition, rule=f"threshold_{direction}", parameter=threshold)
        for k in protocol["decision_rules"]["top_k_values"]:
            if int(k) > unit_count:
                continue
            for direction in protocol["decision_rules"]["top_k_directions"]:
                membership = interval_top_k_membership(observed_bounds[definition], int(k), str(direction))
                _record_metric(agg, "partial_order", "top_k_guaranteed_share", len(membership["guaranteed"]) / int(k), definition, rule=f"top_k_{direction}", parameter=k)
                _record_metric(agg, "partial_order", "top_k_possible_excess", max(len(membership["possible"]) - int(k), 0) / unit_count, definition, rule=f"top_k_{direction}", parameter=k)

    for contrast in protocol["nested_contrasts"]:
        left = str(contrast["left"])
        right = str(contrast["right"])
        name = f"{left}__to__{right}"
        reversal = pairwise_reversal_share(observed_definitions[left], observed_definitions[right])
        _record_metric(agg, "contrast", "observed_strict_reversal_share", reversal["strict_reversal_share"], name)
        _record_metric(agg, "contrast", "observed_pairwise_disagreement_share", reversal["disagreement_share"], name)
        for threshold in protocol["decision_rules"]["threshold_values"]:
            for direction in protocol["decision_rules"]["threshold_directions"]:
                left_set = threshold_action(observed_definitions[left], float(threshold), str(direction))
                right_set = threshold_action(observed_definitions[right], float(threshold), str(direction))
                change = set_churn(left_set, right_set)
                _record_metric(agg, "cross_definition_action", "observed_threshold_symmetric_difference_share", change["symmetric_difference_share"], name, rule=f"threshold_{direction}", parameter=threshold)
        for k in protocol["decision_rules"]["top_k_values"]:
            if int(k) > unit_count:
                continue
            for direction in protocol["decision_rules"]["top_k_directions"]:
                left_set, left_tie = top_k_action(observed_definitions[left], int(k), str(direction))
                right_set, right_tie = top_k_action(observed_definitions[right], int(k), str(direction))
                change = set_churn(left_set, right_set, int(k))
                _record_metric(agg, "cross_definition_action", "observed_top_k_churn", change["churn"], name, rule=f"top_k_{direction}", parameter=k)
                _record_metric(agg, "cross_definition_action", "observed_top_k_jaccard", change["jaccard_overlap"], name, rule=f"top_k_{direction}", parameter=k)
                _record_metric(agg, "tie_audit", "observed_cross_definition_boundary_tie", float(left_tie or right_tie), name, rule=f"top_k_{direction}", parameter=k)

    for objective, benchmark_values in population_objectives.items():
        for definition in protocol["definition_order"]:
            for threshold in protocol["decision_rules"]["threshold_values"]:
                for direction in protocol["decision_rules"]["threshold_directions"]:
                    benchmark = threshold_action(benchmark_values, float(threshold), str(direction))
                    selected = threshold_action(observed_definitions[definition], float(threshold), str(direction))
                    _record_observed_set_metrics(
                        agg,
                        selected=selected,
                        benchmark=benchmark,
                        unit_count=unit_count,
                        definition=definition,
                        objective=objective,
                        rule=f"threshold_{direction}",
                        parameter=threshold,
                        cost_profiles=protocol["cost_profiles"],
                    )
            for k in protocol["decision_rules"]["top_k_values"]:
                if int(k) > unit_count:
                    continue
                for direction in protocol["decision_rules"]["top_k_directions"]:
                    benchmark, benchmark_tie = top_k_action(benchmark_values, int(k), str(direction))
                    selected, selected_tie = top_k_action(observed_definitions[definition], int(k), str(direction))
                    _record_metric(agg, "tie_audit", "observed_objective_or_definition_boundary_tie", float(benchmark_tie or selected_tie), definition, objective, f"top_k_{direction}", k)
                    _record_observed_set_metrics(
                        agg,
                        selected=selected,
                        benchmark=benchmark,
                        unit_count=unit_count,
                        definition=definition,
                        objective=objective,
                        rule=f"top_k_{direction}",
                        parameter=k,
                        cost_profiles=protocol["cost_profiles"],
                    )

    replicate_summary = {
        "total_sample_size": int(total_sample),
        "unresolved_count": int(unresolved_count),
        "probability_minimum": float(probabilities.min()),
        "probability_maximum": float(probabilities.max()),
    }
    return agg, replicate_summary


def run_cell(
    protocol: dict[str, Any],
    cell: dict[str, Any],
    *,
    stream_count: int,
    replications_per_stream: int,
    retain_replicate_summaries: bool = False,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    cell_id = str(cell.get("cell_id", cell.get("smoke_id", "cell")))
    deterministic_rows, probabilities, population_definitions, population_objectives = deterministic_population_metrics(protocol, cell)
    pooled = MetricAggregator()
    stream_rows: list[dict[str, Any]] = []
    replicate_summaries: list[dict[str, Any]] = []

    root_seed = int(protocol["root_seed"])
    seed_words = cell_seed_words({k: v for k, v in cell.items() if k not in {"cell_id", "modules", "smoke_id"}})
    cell_sequence = np.random.SeedSequence([root_seed, *seed_words])
    stream_sequences = cell_sequence.spawn(stream_count)
    global_replication = 0
    for stream_index, stream_sequence in enumerate(stream_sequences, start=1):
        stream = MetricAggregator()
        for sequence in stream_sequence.spawn(replications_per_stream):
            global_replication += 1
            rng = np.random.default_rng(sequence)
            replicate, summary = simulate_observed_replicate(
                protocol,
                cell,
                probabilities,
                population_definitions,
                population_objectives,
                rng,
            )
            for key, stat in replicate.stats.items():
                result = stat.result()
                if result["n_defined"] != 1 or result["n_undefined"] not in (0, 1):
                    raise RuntimeError("replicate metric did not resolve to one scalar")
                value = float(result["mean"]) if result["n_defined"] else float("nan")
                pooled.add(key, value)
                stream.add(key, value)
            if retain_replicate_summaries:
                replicate_summaries.append(
                    {
                        "cell_id": cell_id,
                        "stream_id": f"stream_{stream_index:02d}",
                        "replication": global_replication,
                        **summary,
                    }
                )
        stream_rows.extend(stream.rows(cell_id, "stochastic_observed", f"stream_{stream_index:02d}"))

    pooled_rows = pooled.rows(cell_id, "stochastic_observed", "pooled")
    return deterministic_rows + pooled_rows, replicate_summaries, stream_rows


def write_csv(path: str | Path, rows: list[dict[str, Any]]) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        destination.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0])
    with destination.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


def file_sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
