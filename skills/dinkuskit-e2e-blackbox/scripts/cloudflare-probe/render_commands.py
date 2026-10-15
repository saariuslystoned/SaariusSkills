#!/usr/bin/env python3
"""Render public-only shell commands; invoke with Crabbox --no-sync --shell."""
import base64
import json
from pathlib import Path
import shlex
import sys

ROOT = Path(__file__).resolve().parent
REMOTE = '/workspace/crabbox/e2e-probe'


def commands():
    files = {
        name: base64.b64encode((ROOT / name).read_bytes()).decode()
        for name in ('package.json', 'package-lock.json', 'prepare.sh', 'probe.mjs')
    }
    bootstrap = (
        "const fs=require('node:fs');"
        f"const root={json.dumps(REMOTE)};"
        "fs.mkdirSync(root,{recursive:true});"
        f"const files={json.dumps(files, separators=(',', ':'))};"
        "for(const [name,data] of Object.entries(files))"
        "fs.writeFileSync(root+'/'+name,Buffer.from(data,'base64'),{flag:'wx'});"
    )
    run = (
        f'cd {REMOTE}\n'
        f'export PLAYWRIGHT_BROWSERS_PATH={REMOTE}/browsers\n'
    )
    return {
        'run1': 'set -euo pipefail\nnode -e ' + shlex.quote(bootstrap)
                + f'\nbash {REMOTE}/prepare.sh\n' + run + 'node probe.mjs run1',
        'run2': 'set -euo pipefail\n' + run + 'node probe.mjs run2',
    }


if __name__ == '__main__':
    rendered = commands()
    if len(sys.argv) == 2 and sys.argv[1] in rendered:
        print(rendered[sys.argv[1]])
    elif len(sys.argv) == 1:
        print(json.dumps(rendered, indent=2))
    else:
        raise SystemExit('Usage: render_commands.py [run1|run2]')
