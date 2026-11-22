"""Verify the R13 exact reference core against independent finite oracles.

Reads only synthetic specifications and mathematical oracle files. No data API,
FAT input, simulation engine or manuscript is accessed. Writes one local report.
"""
from pathlib import Path
from fractions import Fraction as F
import hashlib
import json
import sys
import odsa_contract_core as core

ROOT=Path(__file__).resolve().parent
ORACLES=ROOT/'R13_INTERVAL_MEMBERSHIP_ORACLES.json'

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def serial(x):
    if isinstance(x,F):return str(x)
    if isinstance(x,(set,frozenset)):return sorted(x)
    raise TypeError(type(x).__name__)

def main():
    tests=[]
    def check(name,ok,details=None):
        tests.append({'id':name,'status':'PASS' if ok else 'FAIL','details':details})
        if not ok:raise AssertionError(name)
    def invalid(name,fn):
        try:fn()
        except ValueError:check(name,True)
        else:check(name,False)
    states=['manual','standard','platform','specialised','integrated']
    totals=dict(zip(states,[20,30,10,25,15]))
    p=core.state_masses(states,totals)
    check('exact_mass_normalisation',sum(p.values())==1 and p['specialised']==F(1,4))
    narrow=['integrated'];mid=['specialised','integrated'];broad=states[1:];objective=states[2:]
    check('nested_additivity',core.rate(p,broad)-core.rate(p,mid)==F(2,5))
    s=core.semantic_loss(p,broad,objective,(1,1))
    check('semantic_known_false_inclusion',s=={'false_inclusion_mass':F(3,10),'false_exclusion_mass':F(0),'semantic_loss':F(3,10)})
    s=core.semantic_loss(p,narrow,objective,(1,4))
    check('semantic_weighted_false_exclusion',s['false_exclusion_mass']==F(7,20) and s['semantic_loss']==F(7,5))
    zero=core.semantic_loss(p,broad,objective,(0,1))
    check('zero_cost_does_not_establish_alignment',zero['false_inclusion_mass']>0 and zero['semantic_loss']==0)
    scores={'u0':F(1,4),'u1':F(1,4),'u2':F(1,2)};priority=['u1','u0','u2']
    check('threshold_lt_excludes_boundary',core.select(scores,{'kind':'threshold','operator':'lt','threshold':'1/4'},priority)==set())
    check('threshold_ge_includes_boundary',core.select(scores,{'kind':'threshold','operator':'ge','threshold':'1/4'},priority)==set(scores))
    check('lowest_fixed_priority',core.select(scores,{'kind':'rank','direction':'lowest','k':1},priority)=={'u1'})
    check('highest_fixed_priority',core.select(scores,{'kind':'rank','direction':'highest','k':2},priority)=={'u2','u1'})
    check('zero_selection_cardinality',core.select(scores,{'kind':'rank','direction':'highest','k':0},priority)==set())
    selected={'u0','u2'};reference={'u1','u2'}
    a=core.action_loss(selected,reference,scores,(2,1))
    check('action_costs_and_universe_denominator',a['false_selection_count']==a['missed_reference_count']==1 and a['action_loss_count_scale']==3 and a['action_loss_per_unit']==1,a)
    comparison=core.compare_sets(selected,reference,scores,rank_k=2)
    check('jaccard_and_churn_different_denominators',comparison['jaccard']==F(1,3) and comparison['rank_churn']==F(1,2) and comparison['normalised_symmetric_difference']==F(2,3),comparison)
    empty=core.compare_sets(set(),set(),scores)
    check('historic_empty_jaccard_convention_flagged',empty['jaccard']==1 and empty['jaccard_status']=='both_empty_convention_one' and empty['equal_sets'] and empty['rank_churn'] is None,empty)
    threshold_equal=core.compare_sets({'u0'},{'u1'},scores)
    check('equal_size_threshold_sets_do_not_implicitly_report_rank_churn',threshold_equal['rank_churn'] is None)
    c=core.compare_sets({'u0'},{'u0','u1'},scores)
    check('unequal_size_churn_not_reported',c['rank_churn'] is None)
    same=core.compare_sets({'u0'},{'u0'},scores)
    wrong=core.action_loss({'u0'},{'u1'},scores,(1,1))
    check('same_definition_sets_can_both_miss_objective',same['equal_sets'] and wrong['action_loss_count_scale']==2)
    invalid('reject_inconsistent_rank_cardinality',lambda:core.compare_sets({'u0'},{'u1','u2'},scores,rank_k=1))
    invalid('reject_float_implicit_binary',lambda:core.rational(0.1))
    invalid('reject_negative_total',lambda:core.state_masses(['a','b'],{'a':-1,'b':2}))
    invalid('reject_zero_denominator',lambda:core.state_masses(['a'],{'a':0}))
    invalid('reject_extra_state',lambda:core.state_masses(['a'],{'a':1,'b':1}))
    invalid('reject_duplicate_boundary',lambda:core.rate(p,['manual','manual']))
    invalid('reject_invalid_mass_sum',lambda:core.rate({'a':'1/2'},['a']))
    invalid('reject_different_priority_universe',lambda:core.select(scores,{'kind':'rank','direction':'highest','k':1},['u0','u1']))
    invalid('reject_k_above_size',lambda:core.select(scores,{'kind':'rank','direction':'highest','k':4},priority))
    invalid('reject_negative_cost',lambda:core.action_loss(set(),set(),scores,(-1,1)))
    invalid('reject_other_unit_in_action',lambda:core.action_loss({'outside'},set(),scores))
    interval=core.unresolved_rate_interval(20,80,20)
    check('unknown_mass_envelope_uses_full_denominator',interval==(F(1,5),F(2,5)))
    bounds={'a':('0','1/5'),'b':('1/4','1/4'),'c':interval}
    below=core.threshold_membership(bounds,'1/4','lt')
    check('unknown_threshold_strict_boundary',below=={'guaranteed':frozenset({'a'}),'possible':frozenset({'a','c'}),'excluded':frozenset({'b'})})
    above=core.threshold_membership(bounds,'1/4','ge')
    check('unknown_threshold_complement',above=={'guaranteed':frozenset({'b'}),'possible':frozenset({'b','c'}),'excluded':frozenset({'a'})})
    invalid('reject_unknown_zero_total_denominator',lambda:core.unresolved_rate_interval(0,0,0))
    invalid('reject_known_positives_above_denominator',lambda:core.unresolved_rate_interval(4,3,2))
    invalid('reject_reversed_threshold_interval',lambda:core.threshold_membership({'a':(2,1)},'1/4'))
    oracle=json.loads(ORACLES.read_text(encoding='utf-8'))
    comparisons=[]
    for case in oracle['cases']:
        box={i:pair for i,pair in enumerate(case['bounds'])}
        observed=core.interval_membership(box,case['k'],case['direction'],case['tie_mode'],case['priority'])
        passed=(observed['guaranteed']==set(case['expected_guaranteed']) and observed['possible']==set(case['expected_possible']))
        comparisons.append({'case_id':case['case_id'],'pass':passed})
        if not passed:raise AssertionError('Independent oracle mismatch: '+case['case_id'])
    check('independent_interval_oracles',all(c['pass'] for c in comparisons),{'cases':len(comparisons)})
    result={'status':'PASS','scope':'Reference contract operations on synthetic examples and finite independent oracles only',
        'direct_checks_including_oracle_batch':len(tests),'independent_oracle_cases':len(comparisons),
        'checks':tests,'oracle_comparisons':comparisons,'identities':{'core_sha256':digest(ROOT/'odsa_contract_core.py'),'checker_sha256':digest(Path(__file__)),'oracles_sha256':digest(ORACLES)},
        'runtime_python':sys.version.split()[0],'new_empirical_analyses':0,'new_MC_replications':0,
        'limitations':['Finite tests do not prove general theorems.','No native Windows execution.','No input adapters or empirical source reconstruction validated here.']}
    (ROOT/'R13_CONTRACT_CORE_CHECKS.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,default=serial)+'\n',encoding='utf-8')
    print(json.dumps({k:result[k] for k in ('status','direct_checks_including_oracle_batch','independent_oracle_cases','runtime_python','new_empirical_analyses','new_MC_replications')},indent=2))

if __name__=='__main__':main()
