#!/usr/bin/env python3
"""Verify the distribution, replay captured OA data or prepare scientific records.

These entry points use local inputs only and never start the Monte Carlo run.
Generated work must be placed in a new or empty directory outside the kit.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path, PurePosixPath
import platform
import shutil
import stat
import subprocess
import sys
import time
import zipfile

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent
VERSION = '1.0.0'
RECEIPT_NAME = 'ODSA_EXECUTION_RECEIPT.json'

def sha(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):digest.update(block)
    return digest.hexdigest()

def dump(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def safe_relative(raw):
    rel=PurePosixPath(raw)
    if not raw or rel.is_absolute() or '..' in rel.parts or '\\' in raw or ':' in raw or rel.as_posix()!=raw:
        raise ValueError('Unsafe or non-canonical relative path: '+raw)
    return rel

def payload_files(root):
    result=set()
    for directory,dirs,files in os.walk(root,followlinks=False):
        dirs[:]=[name for name in dirs if name!='.git']
        for name in dirs+files:
            if (Path(directory)/name).is_symlink():raise ValueError('Symlink in distributed payload')
        for name in files:result.add((Path(directory)/name).relative_to(root).as_posix())
    return result

def verify_manifest(root):
    path=root/'MANIFEST_SHA256.json'
    manifest=json.loads(path.read_bytes());expected=set()
    for row in manifest['files']:
        rel=safe_relative(row['path'])
        if row['path'] in expected or row['path']=='MANIFEST_SHA256.json':raise ValueError('Duplicate or self-referential manifest entry')
        expected.add(row['path']);p=root.joinpath(*rel.parts)
        if p.is_symlink() or not p.is_file() or p.stat().st_size!=row['bytes'] or sha(p)!=row['sha256']:
            raise ValueError('Manifest mismatch: '+row['path'])
    actual=payload_files(root)
    if actual!=expected|{'MANIFEST_SHA256.json'}:
        raise ValueError('Missing or unlisted payload: '+repr(sorted(actual^(expected|{'MANIFEST_SHA256.json'}))))
    return {'payload_files':len(expected),'manifest_sha256':sha(path)}

def verify_kit():
    result=verify_manifest(ROOT)
    roster=(ROOT/'FILE_ALLOWLIST.txt').read_text(encoding='utf-8').splitlines()
    if len(roster)!=len(set(roster)) or set(roster)!=payload_files(ROOT):
        raise ValueError('Release roster differs from the actual payload')
    projection=verify_manifest(ROOT/'oa')
    record=json.loads((ROOT/'evidence/SCIENTIFIC_ARCHIVE_IDENTITY_PC1.json').read_bytes())
    archive=ROOT/record['archive']
    if archive.stat().st_size!=record['bytes'] or sha(archive)!=record['sha256']:
        raise ValueError('Scientific archive identity differs')
    with zipfile.ZipFile(archive) as z:
        for p in sorted((ROOT/'simulation').rglob('*')):
            if p.is_file():
                member=record['root']+'/frozen_simulation/'+p.relative_to(ROOT/'simulation').as_posix()
                if hashlib.sha256(z.read(member)).hexdigest()!=sha(p):raise ValueError('Visible scientific source differs: '+member)
    return {'status':'PASS_KIT_INTEGRITY','version':VERSION,**result,'oa_projection':projection,
            'scientific_archive_sha256':record['sha256'],
            'scope':'Closed file identities and scientific source projection; not a publication approval or a new experiment.'}

def make_work(path):
    work=path.resolve()
    if work==ROOT or ROOT in work.parents or work in ROOT.parents:
        raise ValueError('Choose a new work directory outside the kit and its ancestors')
    if work.exists() and (not work.is_dir() or any(work.iterdir())):
        raise ValueError('Work directory must be new or empty; existing work is never overwritten')
    work.mkdir(parents=True,exist_ok=True)
    return work

def extract_checked(source,destination,strip_root):
    destination.mkdir(parents=True,exist_ok=False);count=0
    with zipfile.ZipFile(source) as z:
        seen=set()
        for item in z.infolist():
            if item.is_dir():continue
            rel=safe_relative(item.filename)
            if item.filename in seen or stat.S_ISLNK(item.external_attr>>16):raise ValueError('Duplicate or symlink archive member')
            seen.add(item.filename)
            if len(rel.parts)<2 or rel.parts[0]!=strip_root:raise ValueError('Unexpected scientific archive root')
            output=destination.joinpath(*rel.parts[1:]);output.parent.mkdir(parents=True,exist_ok=True)
            with z.open(item) as incoming,output.open('xb') as outgoing:shutil.copyfileobj(incoming,outgoing,1024*1024)
            count+=1
    return count

def run_logged(command,work,label):
    environment=dict(os.environ);environment['PYTHONDONTWRITEBYTECODE']='1';environment['PYTHONUTF8']='1'
    with (work/(label+'.stdout.log')).open('w',encoding='utf-8') as out,(work/(label+'.stderr.log')).open('w',encoding='utf-8') as err:
        process=subprocess.run(command,cwd=work,env=environment,stdout=out,stderr=err,check=False)
    if process.returncode:raise RuntimeError(label+' failed; inspect the logs in '+str(work))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation',choices=['verify','oa','prepare-simulation'])
    parser.add_argument('--work-dir',type=Path,help='New or empty directory outside the kit')
    args=parser.parse_args()
    if sys.version_info<(3,12):parser.error('Python 3.12 or newer is required; the recorded runtime is Python 3.12')
    if args.operation!='verify' and args.work_dir is None:parser.error('--work-dir is required for this operation')
    started=time.monotonic();verification=verify_kit()
    if args.operation=='verify':print(json.dumps(verification,indent=2));return
    if args.operation=='oa':
        try:importlib.metadata.version('jsonschema')
        except importlib.metadata.PackageNotFoundError:parser.error('Install requirements-oa.txt in a separate environment before the offline replay')
    work=make_work(args.work_dir)
    receipt={'version':VERSION,'packaging_source':'PC1','operation':args.operation,'started_utc':datetime.now(timezone.utc).isoformat(),
             'input_verification':verification,'python':platform.python_version(),'platform':platform.platform(),
             'network_acquisition_requested':False,'monte_carlo_replications_executed':0,'native_windows_acceptance_claimed':False}
    try:
        if args.operation=='oa':
            output=work/'oa_replay'
            run_logged([sys.executable,'-B','-X','utf8',str(ROOT/'oa/04_CODE_AND_PROTOCOL/replay_oa_r14_1.py'),'--bundle',str(ROOT/'oa'),'--output',str(output)],work,'oa_replay')
            report=json.loads((output/'R14_1_OFFLINE_REPLAY_REPORT.json').read_bytes())
            if report['status']!='PASS_OFFLINE_RECOVERY_REPLAY' or not all(report['byte_identical_substantive_outputs'].values()):raise ValueError('OA replay did not establish six substantive exact matches')
            receipt['oa_replay']=report
        elif args.operation=='prepare-simulation':
            identity=json.loads((ROOT/'evidence/SCIENTIFIC_ARCHIVE_IDENTITY_PC1.json').read_bytes())
            output=work/'scientific_records'
            receipt['extracted_members']=extract_checked(ROOT/identity['archive'],output,identity['root'])
            receipt['scientific_records_verification']=verify_manifest(output)
            receipt['scientific_root']=str(output)
            receipt['simulation_root']=str(output/'frozen_simulation')
            receipt['scope']='Verified extraction only. No simulator, numerical validator, scientific reconciliation or private-input replay is executed.'
        if verify_kit()!=verification:raise ValueError('Distributed kit changed during execution')
        receipt['status']='PASS'
    except Exception as exc:
        receipt['status']='FAIL';receipt['error']=type(exc).__name__+': '+str(exc)
        dump(work/RECEIPT_NAME,receipt);raise
    receipt['completed_utc']=datetime.now(timezone.utc).isoformat();receipt['duration_seconds']=round(time.monotonic()-started,3);receipt['kit_unchanged']=True
    dump(work/RECEIPT_NAME,receipt)
    print(json.dumps({'status':'PASS','operation':args.operation,'receipt':str(work/RECEIPT_NAME)},indent=2))

if __name__=='__main__':
    try:main()
    except (OSError,ValueError,RuntimeError,KeyError,zipfile.BadZipFile) as exc:
        print('ERROR: '+str(exc),file=sys.stderr);raise SystemExit(2)
