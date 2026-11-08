#!/usr/bin/env python3
"""Verify a published prompt-comparison archive without network access or model calls.

Run from an extracted archive with Python 3.13 (the tested version):
    python3 reproduce_prompt.py
    python3 reproduce_prompt.py --root results/live_prompt

Install scipy==1.18.1 before this offline check. The default root is relative to this script, not the working directory. The
archive must contain audit_prompt.py and prompt_archive_manifest.json beside
this script. The manifest lists every regular archive file except itself under
{"schema":"prompt-archive-manifest-1","files":{"relative/path":"sha256"}}.
SQLite files must be complete backups, with no pending WAL data or sidecars.

This verifier loads the frozen package in the selected result folder. It checks
all 340 run scores and the 320-run main analysis. It also checks saved prompts,
linked logs, source hashes, cost limits, prior receipts, and authorization. It
does not rerun model inference or verify provider account deductions. A manifest
checks archive consistency; it does not prove the origin of an untrusted archive.
No files are written. The JSON report is printed to standard output.
"""
from __future__ import annotations

import argparse
from contextlib import closing, contextmanager
import hashlib
import importlib.util
import json
from pathlib import Path
import socket
import sqlite3
import sys


BASE = Path(__file__).resolve().parent


def read_json(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('A JSON record has a repeated key')
            result[key] = value
        return result

    def invalid_constant(value):
        raise ValueError('A JSON record has a non-finite number: ' + value)

    return json.loads(Path(path).read_text(encoding='utf-8'), object_pairs_hook=unique,
                      parse_constant=invalid_constant)


def sha256(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def checked_path(base, name):
    if not isinstance(name, str) or not name or Path(name).is_absolute():
        raise ValueError('An archive path must be relative')
    lexical = Path(name)
    if '..' in lexical.parts or str(lexical) != name:
        raise ValueError('An archive path is not canonical: ' + name)
    path = base / lexical
    if path.is_symlink() or any(parent.is_symlink() for parent in path.parents if parent != base):
        raise ValueError('Archive symlinks are not supported: ' + name)
    if not path.resolve().is_relative_to(base):
        raise ValueError('An archive path leaves its root: ' + name)
    return path


def verify_manifest(manifest_path):
    manifest_path = Path(manifest_path).resolve()
    base = manifest_path.parent
    record = read_json(manifest_path)
    files = record.get('files') if isinstance(record, dict) else None
    if (record.get('schema') != 'prompt-archive-manifest-1'
            or not isinstance(files, dict) or not files):
        raise ValueError('The archive hash manifest is missing or invalid')
    expected = set()
    for name, expected_hash in files.items():
        path = checked_path(base, name)
        if path == manifest_path:
            raise ValueError('The manifest cannot list itself')
        if (not isinstance(expected_hash, str) or len(expected_hash) != 64
                or any(char not in '0123456789abcdef' for char in expected_hash)):
            raise ValueError('An archive SHA256 value is invalid: ' + name)
        if not path.is_file() or sha256(path) != expected_hash:
            raise ValueError('An archive file is missing or changed: ' + name)
        if path.name.endswith(('.sqlite-wal', '.sqlite-shm')):
            raise ValueError('Archive ledgers must be complete SQLite backups')
        expected.add(name)
    actual = set()
    for path in base.rglob('*'):
        if path.is_symlink():
            raise ValueError('Archive symlinks are not supported')
        if path.is_file() and path != manifest_path:
            actual.add(path.relative_to(base).as_posix())
    if actual != expected:
        raise ValueError('The archive contains files absent from its hash manifest')
    return base, files


@contextmanager
def no_network():
    def denied(*args, **kwargs):
        raise RuntimeError('Network access is disabled for archive verification')
    saved = socket.socket.connect, socket.create_connection, socket.getaddrinfo
    socket.socket.connect = socket.create_connection = socket.getaddrinfo = denied
    try:
        yield
    finally:
        socket.socket.connect, socket.create_connection, socket.getaddrinfo = saved


def immutable_database(path):
    """Read a complete archive backup without creating SQLite sidecar files."""
    uri = Path(path).resolve().as_uri() + '?mode=ro&immutable=1'
    with closing(sqlite3.connect(uri, uri=True)) as db:
        db.row_factory = sqlite3.Row
        metadata = dict(db.execute('SELECT key,value FROM metadata'))
        rows = [dict(row) for row in db.execute('SELECT * FROM attempts ORDER BY rowid')]
    return metadata, rows


def reproduce(root, manifest_path):
    root = Path(root).resolve()
    archive, files = verify_manifest(manifest_path)
    if not root.is_relative_to(archive):
        raise ValueError('The result folder is outside the checked archive')
    study, status = read_json(root / 'study.json'), read_json(root / 'status.json')
    if study.get('protocol') != 'prompt-comparison-1.0' or status.get('status') != 'complete':
        raise ValueError('Reproduction requires a completed prompt-comparison-1.0 study')
    main = read_json(root / 'results.json')
    if not isinstance(main, list) or len(main) != 320:
        raise ValueError('The complete study requires 320 main result records')
    if not (root / 'analysis.json').is_file():
        raise ValueError('The saved main analysis is missing')
    source = (root / 'source').resolve()
    hashes = study.get('source_hashes')
    if not isinstance(hashes, dict) or not hashes:
        raise ValueError('The frozen source hash list is missing')
    for name, expected in hashes.items():
        path = checked_path(source, name)
        if not path.is_file() or sha256(path) != expected:
            raise ValueError('A frozen source file differs: ' + name)
    for name in ('__init__', 'analysis', 'environment', 'common'):
        if 'prompt_study/' + name + '.py' not in hashes:
            raise ValueError('A required frozen module has no saved hash')
    if any(name == 'prompt_study' or name.startswith('prompt_study.') for name in sys.modules):
        raise ValueError('Run this verifier in a fresh Python process')
    audit_path = archive / 'audit_prompt.py'
    saved_audit = read_json(root / 'audit.json')
    if (saved_audit.get('passed') is not True or saved_audit.get('issues') != []
            or saved_audit.get('audit_source_sha256') != sha256(audit_path)):
        raise ValueError('The saved audit did not pass or its source differs')
    prior_roots, authorization_path = {}, None
    if study.get('mode') == 'live':
        receipt = read_json(root / 'prior_study_receipt.json')
        chain = receipt
        for folder in ('live_followup', 'live_paced', 'live'):
            path = chain.get('root')
            if not isinstance(path, str) or path in prior_roots:
                raise ValueError('The prior receipt paths must be distinct')
            prior_roots[path] = root.parent / folder
            chain = chain.get('previous_carry', {})
        authorization_path = root.parent / 'prompt_authorization' / 'claim.json'
        if not authorization_path.is_file():
            raise ValueError('The shared authorization claim is missing from the archive')
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(source))
    with no_network():
        spec = importlib.util.spec_from_file_location('prompt_reproduction_audit', audit_path)
        if spec is None or spec.loader is None:
            raise ValueError('Cannot load the saved audit source')
        audit_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(audit_module)
        for name, module in tuple(sys.modules.items()):
            if name == 'prompt_study' or name.startswith('prompt_study.'):
                if not Path(module.__file__).resolve().is_relative_to(source):
                    raise ValueError('A scorer was loaded outside the frozen source tree')
        audit_module.database = immutable_database
        report = audit_module.audit(root, write_report=False, prior_roots=prior_roots,
                                    authorization_path=authorization_path)
    counts = report.get('counts', {})
    issues = list(report.get('issues', []))
    for name, expected in [('runs', 340), ('complete_runs', 340), ('outcomes', 8072)]:
        if counts.get(name) != expected:
            issues.append('The complete archive count differs: ' + name)
    # This also detects an unexpected write during frozen-source execution.
    _, after_files = verify_manifest(manifest_path)
    if after_files != files:
        issues.append('The archive manifest changed during verification')
    return {'schema': 'prompt-reproduction-1', 'passed': report.get('passed') is True and not issues,
            'issues': issues, 'mode': study['mode'], 'study_status': status['status'],
            'network_blocked': True, 'paid_calls': 0, 'files_written': 0,
            'billing_verified': False, 'archive_files_checked': len(files),
            'frozen_source_files_checked': len(hashes), 'main_runs_recomputed': len(main),
            'counts': counts, 'audit_source_sha256': sha256(audit_path),
            'scope': 'Frozen run scores, main analysis, prompts, logs, source hashes, cost carry, limits, and authorization.'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=BASE / 'results' / 'live_prompt')
    parser.add_argument('--manifest', type=Path, default=BASE / 'prompt_archive_manifest.json')
    args = parser.parse_args(argv)
    try:
        report = reproduce(args.root, args.manifest)
    except Exception as error:
        report = {'schema': 'prompt-reproduction-1', 'passed': False,
                  'issues': [f'{type(error).__name__}: {error}'], 'paid_calls': 0,
                  'files_written': 0, 'billing_verified': False}
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
