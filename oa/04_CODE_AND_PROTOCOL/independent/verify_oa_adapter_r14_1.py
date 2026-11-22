"""Independently reconcile a captured R14.1 OA batch before diagnostics.

approve: read a non-normative pending candidate; write an accepted R13 input
only after every raw-data and protocol check has passed, then bind its digest.
verify: recheck an already accepted input without modifying it.

No live request is made. No producer/adapter/calculation-core import is used.
"""
from pathlib import Path
from fractions import Fraction
from hashlib import sha256
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import argparse
import json
import platform
import sys

sys.dont_write_bytecode = True
from independent_oa_raw_r14_1 import parse_grouped_response, strict_json

EXPECTED = {
    'protocol': 'cde4280396ac29ba8cb840148bb019ec5a5d75da1f42b7d17cbe09f11b0358e4',
    'queries': 'e07ad740deba04d481672dbaab2b8f4de97daf54160609c46edb11cd4bfccc4f',
    'source_registry': '236305adbd5dbc73462957150329181f96b9185ed0d5b22b73ec26b0a1d13e6e',
    'amendment': 'fe1cd65bf92b814575d0096b27ef99c9b2f5e25cdd5d4c99eaffdb9e58c52f7d',
}
ACCEPTED_SOURCE_LABEL = 'R14.1 recovery fixed EU27 OpenAlex batch; independently reconciled from captured raw responses'


