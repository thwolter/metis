from __future__ import annotations

import os
import subprocess
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

    subprocess.run(
        ['psql', '-h', str(url.host), '-p', str(url.port), '-U', username, '-d', database, '-f', str(file_path)],
        check=True,
        env=env,
    )
