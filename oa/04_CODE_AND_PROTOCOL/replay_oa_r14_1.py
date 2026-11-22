"""Rebuild and independently verify all released R14.1 OA outputs offline.

This replays the separately captured recovery batch, not the lost R14 batch.
Choose a new output directory outside the package. No live acquisition runs.
"""
from pathlib import Path
from hashlib import sha256
from datetime import datetime, timezone
import argparse
import importlib.metadata
import json
import platform
import subprocess
import sys

sys.dont_write_bytecode = True
from verify_bundle_r14_1 import verify


def digest(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--output', type=Path, required=True)
    a = parser.parse_args(); root = a.bundle.resolve(); out = a.output.resolve()
    if out.exists() or out.is_relative_to(root):
        raise SystemExit('Output must be a new directory outside the input bundle')
    initial = verify(root)
    if initial['errors']:
        raise SystemExit(json.dumps(initial))
    out.mkdir(parents=True); started = datetime.now(timezone.utc).isoformat()
    code = root / '04_CODE_AND_PROTOCOL'; frozen = code / 'frozen'; independent = code / 'independent'
    data = root / '02_OA_DATA_AND_RESULTS'; audit = root / '05_AUDIT_AND_CONTINUITY'
    batch = data / 'batch_01/R14_1_OA_ACQUISITION_BATCH.json'
    commands = []

    def execute(args):
        command = [sys.executable, '-B', '-X', 'utf8', *map(str, args)]
        result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', timeout=120)
        commands.append({'program': Path(str(args[0])).name, 'exit_code': result.returncode})
        if result.returncode:
            raise RuntimeError('Replay command failed: ' + result.stderr[-4000:] + result.stdout[-1000:])

    def check_results(input_path, point_path, secondary_path, adapter, output_name):
        report = out / output_name
        execute([independent / 'verify_oa_r141.py', '--protocol', frozen / 'R13_EMPIRICAL_PROTOCOL_EN_GB.json',
                 '--queries', frozen / 'R13_OA_QUERY_MANIFEST.json', '--batch', batch, '--input', input_path,
                 '--point', point_path, '--secondary', secondary_path, '--adapter-review', adapter,
                 '--contracts-dir', code / 'r13_contracts', '--report', report])
        value = json.loads(report.read_bytes())
        if value['status'] != 'PASS_INDEPENDENT_OA_RECOVERY_VERIFICATION':
            raise RuntimeError('Independent result review failed')
        return value

    original = check_results(data / 'R14_1_OA_NORMALISED_INPUT.json', data / 'results_01/R14_1_OA_POINT_RESULTS.json',
                             data / 'results_01/R14_1_OA_SECONDARY_RESULTS.json',
                             audit / 'R14_1_OA_ADAPTER_INDEPENDENT_REVIEW.json', 'ORIGINAL_INDEPENDENT_REVIEW.json')
    candidate = out / 'R14_1_OA_CANDIDATE_INPUT.json'; coverage = out / 'R14_1_OA_COVERAGE.json'
    normalised = out / 'R14_1_OA_NORMALISED_INPUT.json'; adapter = out / 'REPLAY_ADAPTER_REVIEW.json'
    execute([code / 'oa_pipeline_r14_1.py', 'normalise', '--protocol', frozen / 'R13_EMPIRICAL_PROTOCOL_EN_GB.json',
             '--batch', batch, '--output', candidate, '--coverage', coverage])
    execute([independent / 'verify_oa_adapter_r14_1.py', '--mode', 'approve',
             '--protocol', frozen / 'R13_EMPIRICAL_PROTOCOL_EN_GB.json', '--queries', frozen / 'R13_OA_QUERY_MANIFEST.json',
             '--source-registry', frozen / 'R13_EMPIRICAL_SOURCE_EVIDENCE.json',
             '--amendment', audit / 'R14_1_AMENDMENT_01_RECOVERY.json', '--batch', batch,
             '--input', candidate, '--coverage', coverage,
             '--acquisition-code', code / 'implementation_history/oa_pipeline_r14_1_acquisition_01.py',
             '--normalisation-code', code / 'oa_pipeline_r14_1.py', '--accepted-output', normalised, '--report', adapter])
    execute([code / 'oa_pipeline_r14_1.py', 'diagnose', '--protocol', frozen / 'R13_EMPIRICAL_PROTOCOL_EN_GB.json',
             '--input', normalised, '--adapter-review', adapter, '--output', out / 'results'])
    repeated = check_results(normalised, out / 'results/R14_1_OA_POINT_RESULTS.json', out / 'results/R14_1_OA_SECONDARY_RESULTS.json',
                             adapter, 'RECOMPUTED_INDEPENDENT_REVIEW.json')
    table = out / 'R14_1_OA_REPORTING_TABLES.json'
    execute([code / 'build_reporting_r14_1.py', '--input', normalised, '--point', out / 'results/R14_1_OA_POINT_RESULTS.json',
             '--secondary', out / 'results/R14_1_OA_SECONDARY_RESULTS.json', '--coverage', coverage, '--output', table])
    reporting_report = out / 'RECOMPUTED_REPORTING_REVIEW.json'
    execute([independent / 'verify_reporting_r141.py', '--protocol', frozen / 'R13_EMPIRICAL_PROTOCOL_EN_GB.json',
             '--input', normalised, '--point', out / 'results/R14_1_OA_POINT_RESULTS.json',
             '--secondary', out / 'results/R14_1_OA_SECONDARY_RESULTS.json', '--coverage', coverage,
             '--batch', batch, '--tables', table, '--report', reporting_report])
    reporting_review = json.loads(reporting_report.read_bytes())
    if (reporting_review.get('status') != 'PASS_INDEPENDENT_OA_REPORTING_MAPPING'
            or type(reporting_review.get('comparisons')) is not int or reporting_review['comparisons'] <= 0
            or reporting_review.get('maximum_exact_numeric_residual') != '0'
            or reporting_review.get('failures') != []):
        raise RuntimeError('Independent reporting review failed')
    reporting_inputs = {'protocol': frozen / 'R13_EMPIRICAL_PROTOCOL_EN_GB.json',
                        'input': normalised, 'point': out / 'results/R14_1_OA_POINT_RESULTS.json',
                        'secondary': out / 'results/R14_1_OA_SECONDARY_RESULTS.json',
                        'coverage': coverage, 'batch': batch, 'tables': table}
    if (reporting_review.get('identities') != {key: digest(path) for key, path in reporting_inputs.items()}
            or reporting_review.get('verifier_sha256') != digest(independent / 'verify_reporting_r141.py')
            or reporting_review.get('math_module_sha256') != digest(independent / 'r141_independent_math.py')):
        raise RuntimeError('Independent reporting review identity mismatch')
    pairs = [(data / 'R14_1_OA_CANDIDATE_INPUT.json', candidate), (data / 'R14_1_OA_COVERAGE.json', coverage),
             (data / 'R14_1_OA_NORMALISED_INPUT.json', normalised), (data / 'results_01/R14_1_OA_POINT_RESULTS.json', out / 'results/R14_1_OA_POINT_RESULTS.json'),
             (data / 'results_01/R14_1_OA_SECONDARY_RESULTS.json', out / 'results/R14_1_OA_SECONDARY_RESULTS.json'),
             (data / 'R14_1_OA_REPORTING_TABLES.json', table)]
    equality = {left.name: digest(left) == digest(right) for left, right in pairs}
    if not all(equality.values()):
        raise RuntimeError('Substantive recovery outputs differ: ' + json.dumps(equality))
    final = verify(root)
    if initial != final:
        raise RuntimeError('Input package changed during replay')
    report = {'status': 'PASS_OFFLINE_RECOVERY_REPLAY', 'started_utc': started,
              'completed_utc': datetime.now(timezone.utc).isoformat(), 'input_manifest_sha256': initial['manifest_sha256'],
              'input_payload_files': initial['payload_files'], 'input_bundle_unchanged': True,
              'byte_identical_substantive_outputs': equality,
              'original_independent_comparisons': original['total_comparisons'],
              'recomputed_independent_comparisons': repeated['total_comparisons'],
              'maximum_exact_numeric_residual': repeated['maximum_exact_numeric_residual'],
              'reporting_review': {'status': reporting_review['status'], 'comparisons': reporting_review['comparisons'],
                                   'maximum_exact_numeric_residual': reporting_review['maximum_exact_numeric_residual'],
                                   'review_sha256': digest(reporting_report),
                                   'verifier_sha256': reporting_review['verifier_sha256'],
                                   'math_module_sha256': reporting_review['math_module_sha256'],
                                   'reporting_tables_sha256': digest(table)},
              'commands': commands, 'network_requests': 0, 'new_MC_replications': 0,
              'runtime': {'python': platform.python_version(), 'platform': sys.platform, 'jsonschema': importlib.metadata.version('jsonschema')},
              'limits': 'R14.1 captured OA only; no restoration of original R14 bytes, provider-classification audit, FAT release approval or native Windows/Word certification.',
              'timestamped_receipts': 'New timestamps and adapter/execution receipt hashes differ intentionally; six substantive files compared byte for byte.'}
    (out / 'R14_1_OFFLINE_REPLAY_REPORT.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
