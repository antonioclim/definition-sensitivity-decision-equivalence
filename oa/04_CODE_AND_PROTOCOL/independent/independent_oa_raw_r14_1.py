"""Independent R14.1 raw OpenAlex response checks; standard library only.

This parser does not import the acquisition adapter, the producer or the R13
calculation core. It validates a captured grouped response; it cannot certify
upstream metadata, transport authenticity or atomic database snapshotting.
"""
import json


class ReconciliationError(ValueError):
    pass


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ReconciliationError('Duplicate JSON object key')
        result[key] = value
    return result


def strict_json(raw):
    """Reject duplicate object keys and non-JSON NaN/Infinity literals."""
    def invalid_constant(value):
        raise ReconciliationError('Non-JSON numeric constant')
    try:
        return json.loads(raw.decode('utf-8'), object_pairs_hook=_unique_object,
                          parse_constant=invalid_constant)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ReconciliationError('Invalid UTF-8 JSON') from error


def parse_grouped_response(raw, *, states, unknown_key, maximum_bytes,
                           http_status=200, checks=None):
    """Return independent integer totals after all registered response gates."""
    local_checks = [] if checks is None else checks

    def require(condition, name):
        local_checks.append({'check': name, 'pass': bool(condition)})
        if not condition:
            raise ReconciliationError(name)

    require(type(http_status) is int and http_status == 200, 'http_200')
    require(isinstance(raw, bytes) and len(raw) <= maximum_bytes, 'bounded_body')
    payload = strict_json(raw)
    require(isinstance(payload, dict), 'json_object')
    meta = payload.get('meta')
    require(isinstance(meta, dict), 'meta_object')
    total = meta.get('count')
    require(type(total) is int and total >= 0, 'meta_count_nonnegative_integer')
    groups = payload.get('group_by')
    require(isinstance(groups, list), 'group_by_array')
    require(len(groups) <= len(states) + 1, 'registered_bucket_capacity')
    if 'results' in payload:
        require(isinstance(payload['results'], list) and not payload['results'],
                'no_unrequested_work_records')
    domain = set(states) | {unknown_key}
    require(len(domain) == len(states) + 1, 'registered_state_domain_distinct')
    returned = {}
    for index, group in enumerate(groups):
        label = 'bucket_' + str(index + 1)
        require(isinstance(group, dict), label + '_object')
        key = group.get('key')
        require(isinstance(key, str) and key in domain, label + '_registered_key')
        require(key not in returned, label + '_unique_key')
        require('group_by' not in group and 'groups' not in group,
                label + '_not_nested_group')
        count = group.get('count')
        require(type(count) is int and count >= 0, label + '_nonnegative_integer')
        returned[key] = count
    require(sum(returned.values()) == total, 'exact_sum_matches_meta_count')
    for location, obj in [('meta', meta), ('top_level', payload)]:
        if 'groups_count' in obj:
            value = obj['groups_count']
            require(type(value) is int and value == len(groups),
                    location + '_groups_count_matches_returned')
        if 'next_cursor' in obj:
            require(obj['next_cursor'] is None, location + '_no_next_cursor')
    # Only now may absent registered buckets be set to zero.
    counts = {state: returned.get(state, 0) for state in states}
    missing = returned.get(unknown_key, 0)
    denominator = sum(counts.values())
    require(denominator == total - missing, 'known_denominator_reconciled')
    return {'N': total, 'M': missing, 'D': denominator,
            'state_counts': counts, 'returned_keys': list(returned)}


def synthetic_parser_checks():
    """Focused invalid-response controls, not empirical result verification."""
    from copy import deepcopy
    states = ['closed', 'bronze', 'green', 'hybrid', 'gold', 'diamond']
    valid = {'meta': {'count': 10, 'groups_count': 2, 'next_cursor': None},
             'results': [],
             'group_by': [{'key': 'closed', 'count': 7},
                          {'key': 'gold', 'count': 3}]}
    cases = []

    def execute(name, payload, expected, raw=None, status=200):
        body = raw if raw is not None else json.dumps(payload).encode('utf-8')
        accepted = True
        result = None
        try:
            result = parse_grouped_response(body, states=states,
                unknown_key='unknown', maximum_bytes=262144, http_status=status)
        except ReconciliationError:
            accepted = False
        if accepted != expected:
            raise AssertionError('Synthetic parser control failed: ' + name)
        cases.append({'name': name, 'expected_acceptance': expected, 'pass': True})
        return result

    result = execute('absent_known_and_unknown_buckets_zero_filled_after_reconciliation', valid, True)
    assert result['M'] == 0 and result['D'] == 10 and result['state_counts']['diamond'] == 0
    sample = deepcopy(valid)
    sample['meta'].pop('groups_count'); sample['meta'].pop('next_cursor'); sample.pop('results')
    execute('optional_meta_and_results_absent', sample, True)
    sample = deepcopy(valid)
    sample['group_by'].append({'key': 'unknown', 'count': 2})
    sample['meta'].update(count=12, groups_count=3)
    result = execute('identified_nonzero_unknown', sample, True)
    assert result['N'] == 12 and result['M'] == 2 and result['D'] == 10
    for name, field, value in [
        ('count_bool', 'count', True), ('count_negative', 'count', -1),
        ('count_float', 'count', 7.0), ('unexpected_enum', 'key', 'new_colour'),
        ('null_group_key', 'key', None), ('nested_group', 'group_by', [])
    ]:
        sample = deepcopy(valid); sample['group_by'][0][field] = value
        execute(name, sample, False)
    for name, field, value in [
        ('meta_count_bool', 'count', True), ('meta_count_negative', 'count', -1),
        ('count_reconciliation_failure', 'count', 11),
        ('groups_count_bool', 'groups_count', True),
        ('groups_count_mismatch', 'groups_count', 3),
        ('nonempty_cursor', 'next_cursor', 'next-page')
    ]:
        sample = deepcopy(valid); sample['meta'][field] = value
        execute(name, sample, False)
    sample = deepcopy(valid); sample['group_by'][1]['key'] = 'closed'
    execute('duplicate_group_key', sample, False)
    sample = deepcopy(valid); sample['results'] = [{'id': 'unrequested'}]
    execute('unrequested_work_records', sample, False)
    sample = deepcopy(valid); sample['results'] = None
    execute('null_results_is_not_empty_array', sample, False)
    execute('http_not_200', valid, False, status=503)
    execute('body_cap', valid, False, raw=b' ' * 262145)
    execute('invalid_utf8', valid, False, raw=b'\xff')
    execute('invalid_json', valid, False, raw=b'{')
    execute('duplicate_object_key', valid, False,
            raw=b'{"meta":{"count":10,"count":10},"group_by":[]}')
    execute('non_json_numeric_constant', valid, False,
            raw=b'{"meta":{"count":NaN},"group_by":[]}')
    return {'status': 'PASS_SYNTHETIC_RAW_RESPONSE_CONTROLS',
            'checks': len(cases), 'cases': cases,
            'scope': 'Focused parser controls; no source acquisition or empirical analysis'}


if __name__ == '__main__':
    print(json.dumps(synthetic_parser_checks(), ensure_ascii=False, indent=2))
