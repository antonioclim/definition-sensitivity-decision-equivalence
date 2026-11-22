"""Check the normalised workflow against hand-worked synthetic expectations.

No empirical source, external service or simulation engine is accessed.
"""
from pathlib import Path
from fractions import Fraction as F
import copy
import hashlib
import json
import sys
import importlib.metadata
from jsonschema import ValidationError, Draft202012Validator
import execute_state_contract as runner

ROOT=Path(__file__).resolve().parent
def main():
    x=json.loads((ROOT/'R13_SYNTHETIC_INPUT.json').read_text())
    result=runner.execute(x)
    checks=[]
    def check(name,condition):
        checks.append({'id':name,'status':'PASS' if condition else 'FAIL'})
        if not condition:raise AssertionError(name)
    expected={
        'lowest3':{'narrow':{'a','b','c'},'middle':{'a','b','e'},'broad':{'a','b','g'},'platform_or_more':{'b','e','g'}},
        'highest3':{'narrow':{'d','f','h'},'middle':{'c','d','f'},'broad':{'d','e','f'},'platform_or_more':{'c','d','f'}},
        'below025':{'narrow':{'a','b','c','d','e','g','h'},'middle':{'a','b','e','g'},'broad':set(),'platform_or_more':{'b'}}}
    for rule,sets in expected.items():
        for boundary,selected in sets.items():
            check('hand_selection_'+rule+'_'+boundary,result['rules'][rule]['selected_sets'][boundary]==selected)
    for boundary,expected_loss in [('narrow',F(1,4)),('middle',F(17,160)),('broad',F(7,32))]:
        check('hand_semantic_'+boundary,result['semantic'][boundary]['equal']['semantic_loss']==expected_loss)
    losses={'lowest3':{'narrow':F(1,2),'middle':F(1,4),'broad':F(1,4)},
        'highest3':{'narrow':F(1,4),'middle':F(0),'broad':F(1,4)},
        'below025':{'narrow':F(3,4),'middle':F(3,8),'broad':F(1,8)}}
    for rule,values in losses.items():
        for boundary,v in values.items():
            check('hand_action_loss_'+rule+'_'+boundary,result['rules'][rule]['objective_losses'][boundary]['equal']['action_loss_per_unit']==v)
    threshold=result['rules']['below025']
    check('threshold_cost_asymmetry_false_negative',threshold['objective_losses']['broad']['miss_costly']['action_loss_per_unit']==F(1,4))
    check('threshold_cost_asymmetry_false_positive',threshold['objective_losses']['narrow']['include_costly']['action_loss_per_unit']==F(3,2))
    check('threshold_churn_absent',all(v['rank_churn'] is None for v in threshold['pairwise_definition_comparisons']))
    check('strict_threshold_leaves_equal_quarter_unselected',result['rates']['platform_or_more']['e']==F(1,4) and 'e' not in threshold['selected_sets']['platform_or_more'])
    check('empty_pairwise_union_not_present_in_this_fixture',all(v['union_count']>0 for v in threshold['pairwise_definition_comparisons']))
    check('synthetic_source_identity',hashlib.sha256((ROOT/'R13_SYNTHETIC_SOURCE_ROWS.json').read_bytes()).hexdigest()==x['provenance']['source_sha256'])
    def rejected(name,mutator):
        bad=copy.deepcopy(x);mutator(bad)
        try:runner.execute(bad)
        except (ValueError,ValidationError):check(name,True)
        else:check(name,False)
    rejected('reject_source_status_mislabel',lambda z:z.update(dataset_kind='FAT'))
    rejected('reject_unknown_schema_field',lambda z:z.update(extra_field='unregistered'))
    rejected('reject_changed_known_denominator',lambda z:z['units'][0].update(known_denominator='101'))
    rejected('reject_mismatched_state_register',lambda z:z['units'][0]['state_totals'].update(other='1'))
    rejected('reject_duplicate_unit',lambda z:z['units'][1].update(id='a'))
    rejected('reject_missing_common_priority',lambda z:z['priority'].pop())
    rejected('reject_non_nested_definitions',lambda z:z['boundaries'][0].update(states=['manual']))
    rejected('reject_unregistered_objective_state',lambda z:z['objective'].update(states=['absent']))
    rejected('reject_missing_rule_cost_mapping',lambda z:z['action_cost_profiles_by_rule'].pop('lowest3'))
    rejected('reject_zero_registered_cost',lambda z:z['cost_profiles'][0].update(false_positive='0'))
    rejected('reject_unidentified_unknown_as_zero',lambda z:z['units'][0].update(unresolved_status='not_identifiable'))
    rejected('reject_rank_size_outside_cohort',lambda z:z['rules'][0].update(k=9))
    out_json=json.loads(json.dumps(result,default=runner.serial))
    Draft202012Validator(json.loads((ROOT/'R13_STATE_OUTPUT.schema.json').read_text())).validate(out_json)
    check('output_schema',True)
    report={'status':'PASS','test_count':len(checks),'checks':checks,'runtime_python':sys.version.split()[0],
        'jsonschema_version':importlib.metadata.version('jsonschema'),'scope':'Eight synthetic units, hand-worked outcomes and deliberate invalid-input cases only',
        'new_empirical_analyses':0,'new_MC_replications':0,
        'identities':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in [
            'odsa_contract_core.py','execute_state_contract.py','check_state_contract.py',
            'R13_STATE_INPUT.schema.json','R13_STATE_OUTPUT.schema.json','R13_SYNTHETIC_INPUT.json']}}
    (ROOT/'R13_STATE_CONTRACT_CHECKS.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ['status','test_count','runtime_python','jsonschema_version','new_empirical_analyses','new_MC_replications']}))

if __name__=='__main__':main()
