"""Write public build identity; only HEAD/refs are included in the build context."""
import json
from pathlib import Path
import re
import sys
from datetime import datetime, timezone

def metadata(git_dir):
    git_dir=Path(git_dir)
    revision=(git_dir/'HEAD').read_text().strip()
    if revision.startswith('ref: '):
        ref=revision[5:]
        if ref not in ('refs/heads/main','refs/heads/master'):
            raise ValueError('Unsupported build branch')
        path=git_dir/ref
        if path.exists():revision=path.read_text().strip()
        else:
            packed=(git_dir/'packed-refs').read_text().splitlines()
            revision=next(line.split()[0] for line in packed if line.endswith(' '+ref))
    if not re.fullmatch('[a-f0-9]{40}',revision):raise ValueError('Invalid build revision')
    return {'revision':revision,'built':datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}

if __name__=='__main__':
    Path(sys.argv[2]).write_text(json.dumps(metadata(sys.argv[1])),encoding='utf-8')
