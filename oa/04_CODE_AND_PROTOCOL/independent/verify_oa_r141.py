"""Independently verify the archived R14.1 OA recovery from raw bytes to results.

Only local reads are performed. The producer/core is never imported or executed.
R14.1 is a separately dated recovery capture, not recovered original R14 bytes.
"""
from pathlib import Path
from hashlib import sha256
from fractions import Fraction
from datetime import datetime, timezone
import argparse
import json
import platform
import sys
sys.dont_write_bytecode = True
from r141_independent_math import (Comparison, parse_oa_raw_response, parse_input,
                                 verify_point, verify_secondary)

PROTOCOL_SHA = 'cde4280396ac29ba8cb840148bb019ec5a5d75da1f42b7d17cbe09f11b0358e4'
QUERIES_SHA = 'e07ad740deba04d481672dbaab2b8f4de97daf54160609c46edb11cd4bfccc4f'
CORE_SHA = '221afe006b7d799b2f5044b5cbb0c61ba8b3f46304d6abb1d0003169715f0541'
EXECUTOR_SHA = '041578bbcd531e0b8b97cd8960240c01f556f554b12029ea4e5750f0493f5bf0'


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def local_child(root, rel):
    path = (root / rel).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError('Raw evidence path missing or outside its batch')
    return path


