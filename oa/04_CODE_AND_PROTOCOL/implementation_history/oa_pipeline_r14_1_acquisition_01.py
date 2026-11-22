"""Explicit R14.1 recovery capture and exact, frozen-protocol OA diagnostics.

Only 'acquire' uses the network. Other commands operate on captured bytes.
The original R14 bytes were not recovered; no original-snapshot identity claim
is made. Outputs must be new, and scientific choices remain those of R13.
"""
from pathlib import Path
from fractions import Fraction as F
from hashlib import sha256
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import argparse
import importlib.metadata
import json
import platform
import shutil
import sys
import time
import urllib.error
import urllib.request

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / 'r13_contracts'))
PROTOCOL_SHA = 'cde4280396ac29ba8cb840148bb019ec5a5d75da1f42b7d17cbe09f11b0358e4'
QUERIES_SHA = 'e07ad740deba04d481672dbaab2b8f4de97daf54160609c46edb11cd4bfccc4f'
AMENDMENT_SHA = 'fe1cd65bf92b814575d0096b27ef99c9b2f5e25cdd5d4c99eaffdb9e58c52f7d'


def utc():
    return datetime.now(timezone.utc).isoformat()


def digest(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def serial(value):
    if isinstance(value, F):
        return str(value)
    if isinstance(value, (set, frozenset)):
        return sorted(value)
    raise TypeError(type(value).__name__)


def save(path, value):
    path = Path(path)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=serial) + '\n', encoding='utf-8')


def read(path):
    return json.loads(Path(path).read_bytes())


def frozen(path, expected):
    if digest(path) != expected:
        raise ValueError('Frozen file identity mismatch: ' + Path(path).name)
    return read(path)


