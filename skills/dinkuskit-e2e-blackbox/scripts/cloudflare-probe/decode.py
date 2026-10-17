#!/usr/bin/env python3
"""Decode only public probe artifacts; refuse partial or corrupted transfers."""
import base64
import hashlib
import json
from pathlib import Path
import sys
import zipfile

PREFIX = 'E2E_PUBLIC_ARTIFACT_V1 '
NAMES = {'page.png', 'trace.zip', 'result.json'}
CAP = 16 * 1024 * 1024
CHUNK_SIZE = 32768
MAX_LINE = 65536
TRACE_ENTRY_CAP = 16 * 1024 * 1024
TRACE_TOTAL_CAP = 64 * 1024 * 1024
TRACE_ENTRY_COUNT = 1024


def records(source):
    with Path(source).open() as stream:
        while True:
            line = stream.readline(MAX_LINE + 1)
            if not line:
                return
            if len(line) > MAX_LINE:
                raise ValueError('Artifact record exceeds line limit')
            if line.startswith(PREFIX):
                yield json.loads(line[len(PREFIX):])


def decode(source, destination, run_id):
    if run_id not in ('run1', 'run2'):
        raise ValueError('Expected run1 or run2')
    active, completed, buffers = {}, {}, {}
    terminal = None
    for item in records(source):
        if item['runId'] != run_id:
            raise ValueError('Wrong run identity')
        kind = item['kind']
        if kind == 'complete':
            if terminal is not None or active:
                raise ValueError('Unexpected completion')
            terminal = item['status']
            continue
        name = item['name']
        if terminal is not None or name not in NAMES:
            raise ValueError('Unexpected artifact')
        if kind == 'begin':
            if (name in active or name in completed or type(item['size']) is not int
                    or not 0 <= item['size'] <= CAP):
                raise ValueError('Duplicate or oversized artifact')
            if (type(item['chunks']) is not int
                    or item['chunks'] != (item['size'] + CHUNK_SIZE - 1) // CHUNK_SIZE):
                raise ValueError('Invalid chunk count')
            active[name] = {**item, 'bytes': bytearray(), 'next': 0}
        elif kind == 'chunk':
            entry = active[name]
            if item['n'] != entry['next'] or entry['next'] >= entry['chunks']:
                raise ValueError('Out-of-order chunk')
            part = base64.b64decode(item['data'], validate=True)
            if len(part) != min(CHUNK_SIZE, entry['size'] - len(entry['bytes'])):
                raise ValueError('Chunk size exceeded')
            entry['bytes'].extend(part)
            entry['next'] += 1
        elif kind == 'end':
            entry = active.pop(name)
            data = bytes(entry['bytes'])
            digest = hashlib.sha256(data).hexdigest()
            if (len(data) != entry['size'] or entry['next'] != entry['chunks']
                    or digest != entry['sha256'] or digest != item['sha256']):
                raise ValueError('Artifact integrity failure')
            completed[name] = {'size': len(data), 'sha256': digest}
            buffers[name] = data
        else:
            raise ValueError('Unknown record')
    if terminal not in ('PASS', 'FAIL') or active or 'result.json' not in completed:
        raise ValueError('Incomplete stream')
    result = json.loads(buffers['result.json'])
    if result['status'] != terminal or result['runId'] != run_id:
        raise ValueError('Result mismatch')
    if terminal == 'PASS' and completed.keys() != NAMES:
        raise ValueError('Missing passing artifacts')
    if 'page.png' in buffers and not buffers['page.png'].startswith(b'\x89PNG\r\n\x1a\n'):
        raise ValueError('Invalid PNG')
    if 'trace.zip' in buffers:
        import io
        with zipfile.ZipFile(io.BytesIO(buffers['trace.zip'])) as archive:
            entries = archive.infolist()
            if (len(entries) > TRACE_ENTRY_COUNT
                    or any(entry.file_size > TRACE_ENTRY_CAP for entry in entries)
                    or sum(entry.file_size for entry in entries) > TRACE_TOTAL_CAP):
                raise ValueError('Playwright trace ZIP exceeds expansion limits')
            if archive.testzip() is not None or not any(entry.filename.endswith('.trace') for entry in entries):
                raise ValueError('Invalid Playwright trace ZIP')
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    for name, data in buffers.items():
        (destination / name).write_bytes(data)
    receipt = {'runId': run_id, 'status': terminal, 'artifacts': completed}
    (destination / 'transfer-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    return receipt


if __name__ == '__main__':
    if len(sys.argv) != 4:
        raise SystemExit('Usage: decode.py CAPTURE NEW_OUTPUT_DIR run1|run2')
    print(json.dumps(decode(*sys.argv[1:]), indent=2))
