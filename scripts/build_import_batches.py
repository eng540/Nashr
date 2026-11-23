"""Build bounded ZIP batches for the authenticated Engineering540 importer."""
import argparse
import csv
import io
from pathlib import Path
import zipfile


def build(root: Path, destination: Path, batch_size: int = 50):
    destination.mkdir(parents=True, exist_ok=True)
    topics = sorted((root / 'content').glob('P*/P*-*.md'))
    for start in range(0, len(topics), batch_size):
        with zipfile.ZipFile(destination / f'topics-{start//batch_size+1:02}.zip', 'w', zipfile.ZIP_DEFLATED) as z:
            for path in topics[start:start+batch_size]:
                z.write(path, str(path.relative_to(root)))
    with (root / 'designs/index.csv').open(encoding='utf-8-sig', newline='') as handle:
        reader = csv.DictReader(handle)
        fields, rows = reader.fieldnames, list(reader)
    for start in range(0, len(rows), batch_size):
        selected = rows[start:start+batch_size]
        stream = io.StringIO()
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(selected)
        with zipfile.ZipFile(destination / f'designs-{start//batch_size+1:02}.zip', 'w', zipfile.ZIP_DEFLATED) as z:
            z.writestr('designs/index.csv', stream.getvalue())
            for row in selected:
                name = row['الملف'].strip()
                z.write(root / name, name)
    return len(topics), len(rows)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(build(args.root, args.output))
