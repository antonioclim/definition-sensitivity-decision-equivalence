"""Derive exact and display tables from verified R14.1 public OA outputs."""
from pathlib import Path
from fractions import Fraction as F
from decimal import Decimal, localcontext, ROUND_HALF_EVEN
from hashlib import sha256
import argparse
import json


def decimal6(raw):
    q = F(raw)
    with localcontext() as context:
        context.prec = max(80, len(str(abs(q.numerator))) + len(str(q.denominator)) + 20)
        return str((Decimal(q.numerator) / Decimal(q.denominator)).quantize(Decimal('0.000001'), rounding=ROUND_HALF_EVEN))


def scientific(raw):
    q = F(raw)
    with localcontext() as context:
        context.prec = 50
        return format(Decimal(q.numerator) / Decimal(q.denominator), '.8E')


def make_tables(input_path, point_path, secondary_path, coverage_path):
    x, p, s, coverage = [json.loads(Path(k).read_bytes()) for k in (input_path, point_path, secondary_path, coverage_path)]
    definitions = [d['id'] for d in x['boundaries']]
    objective = x['objective']['id']
    labels = dict(zip(definitions, ['D1', 'D2', 'D3'])); labels[objective] = 'Q'
    semantic = []
    for d in definitions:
        for cost in x['cost_profiles']:
            v = p['semantic'][d][cost['id']]
            semantic.append({'definition': labels[d], 'definition_id': d, 'cost': cost['id'],
                             'false_inclusion_exact': v['false_inclusion_mass'],
                             'false_exclusion_exact': v['false_exclusion_mass'],
                             'loss_exact': v['semantic_loss'],
                             'false_inclusion': decimal6(v['false_inclusion_mass']),
                             'false_exclusion': decimal6(v['false_exclusion_mass']),
                             'loss': decimal6(v['semantic_loss'])})
    selections = []; objective_rows = []; pairwise = []
    for rule in x['rules']:
        r = p['rules'][rule['id']]
        for d, selected in r['selected_sets'].items():
            selections.append({'rule': rule['id'], 'definition': labels[d], 'selected': selected, 'count': len(selected)})
        for d in definitions:
            for cost_id, loss in r['objective_losses'][d].items():
                objective_rows.append({'rule': rule['id'], 'definition': labels[d], 'cost': cost_id,
                                       **loss, **r['objective_comparisons'][d],
                                       'action_loss_per_unit_display': decimal6(loss['action_loss_per_unit'])})
        for row in r['pairwise_definition_comparisons']:
            pairwise.append({'rule': rule['id'], 'left_label': labels[row['left']], 'right_label': labels[row['right']],
                             'left_count': len(r['selected_sets'][row['left']]),
                             'right_count': len(r['selected_sets'][row['right']]), **row})
    ties = []
    for rule, vectors in s['S5_point_ties'].items():
        for vector, row in vectors.items():
            envelope = row['all_admissible_membership']
            ties.append({'rule': rule, 'definition': labels[vector], **row,
                         'boundary_gap_display': scientific(row['boundary_gap']),
                         'guaranteed_count': len(envelope['guaranteed']), 'possible_count': len(envelope['possible'])})
    missing = []
    for rule in ['lowest_3', 'below_one_quarter']:
        for vector, row in s['S6_unknown'][rule].items():
            missing.append({'rule': rule, 'definition': labels[vector], **row,
                            'guaranteed_count': len(row['guaranteed']), 'possible_count': len(row['possible']),
                            'ambiguous_count': len(set(row['possible']) - set(row['guaranteed'])),
                            'excluded_count': len(row['excluded'])})
    by_country = {row['unit_id']: row for row in coverage['countries']}
    countries = []
    for unit in x['units']:
        g = unit['id']; c = by_country[g]
        countries.append({'country': g, 'country_name': c['country_name'], 'N': c['N'], 'D': c['D'], 'M': c['M'],
                          'missing_share': decimal6(c['missing_OA_share']), 'missing_share_exact': c['missing_OA_share'],
                          'rates': {labels[d]: {'exact': p['rates'][d][g], 'display': decimal6(p['rates'][d][g])} for d in labels}})
    return {'schema_version': 'R14.1-reporting-1.0',
            'input_sha256': sha256(Path(input_path).read_bytes()).hexdigest(),
            'point_sha256': sha256(Path(point_path).read_bytes()).hexdigest(),
            'secondary_sha256': sha256(Path(secondary_path).read_bytes()).hexdigest(),
            'rounding': 'Six decimal places, nearest with ties to even, using exact rational inputs. Exact values are retained.',
            'definition_labels': labels, 'semantic': semantic, 'selections': selections,
            'objective_comparisons': objective_rows, 'pairwise_comparisons': pairwise,
            'point_ties': ties, 'unknown_membership': missing, 'countries': countries,
            'scope': 'Every registered family is retained; tables do not change the underlying exact comparisons.'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ['input', 'point', 'secondary', 'coverage', 'output']:
        p.add_argument('--' + name, required=True, type=Path)
    a = p.parse_args()
    if a.output.exists():
        raise SystemExit('Use a new reporting output path')
    data = make_tables(a.input, a.point, a.secondary, a.coverage)
    a.output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
