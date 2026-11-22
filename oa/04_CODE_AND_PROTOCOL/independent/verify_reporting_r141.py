"""Independent exact source-to-table and decimal mapping review for R14.1.

No producer, formatter or Decimal arithmetic is imported. Rounding uses integer
quotients and remainders, including ties-to-even and scientific mantissas.
"""
from pathlib import Path
from fractions import Fraction
from hashlib import sha256
from datetime import datetime, timezone
import argparse
import json
import sys
sys.dont_write_bytecode = True
from r141_independent_math import (Comparison, point_expected, point_tie_expected,
                                 unknown_expected, select, parse_oa_raw_response)


def rounded_integer(value):
    negative = value < 0
    value = abs(value)
    q,r = divmod(value.numerator,value.denominator)
    if 2*r > value.denominator or (2*r == value.denominator and q%2):
        q += 1
    return -q if negative else q


def fixed(value,places=6):
    scaled = abs(rounded_integer(value * 10**places))
    whole,decimal = divmod(scaled,10**places)
    return ('-' if value<0 else '') + str(whole) + '.' + str(decimal).zfill(places)


def scientific(value,places=8):
    if value == 0:
        # Decimal's fixed mantissa display for an exactly unscaled zero.
        return '0.' + '0'*places + 'E+' + str(places)
    a = abs(value)
    exponent = len(str(a.numerator))-len(str(a.denominator))
    if exponent >= 0:
        if a.numerator < a.denominator * 10**exponent:
            exponent -= 1
    elif a.numerator * 10**(-exponent) < a.denominator:
        exponent -= 1
    shift = places-exponent
    scaled = a * 10**shift if shift>=0 else a / 10**(-shift)
    rounded = rounded_integer(scaled)
    if rounded >= 10**(places+1):
        rounded //= 10
        exponent += 1
    whole,decimal = divmod(rounded,10**places)
    return ('-' if value<0 else '') + str(whole) + '.' + str(decimal).zfill(places) + 'E' + ('+' if exponent>=0 else '') + str(exponent)


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('protocol','input','point','secondary','coverage','batch','tables','report'):
        p.add_argument('--'+name,required=True,type=Path)
    args=p.parse_args()
    load=lambda path:json.loads(path.read_bytes())
    protocol,inp,point,secondary,coverage,batch,tables=[load(path) for path in
        (args.protocol,args.input,args.point,args.secondary,args.coverage,args.batch,args.tables)]
    model=point_expected(inp,protocol)
    labels={name:'D'+str(i+1) for i,name in enumerate(protocol['oa']['definition_order'])}
    labels[protocol['oa']['objective']['id']]='Q'
    c=Comparison()
    c.equal('labels',tables['definition_labels'],labels)
    c.equal('input_identity',tables['input_sha256'],digest(args.input))
    c.equal('point_identity',tables['point_sha256'],digest(args.point))
    c.equal('secondary_identity',tables['secondary_sha256'],digest(args.secondary))
    c.equal('schema',tables['schema_version'],'R14.1-reporting-1.0')
    rounding_controls=[(Fraction(1,2000000),'0.000000'),(Fraction(3,2000000),'0.000002'),
                       (Fraction(5,2000000),'0.000002'),(Fraction(-1,2000000),'-0.000000'),
                       (Fraction(9999995,10000000),'1.000000')]
    for index,(value,wanted) in enumerate(rounding_controls):
        c.equal('rounding_control/' + str(index),fixed(value),wanted)
    c.equal('scientific_control/third',scientific(Fraction(1,3)),'3.33333333E-1')
    c.equal('scientific_control/carry',scientific(Fraction(9999999995,10**10)),'1.00000000E+0')
    semantic=[]
    for name,costs in model['semantic'].items():
        for cost,values in costs.items():
            fp,fn,loss=[values[key] for key in ('false_inclusion_mass','false_exclusion_mass','semantic_loss')]
            semantic.append({'definition':labels[name],'definition_id':name,'cost':cost,
                             'false_inclusion_exact':fp,'false_exclusion_exact':fn,'loss_exact':loss,
                             'false_inclusion':fixed(fp),'false_exclusion':fixed(fn),'loss':fixed(loss)})
    c.equal('semantic',tables['semantic'],semantic)
    selections=[];objective=[];pairwise=[]
    for rid,rule in model['rules'].items():
        for name,chosen in rule['selected_sets'].items():
            selections.append({'rule':rid,'definition':labels[name],'selected':chosen,'count':len(chosen)})
        for name,bycost in rule['objective_losses'].items():
            for cost,loss in bycost.items():
                objective.append({'rule':rid,'definition':labels[name],'cost':cost,**loss,
                                  **rule['objective_comparisons'][name],
                                  'action_loss_per_unit_display':fixed(loss['action_loss_per_unit'])})
        for row in rule['pairwise_definition_comparisons']:
            pairwise.append({'rule':rid,'left_label':labels[row['left']],'right_label':labels[row['right']],
                             'left_count':len(rule['selected_sets'][row['left']]),
                             'right_count':len(rule['selected_sets'][row['right']]),**row})
    c.equal('selections',tables['selections'],selections)
    c.equal('objective_comparisons',tables['objective_comparisons'],objective)
    c.equal('pairwise_comparisons',tables['pairwise_comparisons'],pairwise)
    point_ties=[]
    for rule in inp['rules']:
        if rule['kind']!='rank':continue
        for name,vector in model['rates'].items():
            exp=point_tie_expected(vector,inp['priority'],rule['k'],rule['direction'])
            point_ties.append({'rule':rule['id'],'definition':labels[name],
                               'boundary_gap':exp['boundary_gap'],'boundary_exact_tie':exp['exact_boundary_tie'],
                               'boundary_gap_at_most_1e_12':exp['near_boundary_gap_le_1e_12'],
                               'fixed_priority_selected':select(vector,inp['priority'],rule),
                               'all_admissible_membership':{key:exp[key] for key in ('guaranteed','possible','excluded')},
                               'boundary_gap_display':scientific(exp['boundary_gap']),
                               'guaranteed_count':len(exp['guaranteed']),'possible_count':len(exp['possible'])})
    c.equal('point_ties',tables['point_ties'],point_ties)
    subsets={r['id']:set(r['states']) for r in inp['boundaries']}
    subsets[inp['objective']['id']]=set(inp['objective']['states'])
    envelopes={name:unknown_expected(inp,name,subset) for name,subset in subsets.items()}
    unknown_rows=[]
    for rid in ('lowest_3','below_one_quarter'):
        for name,full in envelopes.items():
            env=full[rid]
            unknown_rows.append({'rule':rid,'definition':labels[name],
                                 **{key:env[key] for key in ('guaranteed','possible','excluded')},
                                 'guaranteed_count':len(env['guaranteed']),
                                 'possible_count':len(env['possible']),
                                 'ambiguous_count':len(set(env['possible'])-set(env['guaranteed'])),
                                 'excluded_count':len(env['excluded'])})
    c.equal('unknown_membership',tables['unknown_membership'],unknown_rows)
    country_names={r['code']:r['name'] for r in protocol['oa']['cohort']['countries']}
    raw_by_id={r['unit_id']:r for r in batch['entries']}
    countries=[];coverage_rows=[]
    for row in inp['units']:
        unit=row['id'];entry=raw_by_id[unit]
        raw=parse_oa_raw_response((args.batch.parent/entry['raw_file']).read_bytes(),inp['states'])
        coverage_rows.append({'unit_id':unit,'country_name':country_names[unit],
                              'N':raw['N'],'M':raw['M'],'D':raw['D'],
                              'counts':{**raw['counts'],'unknown':raw['M']},
                              'returned_bucket_count':raw['returned_bucket_count'],
                              'missing_OA_share':raw['unknown_share']})
        countries.append({'country':unit,'country_name':country_names[unit],
                          'N':raw['N'],'D':raw['D'],'M':raw['M'],
                          'missing_share':fixed(raw['unknown_share']),'missing_share_exact':raw['unknown_share'],
                          'rates':{labels[name]:{'exact':vector[unit],'display':fixed(vector[unit])}
                                   for name,vector in model['rates'].items()}})
    c.equal('coverage/countries',coverage['countries'],coverage_rows)
    c.equal('coverage/batch_identity',coverage['batch_sha256'],digest(args.batch))
    c.equal('countries',tables['countries'],countries)
    report={'status':'PASS_INDEPENDENT_OA_REPORTING_MAPPING' if not c.failures else 'FAIL_INDEPENDENT_OA_REPORTING_MAPPING',
            'created_utc':datetime.now(timezone.utc).isoformat(),
            'comparisons':c.checks,'maximum_exact_numeric_residual':str(c.maximum_exact_numeric_residual),
            'failures':c.failures,'rounding_method':'Integer quotient/remainder, ties to even; no Decimal or producer/table-formatter import',
            'display_controls':len(rounding_controls)+2,
            'coverage':'All nine semantic rows, twelve selections, fifteen objective/cost rows, nine d/d rows with both cardinalities, eight S5 rows, eight S6 rows and all27 country rates/coverage',
            'identities':{name:digest(getattr(args,name)) for name in ('protocol','input','point','secondary','coverage','batch','tables')},
            'verifier_sha256':digest(Path(__file__)),
            'math_module_sha256':digest(Path(__file__).with_name('r141_independent_math.py')),
            'limits':'JSON source-to-report mapping and exact display verification. This is not a DOCX page inspection or native Microsoft Word acceptance.'}
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('status','comparisons','maximum_exact_numeric_residual','failures')},indent=2))
    raise SystemExit(0 if not c.failures else 1)


if __name__=='__main__':main()