def unique_object(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            raise ValueError('Duplicate JSON object key')
        out[k] = v
    return out


def validate_response(raw, states):
    if len(raw) > 262144:
        raise ValueError('Response byte cap exceeded')
    obj = json.loads(raw, object_pairs_hook=unique_object)
    if not isinstance(obj, dict) or not isinstance(obj.get('meta'), dict):
        raise ValueError('Missing top-level object/meta')
    meta = obj['meta']; total = meta.get('count'); groups = obj.get('group_by')
    if type(total) is not int or total < 0 or not isinstance(groups, list) or len(groups) > 7:
        raise ValueError('Invalid count/group array')
    if 'results' in obj and obj['results'] != []:
        raise ValueError('Unrequested records or invalid results payload')
    counts = {}
    for group in groups:
        if not isinstance(group, dict) or set(group) - {'key', 'key_display_name', 'count'}:
            raise ValueError('Unexpected/nested group schema')
        key = group.get('key'); n = group.get('count')
        if not isinstance(key, str) or key not in states + ['unknown'] or key in counts:
            raise ValueError('Unexpected or duplicate status')
        if type(n) is not int or n < 0:
            raise ValueError('Noninteger/negative group count')
        counts[key] = n
    if sum(counts.values()) != total:
        raise ValueError('Group counts do not reconcile to meta.count')
    for container in [meta, obj]:
        if 'groups_count' in container and (type(container['groups_count']) is not int or container['groups_count'] != len(groups)):
            raise ValueError('groups_count mismatch')
        if 'next_cursor' in container and container['next_cursor'] is not None:
            raise ValueError('Unexpected continuation cursor')
    complete = {s: counts.get(s, 0) for s in states + ['unknown']}
    missing = complete['unknown']; known = total - missing
    if total <= 0 or known <= 0:
        raise ValueError('Nonpositive total or known denominator')
    return {'N': total, 'M': missing, 'D': known, 'counts': complete,
            'returned_bucket_count': len(groups)}


def acquire(args):
    protocol = frozen(args.protocol, PROTOCOL_SHA)
    queries = frozen(args.queries, QUERIES_SHA)
    frozen(args.amendment, AMENDMENT_SHA)
    out = args.output.resolve(); out.mkdir(parents=True, exist_ok=False)
    (out / 'raw').mkdir(); (out / 'attempts').mkdir()
    clock_start = time.monotonic(); previous_start = None
    record = {'schema_version': 'R14.1', 'batch_id': 'OA-R14.1-RECOVERY-BATCH-01',
              'status': 'RUNNING', 'started_utc': utc(),
              'protocol_sha256': digest(args.protocol), 'queries_sha256': digest(args.queries),
              'source_registry_sha256': digest(args.source_registry),
              'amendment_sha256': digest(args.amendment), 'code_sha256': digest(__file__),
              'runtime': {'python': platform.python_version(), 'platform': sys.platform},
              'original_R14_bytes_recovered': False,
              'entries': [], 'attempts': []}
    manifest = out / 'R14_1_OA_ACQUISITION_BATCH.json'
    save(manifest, record)
    try:
        if [q['unit_id'] for q in queries['queries']] != protocol['oa']['priority']:
            raise ValueError('Query priority differs from frozen protocol')
        for q in queries['queries']:
            success = False
            for attempt_no in range(1, 4):
                if time.monotonic() - clock_start >= 3600:
                    raise ValueError('Batch window exceeded')
                if previous_start is not None:
                    time.sleep(max(0, 1 - (time.monotonic() - previous_start)))
                start = utc(); previous_start = time.monotonic()
                row = {'sequence': q['sequence'], 'unit_id': q['unit_id'], 'attempt': attempt_no,
                       'url': q['url'], 'request_utc': start}
                raw = None; status = None; headers = {}; retryable = False
                try:
                    req = urllib.request.Request(q['url'], headers={'User-Agent': 'ODSA-R14.1-Research-Recovery', 'Accept': 'application/json'})
                    with urllib.request.urlopen(req, timeout=60) as response:
                        status = response.status; headers = dict(response.headers.items())
                        row['final_url'] = response.geturl(); raw = response.read(262145)
                except urllib.error.HTTPError as exc:
                    status = exc.code; headers = dict(exc.headers.items()); raw = exc.read(262145)
                    row['transport_error'] = type(exc).__name__
                    retryable = status in (408, 429) or 500 <= status <= 599
                except (urllib.error.URLError, TimeoutError, OSError) as exc:
                    row['transport_error'] = type(exc).__name__ + ': ' + str(exc)
                    retryable = True
                row['response_utc'] = utc(); row['http_status'] = status
                lower = {k.lower(): v for k, v in headers.items()}
                row['headers'] = {k: v for k, v in lower.items() if k in ('date', 'etag', 'last-modified', 'content-type', 'retry-after') or 'ratelimit' in k or 'rate-limit' in k}
                if raw is not None:
                    name = f"attempts/{q['sequence']:02d}_{q['unit_id']}_attempt{attempt_no}.body"
                    (out / name).write_bytes(raw)
                    row.update(body_file=name, bytes=len(raw), sha256=sha256(raw).hexdigest())
                record['attempts'].append(row); save(manifest, record)
                if raw is not None and len(raw) > 262144:
                    raise ValueError('Response byte cap exceeded')
                if status == 200:
                    if row.get('final_url') != q['url']:
                        raise ValueError('Unexpected endpoint redirect')
                    if 'json' not in lower.get('content-type', '').lower():
                        raise ValueError('Unexpected response content type')
                    validated = validate_response(raw, protocol['oa']['states'])
                    destination = out / q['raw_output_name']
                    destination.write_bytes(raw)
                    record['entries'].append({**q, 'raw_file': q['raw_output_name'], 'http_status': 200,
                                               'bytes': len(raw), 'sha256': sha256(raw).hexdigest(),
                                               'accepted_attempt': attempt_no,
                                               'response_gate': 'PASS', 'request_utc': start,
                                               'response_utc': row['response_utc']})
                    save(manifest, record); success = True
                    print(json.dumps({'country': q['unit_id'], 'sequence': q['sequence'], 'status': 'CAPTURED'}), flush=True)
                    break
                if status == 429 and raw is not None and any(token in raw.decode('utf-8', 'replace').lower() for token in ['api key', 'api_key', 'credential', 'subscription', 'payment', 'upgrade', 'credit', 'sign in']):
                    raise ValueError('Credential/plan/quota requirement; no bypass')
                if not retryable or attempt_no == 3:
                    raise ValueError('Country request failed within frozen attempt policy: ' + q['unit_id'])
                delay = 5 if attempt_no == 1 else 15
                if 'retry-after' in lower:
                    try:
                        retry_after = float(lower['retry-after'])
                    except ValueError:
                        retry_after = (parsedate_to_datetime(lower['retry-after']) - datetime.now(timezone.utc)).total_seconds()
                    if retry_after > 60:
                        raise ValueError('Retry-After exceeds permitted wait')
                    delay = max(delay, retry_after)
                time.sleep(delay)
            if not success:
                raise ValueError('No valid response for required country')
        if time.monotonic() - clock_start > 3600:
            raise ValueError('Batch window exceeded')
        record['status'] = 'PASS_COMPLETE_CAPTURE'
    except Exception as exc:
        record['status'] = 'FAILED_CAPTURE_NO_COHORT_ANALYSIS'
        record['failure'] = type(exc).__name__ + ': ' + str(exc)
        raise
    finally:
        record['completed_utc'] = utc(); record['elapsed_seconds'] = time.monotonic() - clock_start
        save(manifest, record)


def normalise(args):
    protocol = frozen(args.protocol, PROTOCOL_SHA)
    batch = read(args.batch)
    if batch['status'] != 'PASS_COMPLETE_CAPTURE' or batch['protocol_sha256'] != PROTOCOL_SHA or batch['queries_sha256'] != QUERIES_SHA:
        raise ValueError('Complete frozen capture required')
    if [e['unit_id'] for e in batch['entries']] != protocol['oa']['priority']:
        raise ValueError('Exactly the full fixed ordered cohort is required')
    states = protocol['oa']['states']; units = []; coverage = []
    for entry in batch['entries']:
        path = args.batch.parent / entry['raw_file']
        if path.stat().st_size != entry['bytes'] or digest(path) != entry['sha256']:
            raise ValueError('Captured response byte identity mismatch')
        v = validate_response(path.read_bytes(), states)
        units.append({'id': entry['unit_id'], 'state_totals': {s: str(v['counts'][s]) for s in states},
                      'known_denominator': str(v['D']), 'unresolved_total': str(v['M']),
                      'unresolved_status': 'known_nonnegative_total'})
        coverage.append({'unit_id': entry['unit_id'], 'country_name': entry['country_name'],
                         **v, 'missing_OA_share': str(F(v['M'], v['N']))})
    common = protocol['common_contract']; oa = protocol['oa']
    data = {'schema_version': 'R13.1', 'dataset_kind': 'OA', 'input_status': 'real_extension_input',
            'provenance': {'source_label': 'R14.1 recovery fixed EU27 OpenAlex batch; staged for separate adapter acceptance',
                           'source_sha256': digest(args.batch), 'adapter_status': 'independently_reconciled'},
            'states': states, 'units': units,
            'boundaries': [{'id': k, 'states': oa['definitions'][k]} for k in oa['definition_order']],
            'objective': {'id': oa['objective']['id'], 'states': oa['objective']['states']},
            'priority': oa['priority'], 'rules': list(common['rules'].values()),
            'cost_profiles': [{'id': k, 'false_positive': v['false_inclusion'], 'false_negative': v['false_exclusion']} for k, v in common['cost_profiles'].items()],
            'action_cost_profiles_by_rule': {'lowest_3': ['equal_costs'], 'highest_3': ['equal_costs'],
                                            'below_one_quarter': ['equal_costs', 'exclusion_costly', 'inclusion_costly']}}
    for p in [args.output, args.coverage]:
        if p.exists():
            raise ValueError('Refuse to overwrite an existing normalisation output')
        p.parent.mkdir(parents=True, exist_ok=True)
    save(args.output, data)
    save(args.coverage, {'schema_version': 'R14.1', 'batch_sha256': digest(args.batch), 'countries': coverage,
                         'stage_status': 'CANDIDATE_AWAITING_SEPARATE_ADAPTER_ACCEPTANCE',
                         'input_stage_note': 'The input enum is the normative target value; actual acceptance is governed by the separate hash-bound adapter receipt, which diagnose requires.'})


def diagnose(args):
    from jsonschema import Draft202012Validator
    import execute_state_contract as executor
    import odsa_contract_core as core
    protocol = frozen(args.protocol, PROTOCOL_SHA)
    evidence = read(args.adapter_review)
    if evidence.get('status') != 'PASS_INDEPENDENT_OA_ADAPTER_RECONCILIATION' or evidence.get('normalised_input_sha256') != digest(args.input):
        raise ValueError('Separate independent acceptance bound to this exact input is required')
    out = args.output.resolve(); out.mkdir(parents=True, exist_ok=False)
    x = read(args.input); started = utc()
    point = executor.execute(x)
    point['identities'] = {'input_sha256': digest(args.input),
                           'core_sha256': digest(HERE / 'r13_contracts/odsa_contract_core.py'),
                           'executor_sha256': digest(HERE / 'r13_contracts/execute_state_contract.py')}
    encoded_point = json.loads(json.dumps(point, default=serial))
    Draft202012Validator(read(HERE / 'r13_contracts/R13_STATE_OUTPUT.schema.json')).validate(encoded_point)
    save(out / 'R14_1_OA_POINT_RESULTS.json', point)
    s5 = {}
    for rule in x['rules']:
        if rule['kind'] != 'rank':
            continue
        s5[rule['id']] = {}
        for vector, scores in point['rates'].items():
            values = sorted(scores.values(), reverse=rule['direction'] == 'highest')
            gap = abs(values[rule['k']] - values[rule['k'] - 1])
            membership = core.interval_membership({g: (v, v) for g, v in scores.items()}, rule['k'], rule['direction'])
            s5[rule['id']][vector] = {'boundary_gap': gap, 'boundary_exact_tie': gap == 0,
                                    'boundary_gap_at_most_1e_12': gap <= F(1, 10**12),
                                    'fixed_priority_selected': point['rules'][rule['id']]['selected_sets'][vector],
                                    'all_admissible_membership': membership}
    vectors = {d['id']: d['states'] for d in x['boundaries']}; vectors[x['objective']['id']] = x['objective']['states']
    intervals = {}; low = {}; threshold = {}
    for vector, members in vectors.items():
        intervals[vector] = {u['id']: core.unresolved_rate_interval(sum((F(u['state_totals'][s]) for s in members), F(0)),
                                                                  u['known_denominator'], u['unresolved_total']) for u in x['units']}
        low[vector] = core.interval_membership(intervals[vector], 3, 'lowest')
        threshold[vector] = core.threshold_membership(intervals[vector], '1/4', 'lt')
    secondary = {'schema_version': 'R14.1', 'dataset_kind': 'OA', 'input_sha256': digest(args.input),
                 'S5_point_ties': s5,
                 'S6_unknown': {'scope': 'Marginal rectangular outer-envelope certificates; not joint attainability or joint action-loss extrema.',
                                'intervals': intervals, 'lowest_3': low, 'below_one_quarter': threshold}}
    save(out / 'R14_1_OA_SECONDARY_RESULTS.json', secondary)
    save(out / 'R14_1_OA_EXECUTION_RECORD.json', {'status': 'EXECUTED_AWAITING_INDEPENDENT_RESULT_REVIEW',
         'started_utc': started, 'completed_utc': utc(), 'protocol_sha256': digest(args.protocol),
         'input_sha256': digest(args.input), 'adapter_review_sha256': digest(args.adapter_review),
         'pipeline_sha256': digest(__file__), 'python': platform.python_version(), 'platform': sys.platform,
         'jsonschema': importlib.metadata.version('jsonschema'), 'network_requests': 0, 'new_MC_replications': 0,
         'outputs': {p.name: digest(p) for p in sorted(out.glob('*RESULTS.json'))}})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    acq = commands.add_parser('acquire'); acq.add_argument('--protocol', type=Path, required=True)
    acq.add_argument('--queries', type=Path, required=True); acq.add_argument('--source-registry', type=Path, required=True)
    acq.add_argument('--amendment', type=Path, required=True); acq.add_argument('--output', type=Path, required=True)
    norm = commands.add_parser('normalise'); norm.add_argument('--protocol', type=Path, required=True)
    norm.add_argument('--batch', type=Path, required=True); norm.add_argument('--output', type=Path, required=True)
    norm.add_argument('--coverage', type=Path, required=True)
    run = commands.add_parser('diagnose'); run.add_argument('--protocol', type=Path, required=True)
    run.add_argument('--input', type=Path, required=True); run.add_argument('--adapter-review', type=Path, required=True)
    run.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    {'acquire': acquire, 'normalise': normalise, 'diagnose': diagnose}[args.command](args)


if __name__ == '__main__':
    main()
