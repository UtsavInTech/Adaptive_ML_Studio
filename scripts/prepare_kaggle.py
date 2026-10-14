"""Fetch pinned public Kaggle archives and rebuild the local dataset snapshots.

No API token required. Pass --elec2-archive /path.zip and --occupancy-archive
/path.zip to use files downloaded through Kaggle's browser instead.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
from urllib.request import urlopen
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]


def prepare(entry, archive: bytes):
    if hashlib.sha256(archive).hexdigest() != entry['archive_sha256']:
        raise ValueError(f"Archive checksum mismatch for {entry['id']}; inspect upstream changes before replacing data")
    folder = ROOT / 'data' / 'kaggle' / entry['id']
    folder.mkdir(parents=True, exist_ok=True)
    with ZipFile(io.BytesIO(archive)) as z:
        if entry['id'] == 'elec2':
            raw = z.read('electricity-normalized.csv')
        elif entry['id'] == 'occupancy':
            combined = []
            for name in ('datatest.txt', 'datatraining.txt', 'datatest2.txt'):
                original = z.read(name)
                (folder / name).write_bytes(original)
                reader = csv.reader(io.StringIO(original.decode('utf-8-sig')))
                header = ['sample_id', *next(reader)]
                for values in reader:
                    if len(values) != len(header):
                        raise ValueError(f'Unexpected column count in {name}')
                    combined.append(dict(zip(header, values), source_file=name))
            combined.sort(key=lambda row: row['date'])
            out = io.StringIO(newline='')
            writer = csv.DictWriter(out, fieldnames=[*header, 'source_file'], lineterminator='\n')
            writer.writeheader(); writer.writerows(combined)
            raw = out.getvalue().encode()
        else:
            raise ValueError(f"Unsupported preparation: {entry['id']}")
    if hashlib.sha256(raw).hexdigest() != entry['sha256']:
        raise ValueError(f"Prepared checksum mismatch for {entry['id']}")
    target = ROOT / 'data' / entry['file']
    target.write_bytes(raw)
    print(f"Verified {entry['id']}: {entry['rows']:,} rows → {target}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--elec2-archive', type=Path)
    parser.add_argument('--occupancy-archive', type=Path)
    args = parser.parse_args()
    for entry in json.loads((ROOT / 'data/catalog.json').read_text()):
        path = getattr(args, entry['id'] + '_archive')
        if path:
            archive = path.read_bytes()
        else:
            with urlopen(entry['download_url'], timeout=60) as response:
                archive = response.read()
        prepare(entry, archive)


if __name__ == '__main__':
    main()
