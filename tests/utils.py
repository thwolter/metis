from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import URL, make_url


def load_fixtures(name: str, *, url: URL | None = None):
    if not url:
        url_str = os.environ.get('POSTGRES_URL')
        if not url_str:
            raise RuntimeError('POSTGRES_URL is not set')
        url = make_url(url_str)
    env = os.environ.copy()

    # Set testcontainer database attributes
    env['PGPASSWORD'] = 'test'
    username = 'test'
    database = 'test'

    file_path = Path(__file__).parent / 'fixtures' / name

    try:
        subprocess.run(
            [
                'psql',
                '-v',
                'ON_ERROR_STOP=1',
                '-h',
                str(url.host),
                '-p',
                str(url.port),
                '-U',
                username,
                '-d',
                database,
                '-f',
                str(file_path),
            ],
            check=True,
            capture_output=True,
            text=True,
            env=env,
        )
    except subprocess.CalledProcessError as e:
        # Print stderr cleanly and abort tests
        print(f'[load_fixtures] Error running {file_path.name}:', file=sys.stderr)
        print(e.stderr, file=sys.stderr)
        if 'already exists' not in e.stderr:
            raise SystemExit(1)
