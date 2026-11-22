"""Validate and execute a normalised comparison contract; no data acquisition.

The default input is a toy fixture. A real input requires independent adapter
reconciliation before this contract is appropriate. The output remains a local
working result, not disclosure or publication approval. Requires jsonschema.
"""
from pathlib import Path
from fractions import Fraction as F
from itertools import combinations
import hashlib
import json
import sys
from jsonschema import Draft202012Validator
import odsa_contract_core as core

ROOT=Path(__file__).resolve().parent

def serial(x):
    if isinstance(x,F):return str(x)
    if isinstance(x,(set,frozenset)):return sorted(x)
    raise TypeError(type(x).__name__)

def semantic_validation(x):
    Draft202012Validator(json.loads((ROOT/'R13_STATE_INPUT.schema.json').read_text())).validate(x)
    is_toy=x['dataset_kind']=='TOY'
    if is_toy!=(x['input_status']=='synthetic_fixture') or is_toy!=(x['provenance']['adapter_status']=='synthetic_construction'):
        raise ValueError('Synthetic and real-source status must be consistent')
    states=x['states']; ids=[u['id'] for u in x['units']]
    if len(ids)!=len(set(ids)) or set(x['priority'])!=set(ids) or len(x['priority'])!=len(ids):
        raise ValueError('Unique units and one complete common priority required')
    for u in x['units']:
        if set(u['state_totals'])!=set(states):raise ValueError('State total keys must exactly match the register')
        vals=list(map(core.rational,u['state_totals'].values()))
        if any(v<0 for v in vals) or sum(vals)<=0:raise ValueError('Nonnegative totals and positive known denominator required')
        if core.rational(u['known_denominator'])!=sum(vals):raise ValueError('Known denominator does not equal known state totals')
        if (u['unresolved_status']=='not_identifiable')!=(u['unresolved_total'] is None):raise ValueError('Unresolved status inconsistent')
        if u['unresolved_total'] is not None and core.rational(u['unresolved_total'])<0:raise ValueError('Negative unresolved total')
    boundary_ids=[d['id'] for d in x['boundaries']]
    if len(boundary_ids)!=len(set(boundary_ids)) or x['objective']['id'] in boundary_ids:raise ValueError('Boundary/objective identifiers must be distinct')
    subsets=[set(d['states']) for d in x['boundaries']]
    if any(not s<=set(states) for s in subsets+[set(x['objective']['states'])]):raise ValueError('Unregistered state')
    if any(not a<=b for a,b in zip(subsets,subsets[1:])):raise ValueError('Boundaries not nested in recorded order')
    rule_ids=[r['id'] for r in x['rules']]
    cost_ids=[c['id'] for c in x['cost_profiles']]
    if len(rule_ids)!=len(set(rule_ids)) or len(cost_ids)!=len(set(cost_ids)):raise ValueError('Repeated rule or cost identifier')
    if set(x['action_cost_profiles_by_rule'])!=set(rule_ids):raise ValueError('Every rule needs an explicit cost profile list')
    for chosen in x['action_cost_profiles_by_rule'].values():
        if not set(chosen)<=set(cost_ids):raise ValueError('Unknown cost profile')
    for c in x['cost_profiles']:
        if min(core.rational(c['false_positive']),core.rational(c['false_negative']))<=0:
            raise ValueError('Registered extension costs are strictly positive')
    for r in x['rules']:
        if r['kind']=='rank' and r['k']>len(ids):raise ValueError('Rank cardinality exceeds universe')
        if r['kind']=='threshold' and not 0<=core.rational(r['threshold'])<=1:raise ValueError('Threshold outside unit-rate range')
    return ids

def execute(x):
    ids=semantic_validation(x)
    masses={u['id']:core.state_masses(x['states'],u['state_totals']) for u in x['units']}
    mixture={s:sum((p[s] for p in masses.values()),F(0))/len(ids) for s in x['states']}
    definitions={d['id']:d['states'] for d in x['boundaries']}
    objective_id=x['objective']['id']
    all_sets={**definitions,objective_id:x['objective']['states']}
    scores={d:{g:core.rate(masses[g],s) for g in ids} for d,s in all_sets.items()}
    costs={c['id']:(c['false_positive'],c['false_negative']) for c in x['cost_profiles']}
    semantic={d:{c:core.semantic_loss(mixture,s,x['objective']['states'],v) for c,v in costs.items()} for d,s in definitions.items()}
    rules={}
    for r in x['rules']:
        selections={d:core.select(p,r,x['priority']) for d,p in scores.items()}
        rank_k=r['k'] if r['kind']=='rank' else None
        pairwise=[{'left':a,'right':b,**core.compare_sets(selections[a],selections[b],ids,rank_k)} for a,b in combinations(definitions,2)]
        losses={d:{c:core.action_loss(selections[d],selections[objective_id],ids,costs[c]) for c in x['action_cost_profiles_by_rule'][r['id']]} for d in definitions}
        against_objective={d:core.compare_sets(selections[d],selections[objective_id],ids,rank_k) for d in definitions}
        rules[r['id']]={'selected_sets':selections,'pairwise_definition_comparisons':pairwise,
            'objective_comparisons':against_objective,'objective_losses':losses}
    return {'schema_version':'R13.1','dataset_kind':x['dataset_kind'],
        'input_status':x['input_status'],'release_status':'working_only_not_release_approval',
        'unit_count':len(ids),'unit_ids':ids,'mixture_weighting':'equal_eligible_units',
        'rates':scores,'mixture_masses':mixture,'semantic':semantic,'rules':rules,
        'scope':'Point comparisons on supplied normalised known-state totals; no source-adapter, missing-data or population validation'}

def main():
    if len(sys.argv)>3:raise SystemExit('Usage: execute_state_contract.py [INPUT.json [OUTPUT.json]]')
    inp=Path(sys.argv[1]) if len(sys.argv)>1 else ROOT/'R13_SYNTHETIC_INPUT.json'
    out=Path(sys.argv[2]) if len(sys.argv)>2 else ROOT/'R13_SYNTHETIC_OUTPUT.json'
    if inp.resolve()==out.resolve():raise SystemExit('Output must not overwrite input')
    raw=inp.read_bytes();x=json.loads(raw)
    result=execute(x)
    result['identities']={'input_sha256':hashlib.sha256(raw).hexdigest(),
        'core_sha256':hashlib.sha256((ROOT/'odsa_contract_core.py').read_bytes()).hexdigest(),
        'executor_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2,default=serial)+'\n')
    print(json.dumps({'status':'PASS','dataset_kind':x['dataset_kind'],'units':result['unit_count'],'output':str(out)}))

if __name__=='__main__':main()