def digest(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def load(path):
    return strict_json(Path(path).read_bytes())


def instant(text):
    value = datetime.fromisoformat(text.replace('Z', '+00:00'))
    if value.tzinfo is None or value.utcoffset().total_seconds() != 0:
        raise ValueError('Recorded time is not explicit UTC')
    return value


class Checks:
    def __init__(self):
        self.rows = []

    def require(self, condition, name):
        self.rows.append({'check': name, 'pass': bool(condition)})
        if not condition:
            raise ValueError(name)


def safe_path(base, relative):
    if not isinstance(relative, str):
        raise ValueError('Invalid recorded path')
    path = (base / relative).resolve()
    if not path.is_relative_to(base.resolve()) or not path.is_file():
        raise ValueError('Recorded path escapes or is missing')
    return path


def query_echo(raw, unit_id, protocol, checks):
    meta = strict_json(raw)['meta']
    prefix = unit_id + ':echo:'
    if 'per_page' in meta:
        checks.require(type(meta['per_page']) is int and meta['per_page'] == 100,
                       prefix + 'per_page_100')
    echoed = meta.get('x_query')
    if echoed is None:
        return 'NOT_RETURNED'
    checks.require(isinstance(echoed, dict), prefix + 'query_object')
    oqo = echoed.get('oqo')
    checks.require(isinstance(oqo, dict), prefix + 'structured_query_object')
    checks.require(oqo.get('get_rows') == 'works', prefix + 'works_endpoint')
    filters = oqo.get('filter_rows')
    checks.require(isinstance(filters, list) and len(filters) == 3,
                   prefix + 'three_expected_filters')
    found = {}
    for field in filters:
        checks.require(isinstance(field, dict) and set(field) == {'column_id', 'value'},
                       prefix + 'filter_structure')
        key = field['column_id']
        checks.require(key not in found, prefix + 'unique_filter_column')
        found[key] = field['value']
    expected = {'authorships.institutions.country_code': unit_id,
                'publication_year': protocol['oa']['cohort']['year'], 'type': 'article'}
    checks.require(set(found) == set(expected), prefix + 'filter_columns')
    checks.require(isinstance(found['authorships.institutions.country_code'], str)
                   and found['authorships.institutions.country_code'].upper() == unit_id,
                   prefix + 'institution_country')
    checks.require(type(found['publication_year']) is int
                   and found['publication_year'] == expected['publication_year'],
                   prefix + 'publication_year')
    checks.require(found['type'] == 'article', prefix + 'article_type')
    checks.require(oqo.get('group_by') == [{'column_id': 'open_access.oa_status:include_unknown'}],
                   prefix + 'grouping_includes_unknown')
    return 'PASS_RETURNED_FILTER_AND_GROUPING_ECHO_CORPUS_NOT_SEPARATELY_CERTIFIED'


def compare_exact(actual, expected, path, checks):
    checks.require(type(actual) is type(expected), path + ':type')
    if isinstance(expected, dict):
        checks.require(set(actual) == set(expected), path + ':keys')
        for key, value in expected.items():
            compare_exact(actual[key], value, path + '/' + key, checks)
    elif isinstance(expected, list):
        checks.require(len(actual) == len(expected), path + ':length')
        for index, value in enumerate(expected):
            compare_exact(actual[index], value, path + '/' + str(index), checks)
    else:
        checks.require(actual == expected, path + ':value')


def reconcile(args, checks):
    hashes = {}
    for key, expected_hash in EXPECTED.items():
        value = digest(getattr(args, key))
        checks.require(value == expected_hash, 'frozen_identity:' + key)
        hashes[key] = value
    protocol = load(args.protocol); queries = load(args.queries)
    amendment = load(args.amendment); batch = load(args.batch)
    candidate = load(args.input); coverage = load(args.coverage)
    batch_hash = digest(args.batch)
    checks.require(batch.get('status') == 'PASS_COMPLETE_CAPTURE', 'complete_capture_status')
    checks.require(batch.get('batch_id') == 'OA-R14.1-RECOVERY-BATCH-01', 'separate_recovery_batch_id')
    checks.require(batch.get('original_R14_bytes_recovered') is False, 'no_original_capture_recovery_claim')
    for key, value in hashes.items():
        checks.require(batch.get(key + '_sha256') == value, 'batch_bound:' + key)
    checks.require(batch.get('code_sha256') == digest(args.acquisition_code), 'actual_acquisition_source_identity')
    start = instant(batch['started_utc']); end = instant(batch['completed_utc'])
    checks.require(instant(amendment['created_utc']) <= start <= end, 'amendment_precedes_capture')
    checks.require((end - start).total_seconds() <= 3600, 'batch_utc_duration_at_most_one_hour')
    checks.require(type(batch.get('elapsed_seconds')) in (int, float)
                   and 0 <= batch['elapsed_seconds'] <= 3600, 'batch_recorded_duration_at_most_one_hour')
    planned = queries['queries']; priority = protocol['oa']['priority']
    checks.require(len(priority) == 27 and [q['unit_id'] for q in planned] == priority, 'frozen_full_EU27_order')
    entries = batch['entries']; attempts = batch['attempts']
    checks.require(len(entries) == 27 and [e['unit_id'] for e in entries] == priority,
                   'captured_full_EU27_order')
    checks.require(isinstance(attempts, list), 'attempt_array')
    by_unit = {u: [] for u in priority}; previous_request = None; previous_response = None
    sequence_pairs = []
    query_lookup = {q['unit_id']: q for q in planned}
    for attempt in attempts:
        unit = attempt['unit_id']
        checks.require(unit in query_lookup, 'attempt_registered_unit')
        q = query_lookup[unit]
        checks.require(attempt.get('url') == q['url'] and attempt.get('sequence') == q['sequence'],
                       unit + ':attempt_query_identity')
        request = instant(attempt['request_utc']); response = instant(attempt['response_utc'])
        checks.require(start <= request <= response <= end, unit + ':attempt_inside_batch')
        if previous_request is not None:
            checks.require((request - previous_request).total_seconds() >= 1,
                           unit + ':request_rate_at_most_one_per_second')
            checks.require(request >= previous_response, unit + ':requests_sequential')
        previous_request, previous_response = request, response
        checks.require(attempt.get('attempt') == len(by_unit[unit]) + 1,
                       unit + ':consecutive_attempt_number')
        by_unit[unit].append(attempt); sequence_pairs.append((q['sequence'], attempt['attempt']))
        checks.require(len(by_unit[unit]) <= 3, unit + ':attempt_limit')
        headers = attempt.get('headers')
        checks.require(isinstance(headers, dict), unit + ':captured_headers_object')
        checks.require(not ({k.lower() for k in headers} & {'authorization', 'cookie', 'set-cookie'}),
                       unit + ':no_credential_headers')
        if 'body_file' in attempt:
            body = safe_path(args.batch.parent, attempt['body_file'])
            raw = body.read_bytes()
            checks.require(type(attempt.get('bytes')) is int and len(raw) == attempt['bytes'],
                           unit + ':attempt_byte_size')
            checks.require(len(raw) <= 262144 and digest(body) == attempt.get('sha256'),
                           unit + ':attempt_body_identity_and_cap')
        else:
            checks.require(attempt.get('http_status') is None and bool(attempt.get('transport_error')),
                           unit + ':body_absence_only_transport_error')
    checks.require(sequence_pairs == sorted(sequence_pairs), 'attempts_fixed_query_then_attempt_order')
    units = []; expected_coverage = []; echo_results = {}; raw_evidence = []
    for q, entry in zip(planned, entries):
        unit = q['unit_id']; local = by_unit[unit]
        checks.require(1 <= len(local) <= 3, unit + ':at_least_one_attempt')
        for key, value in q.items():
            checks.require(entry.get(key) == value, unit + ':entry_frozen_' + key)
        checks.require(entry.get('http_status') == 200 and entry.get('response_gate') == 'PASS',
                       unit + ':recorded_response_gate')
        checks.require(entry.get('accepted_attempt') == len(local), unit + ':last_attempt_is_accepted')
        for previous, following in zip(local, local[1:]):
            status = previous.get('http_status')
            permitted = status is None and bool(previous.get('transport_error'))
            permitted = permitted or (type(status) is int and (status in (408, 429) or 500 <= status <= 599))
            checks.require(permitted, unit + ':only_permitted_retry')
            minimum_delay = 5 if previous['attempt'] == 1 else 15
            header = previous.get('headers', {}).get('retry-after')
            if header is not None:
                try:
                    retry_after = float(header)
                except ValueError:
                    retry_after = (parsedate_to_datetime(header) - instant(previous['response_utc'])).total_seconds()
                checks.require(retry_after <= 60, unit + ':retry_after_within_limit')
                minimum_delay = max(minimum_delay, retry_after)
            checks.require((instant(following['request_utc']) - instant(previous['response_utc'])).total_seconds() >= minimum_delay,
                           unit + ':retry_delay_respected')
        accepted = local[-1]
        checks.require(accepted.get('http_status') == 200, unit + ':accepted_http_200')
        checks.require(accepted.get('final_url') == q['url'], unit + ':final_endpoint_unchanged')
        checks.require('json' in accepted.get('headers', {}).get('content-type', '').lower(),
                       unit + ':recorded_json_content_type')
        for field in ('request_utc', 'response_utc', 'bytes', 'sha256'):
            checks.require(entry.get(field) == accepted.get(field), unit + ':accepted_attempt_' + field)
        checks.require(entry.get('raw_file') == q['raw_output_name'], unit + ':raw_name_fixed')
        raw_path = safe_path(args.batch.parent, entry['raw_file']); raw = raw_path.read_bytes()
        checks.require(len(raw) == entry['bytes'] and digest(raw_path) == entry['sha256'], unit + ':raw_byte_identity')
        checks.require(raw == safe_path(args.batch.parent, accepted['body_file']).read_bytes(), unit + ':raw_equals_accepted_body')
        raw_checks = []
        parsed = parse_grouped_response(raw, states=protocol['oa']['states'], unknown_key=protocol['oa']['unresolved_key'],
                                         maximum_bytes=262144, http_status=accepted['http_status'], checks=raw_checks)
        checks.rows.extend({'check': unit + ':raw:' + r['check'], 'pass': r['pass']} for r in raw_checks)
        checks.require(parsed['N'] > 0 and parsed['D'] > 0, unit + ':positive_total_and_known_denominator')
        echo_results[unit] = query_echo(raw, unit, protocol, checks)
        units.append({'id': unit, 'state_totals': {s: str(parsed['state_counts'][s]) for s in protocol['oa']['states']},
                      'known_denominator': str(parsed['D']), 'unresolved_total': str(parsed['M']),
                      'unresolved_status': 'known_nonnegative_total'})
        expected_coverage.append({'unit_id': unit, 'country_name': q['country_name'],
            'N': parsed['N'], 'M': parsed['M'], 'D': parsed['D'],
            'counts': {**parsed['state_counts'], protocol['oa']['unresolved_key']: parsed['M']},
            'returned_bucket_count': len(parsed['returned_keys']), 'missing_OA_share': str(Fraction(parsed['M'], parsed['N']))})
        raw_evidence.append({'unit_id': unit, 'path': entry['raw_file'], 'bytes': len(raw), 'sha256': digest(raw_path)})
    provenance = candidate.get('provenance', {})
    label = provenance.get('source_label')
    checks.require(isinstance(label, str) and 1 <= len(label) <= 160 and 'R14.1' in label and 'OpenAlex' in label,
                   'candidate_source_label')
    expected_status = 'pending_independent_reconciliation' if args.mode == 'approve' else 'independently_reconciled'
    common = protocol['common_contract']; oa = protocol['oa']
    expected_input = {'schema_version': 'R13.1', 'dataset_kind': 'OA', 'input_status': 'real_extension_input',
        'provenance': {'source_label': label, 'source_sha256': batch_hash, 'adapter_status': expected_status},
        'states': oa['states'], 'units': units,
        'boundaries': [{'id': key, 'states': oa['definitions'][key]} for key in oa['definition_order']],
        'nested_boundaries': True,
        'objective': {'id': oa['objective']['id'], 'states': oa['objective']['states']},
        'priority': priority, 'rules': list(common['rules'].values()),
        'cost_profiles': [{'id': key, 'false_positive': value['false_inclusion'], 'false_negative': value['false_exclusion']}
                          for key, value in common['cost_profiles'].items()],
        'action_cost_profiles_by_rule': {'lowest_3': ['equal_costs'], 'highest_3': ['equal_costs'],
                                        'below_one_quarter': ['equal_costs', 'exclusion_costly', 'inclusion_costly']},
        'mixture_weighting': 'equal_eligible_units', 'primary_missing_policy': 'complete_known_states'}
    compare_exact(candidate, expected_input, 'normalised_candidate' if args.mode == 'approve' else 'accepted_input', checks)
    checks.require(coverage.get('batch_sha256') == batch_hash, 'coverage_source_identity')
    compare_exact(coverage.get('countries'), expected_coverage, 'coverage', checks)
    if args.mode == 'approve':
        checks.require(coverage.get('stage_status') == 'CANDIDATE_AWAITING_SEPARATE_ADAPTER_ACCEPTANCE', 'coverage_pending_status')
    accepted_input = expected_input
    if args.mode == 'approve':
        accepted_input['provenance'] = {**expected_input['provenance'],
            'adapter_status': 'independently_reconciled', 'source_label': ACCEPTED_SOURCE_LABEL}
    return accepted_input, raw_evidence, echo_results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=['approve', 'verify'], required=True)
    for name in ('protocol', 'queries', 'source-registry', 'amendment', 'batch', 'input', 'coverage', 'acquisition-code', 'normalisation-code', 'report'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--accepted-output', type=Path)
    args = parser.parse_args()
    if args.report.exists():
        raise SystemExit('Refuse to overwrite an existing review report')
    if args.mode == 'approve' and (args.accepted_output is None or args.accepted_output.exists()):
        raise SystemExit('Approval needs a new accepted-output path')
    checks = Checks(); started = datetime.now(timezone.utc).isoformat(); accepted_written = False
    try:
        approved, raw_evidence, echo_results = reconcile(args, checks)
        accepted_path = args.input
        if args.mode == 'approve':
            accepted_path = args.accepted_output
            accepted_path.parent.mkdir(parents=True, exist_ok=True)
            with accepted_path.open('x', encoding='utf-8') as stream:
                stream.write(json.dumps(approved, ensure_ascii=False, indent=2) + '\n')
            accepted_written = True
        report = {
            'status': 'PASS_INDEPENDENT_OA_ADAPTER_RECONCILIATION', 'mode': args.mode,
            'started_utc': started, 'completed_utc': datetime.now(timezone.utc).isoformat(),
            'normalised_input_sha256': digest(accepted_path), 'reviewed_input_sha256': digest(args.input),
            'batch_sha256': digest(args.batch), 'coverage_sha256': digest(args.coverage),
            'protocol_sha256': digest(args.protocol), 'queries_sha256': digest(args.queries),
            'source_registry_sha256': digest(args.source_registry), 'amendment_sha256': digest(args.amendment),
            'acquisition_code_sha256': digest(args.acquisition_code),
            'normalisation_code_sha256': digest(args.normalisation_code),
            'reviewer_code_sha256': digest(__file__),
            'raw_parser_code_sha256': digest(Path(__file__).with_name('independent_oa_raw_r14_1.py')),
            'checks': len(checks.rows), 'all_checks_pass': True, 'check_details': checks.rows,
            'country_count': 27, 'maximum_integer_reconciliation_residual': 0,
            'raw_response_identities': raw_evidence, 'provider_query_echo': echo_results,
            'pending_to_accepted_transition': args.mode == 'approve',
            'transition_scope': ('Only adapter_status and descriptive source_label changed after reconciliation; scientific fields matched before acceptance.'
                                 if args.mode == 'approve' else 'No input modification; accepted scientific fields were reconciled directly against the captured raw responses.'),
            'runtime': {'python': platform.python_version(), 'platform': sys.platform},
            'network_requests': 0, 'producer_or_core_imports': False,
            'limits': ['Local captured bytes and recorded metadata only; no transport signature or provider classification certification.',
                       'The requested corpus=core is not separately echoed by the provider; upstream corpus implementation is not certified.',
                       'Earlier R14 results were known; no outcome-blindness or restored-original-snapshot claim.',
                       'This gate precedes new diagnostics; it does not verify later calculated losses or clear FAT release.']
        }
    except Exception as error:
        report = {'status': 'FAIL_INDEPENDENT_OA_ADAPTER_RECONCILIATION',
                  'started_utc': started, 'completed_utc': datetime.now(timezone.utc).isoformat(),
                  'failure': type(error).__name__ + ': ' + str(error), 'checks': len(checks.rows),
                  'check_details': checks.rows, 'accepted_input_written': accepted_written}
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        raise
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: report[k] for k in ['status', 'mode', 'checks', 'normalised_input_sha256', 'country_count', 'maximum_integer_reconciliation_residual']}, indent=2))


if __name__ == '__main__':
    main()
