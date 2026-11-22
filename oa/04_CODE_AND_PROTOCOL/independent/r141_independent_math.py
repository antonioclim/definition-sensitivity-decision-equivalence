"""Independent exact arithmetic for the R14.1 recovery of the R13 OA design.

This is a new implementation written after historical R14 outcomes were known.
It is neither the lost R14 oracle nor a blinded/preregistered verification.
Only the Python standard library is used. No producer/core implementation is
imported or executed. Membership envelopes use direct subset feasibility, not
the endpoint-count formula implemented by the R13 core.
"""
from fractions import Fraction
from itertools import combinations, product
from hashlib import sha256
from pathlib import Path
from datetime import datetime, timezone
import argparse
import json
import sys

sys.dont_write_bytecode = True
NEAR = Fraction(1, 10**12)


def parse_oa_raw_response(body, states):
    """Independently validate/reconstruct one bounded grouped OA response."""
    if not isinstance(body, bytes) or len(body) > 262144:
        raise ValueError('Invalid body type or response cap exceeded')
    def unique_object(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise ValueError('Duplicated JSON object key')
            obj[key] = value
        return obj
    raw = json.loads(body.decode('utf-8'), object_pairs_hook=unique_object)
    if not isinstance(raw, dict) or not isinstance(raw.get('meta'), dict):
        raise ValueError('Missing response/meta object')
    buckets = raw.get('group_by')
    if not isinstance(buckets, list) or len(buckets) > len(states) + 1:
        raise ValueError('Invalid group list')
    if 'results' in raw and raw['results'] != []:
        raise ValueError('Unrequested records returned')
    counts = {}
    for item in buckets:
        if not isinstance(item, dict) or item.get('key') not in set(states) | {'unknown'}:
            raise ValueError('Unexpected OA status')
        if item['key'] in counts:
            raise ValueError('Duplicated OA group')
        if any(isinstance(v, (dict, list)) for v in item.values()):
            raise ValueError('Nested grouping/payload')
        value = item.get('count')
        if type(value) is not int or value < 0:
            raise ValueError('Non-integer/negative/Boolean group count')
        counts[item['key']] = value
    n = raw['meta'].get('count')
    if type(n) is not int or n < 0 or sum(counts.values()) != n:
        raise ValueError('meta.count does not equal grouped integer total')
    for container in (raw, raw['meta']):
        if 'groups_count' in container and (type(container['groups_count']) is not int or container['groups_count'] != len(buckets)):
            raise ValueError('Wrong groups_count')
        if 'next_cursor' in container and container['next_cursor'] is not None:
            raise ValueError('Unfinished grouped pagination')
    m = counts.get('unknown', 0)
    known = {s: counts.get(s, 0) for s in states}
    d = sum(known.values())
    if n <= 0 or d <= 0 or n - m != d:
        raise ValueError('Nonpositive or inconsistent common denominator')
    return {'counts': known, 'N': n, 'D': d, 'M': m,
            'unknown_share': Fraction(m, n), 'returned_bucket_count': len(buckets)}


def rational(value):
    if not isinstance(value, str):
        raise ValueError('Exact numbers must be strings; binary floats and Boolean numbers are rejected')
    return Fraction(value)


def stringify(value):
    if isinstance(value, Fraction):
        return str(value)
    if isinstance(value, dict):
        return {key: stringify(val) for key, val in value.items()}
    if isinstance(value, (list, tuple)):
        return [stringify(val) for val in value]
    return value


def select(scores, priority, rule):
    if set(scores) != set(priority) or len(priority) != len(set(priority)):
        raise ValueError('Incomplete or duplicated priority')
    pos = {unit: i for i, unit in enumerate(priority)}
    if rule['kind'] == 'rank':
        k = rule['k']
        if type(k) is not int or not 1 <= k <= len(priority):
            raise ValueError('Invalid rank size')
        if rule['direction'] == 'lowest':
            order = sorted(priority, key=lambda u: (scores[u], pos[u]))
        elif rule['direction'] == 'highest':
            order = sorted(priority, key=lambda u: (-scores[u], pos[u]))
        else:
            raise ValueError('Invalid rank direction')
        chosen = set(order[:k])
    elif rule['kind'] == 'threshold':
        threshold = rational(rule['threshold'])
        comparisons = {'lt': lambda x: x < threshold,
                       'le': lambda x: x <= threshold,
                       'gt': lambda x: x > threshold,
                       'ge': lambda x: x >= threshold}
        chosen = {u for u in priority if comparisons[rule['operator']](scores[u])}
    else:
        raise ValueError('Unrecognised rule')
    return [u for u in priority if u in chosen]


def compare_sets(left, right, n, rule):
    if type(n) is not int or n <= 0:
        raise ValueError('Empty or invalid common universe')
    a, b = set(left), set(right)
    intersection, union = len(a & b), len(a | b)
    difference = len(a ^ b)
    rank_churn = None
    churn_status = 'not_applicable_to_rule_or_zero_k'
    if rule['kind'] == 'rank':
        k = rule['k']
        if not (k > 0 and len(a) == len(b) == k):
            raise ValueError('Rank cardinality mismatch')
        rank_churn = Fraction(difference, 2 * k)
        churn_status = 'defined_equal_positive_rank_size'
    return {'equal_sets': a == b, 'intersection_count': intersection,
            'union_count': union, 'symmetric_difference_count': difference,
            'jaccard': Fraction(intersection, union) if union else Fraction(1),
            'jaccard_status': 'defined_nonempty_union' if union else 'both_empty_convention_one',
            'normalised_symmetric_difference': Fraction(difference, n),
            'rank_churn': rank_churn, 'rank_churn_status': churn_status}


def parse_input(inp, protocol=None):
    if inp['schema_version'] != 'R13.1':
        raise ValueError('Unsupported normalised-input schema version')
    priority, states = inp['priority'], inp['states']
    if not priority or len(set(priority)) != len(priority):
        raise ValueError('Invalid unit priority')
    if not states or len(set(states)) != len(states):
        raise ValueError('Invalid states')
    if [r['id'] for r in inp['units']] != priority:
        raise ValueError('Input units differ from declared priority order')
    if inp['mixture_weighting'] != 'equal_eligible_units' or inp['primary_missing_policy'] != 'complete_known_states':
        raise ValueError('Wrong denominator or mixture convention')
    masses, totals, missing, denominator = {}, {}, {}, {}
    for row in inp['units']:
        u = row['id']
        if set(row['state_totals']) != set(states):
            raise ValueError('Missing or extra state')
        totals[u] = {s: rational(row['state_totals'][s]) for s in states}
        denominator[u] = rational(row['known_denominator'])
        if min(totals[u].values()) < 0 or denominator[u] <= 0 or sum(totals[u].values()) != denominator[u]:
            raise ValueError('Negative mass, nonpositive denominator or inconsistent total')
        masses[u] = {s: totals[u][s] / denominator[u] for s in states}
        if row['unresolved_total'] is None:
            if row['unresolved_status'] != 'not_identifiable':
                raise ValueError('Inconsistent unresolved label')
            missing[u] = None
        else:
            missing[u] = rational(row['unresolved_total'])
            if row['unresolved_status'] != 'known_nonnegative_total' or missing[u] < 0:
                raise ValueError('Invalid identified missing total')
    boundaries = {r['id']: set(r['states']) for r in inp['boundaries']}
    if len(boundaries) != len(inp['boundaries']):
        raise ValueError('Duplicated boundary')
    objective = inp['objective']
    if objective['id'] in boundaries:
        raise ValueError('Objective identifier collides with a boundary')
    sets = {**boundaries, objective['id']: set(objective['states'])}
    if any(not s <= set(states) for s in sets.values()):
        raise ValueError('Undefined state in definition')
    if inp['nested_boundaries'] is not True:
        raise ValueError('Registered boundaries must be nested')
    boundary_values = list(boundaries.values())
    if any(not a <= b for a, b in zip(boundary_values, boundary_values[1:])):
        raise ValueError('Non-nested boundaries')
    if protocol is not None:
        oa, common = protocol['oa'], protocol['common_contract']
        if inp['dataset_kind'] != 'OA' or inp['input_status'] != 'real_extension_input':
            raise ValueError('Not the real OA extension')
        if priority != oa['priority'] or states != oa['states']:
            raise ValueError('Registered OA roster/state order changed')
        if [r['id'] for r in inp['boundaries']] != oa['definition_order']:
            raise ValueError('Registered boundary order changed')
        if {k: set(v) for k, v in oa['definitions'].items()} != boundaries:
            raise ValueError('Registered boundary membership changed')
        if objective != {'id': oa['objective']['id'], 'states': oa['objective']['states']}:
            raise ValueError('Registered objective changed')
        if inp['rules'] != list(common['rules'].values()):
            raise ValueError('Registered rules changed')
        costs = [{'id': k, 'false_positive': v['false_inclusion'],
                  'false_negative': v['false_exclusion']} for k, v in common['cost_profiles'].items()]
        if inp['cost_profiles'] != costs:
            raise ValueError('Registered cost profiles changed')
        schedule = {'lowest_3': ['equal_costs'], 'highest_3': ['equal_costs'],
                    'below_one_quarter': ['equal_costs', 'exclusion_costly', 'inclusion_costly']}
        if inp['action_cost_profiles_by_rule'] != schedule:
            raise ValueError('Registered action-cost schedule changed')
        if any(v is None or v.denominator != 1 for v in missing.values()):
            raise ValueError('OA missing totals not identified integer counts')
        if any(t.denominator != 1 for rows in totals.values() for t in rows.values()):
            raise ValueError('OA known totals are not integer counts')
    return priority, states, masses, totals, denominator, missing, boundaries, sets


def point_expected(inp, protocol=None):
    priority, states, masses, totals, denominator, missing, boundaries, sets = parse_input(inp, protocol)
    n = len(priority)
    qid, qstates = inp['objective']['id'], set(inp['objective']['states'])
    rates = {name: {u: sum((masses[u][s] for s in subset), Fraction()) for u in priority}
             for name, subset in sets.items()}
    mixture = {s: sum(masses[u][s] for u in priority) / n for s in states}
    costs = {r['id']: (rational(r['false_positive']), rational(r['false_negative'])) for r in inp['cost_profiles']}
    if len(costs) != len(inp['cost_profiles']):
        raise ValueError('Duplicated cost identifier')
    if any(fp < 0 or fn < 0 for fp, fn in costs.values()):
        raise ValueError('Negative assumed cost')
    semantic = {}
    for name, subset in boundaries.items():
        fp = sum((mixture[s] for s in subset - qstates), Fraction())
        fn = sum((mixture[s] for s in qstates - subset), Fraction())
        semantic[name] = {costid: {'false_inclusion_mass': fp, 'false_exclusion_mass': fn,
                                  'semantic_loss': cf * fp + cn * fn}
                          for costid, (cf, cn) in costs.items()}
    rules = {}
    for rule in inp['rules']:
        rid = rule['id']
        if rid in rules:
            raise ValueError('Duplicated rule identifier')
        selections = {name: select(vector, priority, rule) for name, vector in rates.items()}
        pairwise = [{'left': a, 'right': b, **compare_sets(selections[a], selections[b], n, rule)}
                    for a, b in combinations(boundaries, 2)]
        obj_comp, obj_loss = {}, {}
        for name in boundaries:
            a, q = set(selections[name]), set(selections[qid])
            obj_comp[name] = compare_sets(a, q, n, rule)
            fp, fn = len(a - q), len(q - a)
            obj_loss[name] = {}
            for costid in inp['action_cost_profiles_by_rule'][rid]:
                cf, cn = costs[costid]
                loss = cf * fp + cn * fn
                obj_loss[name][costid] = {'false_selection_count': fp, 'missed_reference_count': fn,
                                         'action_loss_count_scale': loss, 'action_loss_per_unit': loss / n,
                                         'selected_count': len(a), 'reference_count': len(q)}
        rules[rid] = {'selected_sets': selections, 'pairwise_definition_comparisons': pairwise,
                      'objective_comparisons': obj_comp, 'objective_losses': obj_loss}
    return {'schema_version': inp['schema_version'], 'dataset_kind': inp['dataset_kind'],
            'input_status': inp['input_status'], 'release_status': 'working_only_not_release_approval',
            'unit_count': n, 'unit_ids': priority, 'mixture_weighting': 'equal_eligible_units',
            'rates': rates, 'mixture_masses': mixture, 'semantic': semantic, 'rules': rules}


def enumerate_box_membership(bounds, priority, k, direction):
    """Directly enumerate every k-subset and whether a point in the box admits it.

    For a proposed lowest-k set choose selected lower endpoints and excluded
    upper endpoints; the set is feasible iff every selected value is <= every
    excluded value. For highest-k choose the opposite endpoints. Intersections
    and unions are then the defining all-admissible guaranteed/possible sets.
    These are BOX statements, not feasibility claims about coupled country data.
    """
    n = len(priority)
    if not 1 <= k <= n or set(bounds) != set(priority):
        raise ValueError('Invalid box universe/rank size')
    if any(low > high for low, high in bounds.values()):
        raise ValueError('Empty coordinate interval')
    if direction not in ('lowest', 'highest'):
        raise ValueError('Invalid box direction')
    guaranteed, possible, examined, feasible = set(priority), set(), 0, 0
    for group in combinations(priority, k):
        examined += 1
        selected = set(group)
        excluded = set(priority) - selected
        if not excluded:
            allowed = True
        elif direction == 'lowest':
            allowed = max(bounds[u][0] for u in selected) <= min(bounds[u][1] for u in excluded)
        else:
            allowed = min(bounds[u][1] for u in selected) >= max(bounds[u][0] for u in excluded)
        if allowed:
            feasible += 1
            guaranteed &= selected
            possible |= selected
    if not feasible:
        raise ValueError('No admissible set in nonempty box')
    return {'guaranteed': [u for u in priority if u in guaranteed],
            'possible': [u for u in priority if u in possible],
            'ambiguous': [u for u in priority if u in possible - guaranteed],
            'excluded': [u for u in priority if u not in possible],
            'examined_subsets': examined, 'feasible_subsets': feasible}


def point_tie_expected(scores, priority, k, direction):
    ordered_values = sorted(scores.values(), reverse=direction == 'highest')
    gap = abs(ordered_values[k] - ordered_values[k - 1]) if k < len(priority) else None
    envelope = enumerate_box_membership({u: (scores[u], scores[u]) for u in priority}, priority, k, direction)
    return {'boundary_gap': gap, 'exact_boundary_tie': gap == 0 if gap is not None else False,
            'near_boundary_gap_le_1e_12': gap <= NEAR if gap is not None else False,
            **envelope}


def unknown_expected(inp, name, subset):
    priority, states, masses, totals, denominators, missing, boundaries, sets = parse_input(inp)
    intervals, coverage = {}, {}
    for u in priority:
        m, d = missing[u], denominators[u]
        if m is None:
            raise ValueError('Missing total not identified; sensitivity blocked')
        p = sum((totals[u][s] for s in subset), Fraction())
        n = d + m
        intervals[u] = (p / n, (p + m) / n)
        coverage[u] = {'N': n, 'D': d, 'M': m, 'unknown_share': m / n}
    envelope = enumerate_box_membership(intervals, priority, 3, 'lowest')
    guaranteed = [u for u in priority if intervals[u][1] < Fraction(1, 4)]
    excluded = [u for u in priority if intervals[u][0] >= Fraction(1, 4)]
    ambiguous = [u for u in priority if u not in guaranteed and u not in excluded]
    threshold = {'guaranteed': guaranteed, 'ambiguous': ambiguous, 'excluded': excluded,
                 'possible': [u for u in priority if u not in excluded]}
    return {'intervals': intervals, 'coverage': coverage, 'lowest_3': envelope,
            'below_one_quarter': threshold}


class Comparison:
    def __init__(self):
        self.checks = 0
        self.failures = []
        self.maximum_exact_numeric_residual = Fraction()

    def equal(self, path, actual, expected):
        self.checks += 1
        if isinstance(expected, Fraction):
            try:
                actual_num = rational(actual)
                residual = abs(actual_num - expected)
            except (ValueError, TypeError, ZeroDivisionError):
                self.failures.append({'path': path, 'reason': 'Not an exact-number string'})
                return
            self.maximum_exact_numeric_residual = max(self.maximum_exact_numeric_residual, residual)
            if residual:
                self.failures.append({'path': path, 'reason': 'Exact numeric disagreement', 'residual': str(residual)})
        elif isinstance(expected, dict):
            if not isinstance(actual, dict) or set(actual) != set(expected):
                self.failures.append({'path': path, 'reason': 'Dictionary key mismatch'})
                return
            for k, value in expected.items():
                self.equal(path + '/' + k, actual[k], value)
        elif isinstance(expected, (list, tuple)):
            if not isinstance(actual, list) or len(actual) != len(expected):
                self.failures.append({'path': path, 'reason': 'List type or size mismatch'})
                return
            for i, value in enumerate(expected):
                self.equal(path + '/' + str(i), actual[i], value)
        elif type(expected) is int and type(actual) is int:
            residual = abs(Fraction(actual - expected))
            self.maximum_exact_numeric_residual = max(self.maximum_exact_numeric_residual, residual)
            if residual:
                self.failures.append({'path': path, 'reason': 'Exact integer disagreement', 'residual': str(residual)})
        elif type(actual) is not type(expected) or actual != expected:
            self.failures.append({'path': path, 'reason': 'Value/type mismatch'})


def verify_point(inp, point, protocol=None):
    expected = point_expected(inp, protocol)
    comparison = Comparison()
    actual = {k: v for k, v in point.items() if k not in ('scope', 'identities')}
    comparison.equal('point', actual, expected)
    if not isinstance(point.get('scope'), str) or not point['scope']:
        comparison.failures.append({'path': 'point/scope', 'reason': 'Missing interpretation scope'})
    return comparison


def verify_secondary(inp, secondary):
    """Verify the declared R14.1 secondary layout with independent enumeration."""
    expected_point = point_expected(inp)
    priority = inp['priority']
    comparison = Comparison()
    enumerated_subsets = 0

    def members(path, actual, expected):
        nonlocal comparison
        wanted = {k: expected[k] for k in ('guaranteed', 'possible', 'excluded')}
        if 'ambiguous' in actual:
            wanted['ambiguous'] = expected.get('ambiguous', [u for u in priority if u in expected['possible'] and u not in expected['guaranteed']])
        comparison.equal(path, actual, wanted)

    ties = secondary['S5_point_ties']
    rank_rules = {r['id']: r for r in inp['rules'] if r['kind'] == 'rank'}
    comparison.equal('S5/rule_ids', list(ties), list(rank_rules))
    for rid, rule in rank_rules.items():
        comparison.equal('S5/' + rid + '/vector_ids', list(ties[rid]), list(expected_point['rates']))
        for name, scores in expected_point['rates'].items():
            actual = ties[rid][name]
            exp = point_tie_expected(scores, priority, rule['k'], rule['direction'])
            enumerated_subsets += exp['examined_subsets']
            path = 'S5/' + rid + '/' + name
            comparison.equal(path + '/boundary_gap', actual['boundary_gap'], exp['boundary_gap'])
            comparison.equal(path + '/boundary_exact_tie', actual['boundary_exact_tie'], exp['exact_boundary_tie'])
            comparison.equal(path + '/boundary_gap_at_most_1e_12', actual['boundary_gap_at_most_1e_12'], exp['near_boundary_gap_le_1e_12'])
            comparison.equal(path + '/fixed_priority_selected', actual['fixed_priority_selected'], select(scores, priority, rule))
            members(path + '/all_admissible_membership', actual['all_admissible_membership'], exp)
            comparison.equal(path + '/fields', sorted(actual), sorted(['boundary_gap','boundary_exact_tie',
                'boundary_gap_at_most_1e_12','fixed_priority_selected','all_admissible_membership']))

    unknown = secondary['S6_unknown']
    if not isinstance(unknown.get('scope'), str) or not unknown['scope']:
        comparison.failures.append({'path': 'S6/scope', 'reason': 'Missing marginal outer-envelope scope'})
    sets = {r['id']: set(r['states']) for r in inp['boundaries']}
    sets[inp['objective']['id']] = set(inp['objective']['states'])
    for section in ('intervals','lowest_3','below_one_quarter'):
        comparison.equal('S6/' + section + '/vector_ids', list(unknown[section]), list(sets))
    for name, subset in sets.items():
        exp = unknown_expected(inp, name, subset)
        enumerated_subsets += exp['lowest_3']['examined_subsets']
        comparison.equal('S6/' + name + '/intervals', unknown['intervals'][name], exp['intervals'])
        members('S6/' + name + '/lowest_3', unknown['lowest_3'][name], exp['lowest_3'])
        members('S6/' + name + '/below_one_quarter', unknown['below_one_quarter'][name], exp['below_one_quarter'])
    return comparison, enumerated_subsets


def sha(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--protocol', required=True, type=Path)
    p.add_argument('--input', required=True, type=Path)
    p.add_argument('--point', required=True, type=Path)
    p.add_argument('--report', required=True, type=Path)
    args = p.parse_args()
    protocol, inp, point = [json.loads(path.read_bytes()) for path in (args.protocol, args.input, args.point)]
    comparison = verify_point(inp, point, protocol)
    report = {'status': 'PASS_INDEPENDENT_POINT_VERIFICATION' if not comparison.failures else 'FAIL_INDEPENDENT_POINT_VERIFICATION',
              'created_utc': datetime.now(timezone.utc).isoformat(), 'runtime': sys.version.split()[0],
              'comparisons': comparison.checks, 'maximum_exact_numeric_residual': str(comparison.maximum_exact_numeric_residual),
              'failures': comparison.failures, 'identities': {k: sha(getattr(args, k)) for k in ('protocol', 'input', 'point')},
              'verifier_sha256': sha(__file__), 'scope': 'New recovery implementation, exact point calculations from the supplied normalised input; no producer/core imports',
              'limits': ['Historical R14 results were already known; no blinding claim.',
                         'This point-only entry point does not establish raw-source extraction, secondary-envelope correctness or native Windows acceptance.']}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if not comparison.failures else 1)


if __name__ == '__main__':
    main()