def verify_raw(batch, batch_path, queries, inp, protocol):
    c = Comparison()
    c.equal('batch/status',batch['status'],'PASS_COMPLETE_CAPTURE')
    c.equal('batch/prior_bytes_not_recovered',batch['original_R14_bytes_recovered'],False)
    c.equal('batch/protocol_sha256',batch['protocol_sha256'],PROTOCOL_SHA)
    c.equal('batch/queries_sha256',batch['queries_sha256'],QUERIES_SHA)
    c.equal('batch/unit_order',[e['unit_id'] for e in batch['entries']],protocol['oa']['priority'])
    c.equal('batch/complete_entry_count',len(batch['entries']),27)
    c.equal('input/source_identity',inp['provenance']['source_sha256'],digest(batch_path))
    c.equal('input/adapter_status',inp['provenance']['adapter_status'],'independently_reconciled')
    if len(batch['entries']) != 27:
        raise ValueError('Incomplete cohort; numerical verification is blocked')
    query_by_id={q['unit_id']:q for q in queries['queries']}
    input_by_id={r['id']:r for r in inp['units']}
    c.equal('raw_input/exact_roster',list(input_by_id),protocol['oa']['priority'])
    attempts={u:[] for u in protocol['oa']['priority']}
    previous_request = None
    for attempt in batch['attempts']:
        unit=attempt['unit_id']
        if unit not in attempts:
            raise ValueError('Unregistered attempt unit')
        attempts[unit].append(attempt)
        request=datetime.fromisoformat(attempt['request_utc'])
        response=datetime.fromisoformat(attempt['response_utc'])
        c.equal('transport/' + unit + '/response_after_request',response >= request,True)
        if previous_request is not None:
            c.equal('transport/' + unit + '/request_spacing', (request-previous_request).total_seconds() >= 1,True)
        previous_request=request
    start=datetime.fromisoformat(batch['started_utc'])
    end=datetime.fromisoformat(batch['completed_utc'])
    c.equal('batch/window_at_most_hour',0 <= (end-start).total_seconds() <= 3600,True)
    independently_reconstructed = {}
    for entry in batch['entries']:
        unit=entry['unit_id']; expected_query=query_by_id[unit]
        for key,val in expected_query.items():
            c.equal('query/' + unit + '/' + key,entry[key],val)
        c.equal('raw/' + unit + '/http_status',entry['http_status'],200)
        path=local_child(batch_path.parent,entry['raw_file'])
        raw=path.read_bytes()
        c.equal('raw/' + unit + '/bytes',len(raw),entry['bytes'])
        c.equal('raw/' + unit + '/sha256',sha256(raw).hexdigest(),entry['sha256'])
        values=parse_oa_raw_response(raw,protocol['oa']['states'])
        independently_reconstructed[unit]=values
        c.equal('normalised/' + unit + '/states',input_by_id[unit]['state_totals'],
                {k:Fraction(v) for k,v in values['counts'].items()})
        c.equal('normalised/' + unit + '/known_denominator',input_by_id[unit]['known_denominator'],Fraction(values['D']))
        c.equal('normalised/' + unit + '/unresolved_total',input_by_id[unit]['unresolved_total'],Fraction(values['M']))
        c.equal('normalised/' + unit + '/unresolved_status',input_by_id[unit]['unresolved_status'],'known_nonnegative_total')
        c.equal('attempt/' + unit + '/bounded_number',1 <= len(attempts[unit]) <= 3,True)
        accepted=[]
        for position,attempt in enumerate(attempts[unit],1):
            c.equal('attempt/' + unit + '/sequence',attempt['attempt'],position)
            c.equal('attempt/' + unit + '/url',attempt['url'],expected_query['url'])
            if attempt.get('http_status') == 200:
                body=local_child(batch_path.parent,attempt['body_file']).read_bytes()
                parse_oa_raw_response(body,protocol['oa']['states'])
                accepted.append(attempt)
                c.equal('attempt/' + unit + '/raw_body_identity',body,raw)
                c.equal('attempt/' + unit + '/sha256',sha256(body).hexdigest(),attempt['sha256'])
                c.equal('attempt/' + unit + '/bytes',len(body),attempt['bytes'])
                c.equal('attempt/' + unit + '/content_type_json','application/json' in attempt.get('headers',{}).get('content-type','').lower(),True)
            else:
                status=attempt.get('http_status')
                retryable=status in (408,429) or (type(status) is int and 500 <= status <= 599) or (status is None and bool(attempt.get('error')))
                c.equal('attempt/' + unit + '/retryable_only',retryable,True)
        c.equal('attempt/' + unit + '/one_success',len(accepted),1)
        if accepted:
            c.equal('attempt/' + unit + '/first_success_retained',entry['accepted_attempt'],accepted[0]['attempt'])
    parse_input(inp,protocol)
    return c,independently_reconstructed


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('protocol','queries','batch','input','point','secondary','adapter-review','contracts-dir','report'):
        p.add_argument('--'+name,required=True,type=Path)
    args=p.parse_args()
    if digest(args.protocol)!=PROTOCOL_SHA or digest(args.queries)!=QUERIES_SHA:
        raise SystemExit('Frozen protocol/query identity mismatch')
    if digest(args.contracts_dir/'odsa_contract_core.py')!=CORE_SHA or digest(args.contracts_dir/'execute_state_contract.py')!=EXECUTOR_SHA:
        raise SystemExit('Frozen core/executor identity mismatch')
    protocol,queries,batch,inp,point,secondary,adapter=[read(pth) for pth in
        (args.protocol,args.queries,args.batch,args.input,args.point,args.secondary,args.adapter_review)]
    raw_comparison,counts=verify_raw(batch,args.batch,queries,inp,protocol)
    gate=Comparison()
    gate.equal('adapter/status',adapter['status'],'PASS_INDEPENDENT_OA_ADAPTER_RECONCILIATION')
    gate.equal('adapter/input_identity',adapter['normalised_input_sha256'],digest(args.input))
    gate.equal('point/input_identity',point['identities']['input_sha256'],digest(args.input))
    gate.equal('point/core_identity',point['identities']['core_sha256'],CORE_SHA)
    gate.equal('point/executor_identity',point['identities']['executor_sha256'],EXECUTOR_SHA)
    gate.equal('secondary/input_identity',secondary['input_sha256'],digest(args.input))
    gate.equal('secondary/schema_version',secondary['schema_version'],'R14.1')
    gate.equal('secondary/dataset_kind',secondary['dataset_kind'],'OA')
    point_comparison=verify_point(inp,point,protocol)
    secondary_comparison,subsets=verify_secondary(inp,secondary)
    groups={'raw_to_normalised':raw_comparison,'identity_and_stage_gates':gate,
            'point_results':point_comparison,'secondary_results':secondary_comparison}
    failures=[{'group':name,**failure} for name,c in groups.items() for failure in c.failures]
    report={'status':'PASS_INDEPENDENT_OA_RECOVERY_VERIFICATION' if not failures else 'FAIL_INDEPENDENT_OA_RECOVERY_VERIFICATION',
            'created_utc':datetime.now(timezone.utc).isoformat(),
            'runtime':{'python':sys.version.split()[0],'platform':platform.system()},
            'comparison_counts':{name:c.checks for name,c in groups.items()},
            'total_comparisons':sum(c.checks for c in groups.values()),
            'comparison_count_convention':'One scalar or container check; not independent statistical tests.',
            'subset_feasibility_checks':subsets,
            'maximum_exact_numeric_residual':str(max(c.maximum_exact_numeric_residual for c in groups.values())),
            'failures':failures,
            'identities':{name:digest(getattr(args,name)) for name in ('protocol','queries','batch','input','point','secondary','adapter_review')},
            'verifier_sha256':digest(Path(__file__)),
            'math_module_sha256':digest(Path(__file__).with_name('r141_independent_math.py')),
            'scope':'New independent local raw-byte reconstruction, point diagnostics and exhaustive subset-feasibility verification of registered S5/S6 marginal envelopes.',
            'limits':['This is a separately numbered recovery capture, not restoration of the lost original R14 source bytes.',
                      'Earlier R14 outcomes were known; this is not blinded or registered-before-outcome verification.',
                      'The code imports no producer/core, makes no network calls and does not audit provider classification or work-level country overlap.',
                      'S6 results are rectangular marginal outer-envelope certificates, not exact joint loss or attainability statements.',
                      'No native Windows/Microsoft Word acceptance, historical Monte Carlo rerun or FAT release approval is implied.'],
            'network_requests':0,'new_MC_replications':0}
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('status','comparison_counts','total_comparisons','subset_feasibility_checks','maximum_exact_numeric_residual','failures')},ensure_ascii=False,indent=2))
    raise SystemExit(0 if not failures else 1)


if __name__=='__main__':main()
