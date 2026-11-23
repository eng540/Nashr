import io
import zipfile

import pytest
from app.api.library_import import validate_archive, MAX_FILES


def archive(entries):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as z:
        for name, value in entries:
            z.writestr(name, value)
    return stream.getvalue()


def test_topic_archive():
    assert validate_archive(archive([('content/P1/P1-001.md', '# Topic')])) == [('content/P1/P1-001.md', b'# Topic')]


@pytest.mark.parametrize('name', ['../escape.md', '/content/P1/P1-1.md', 'content/../evil.md', 'run.py', 'content\\P1\\P1-1.md'])
def test_reject_unsafe_paths(name):
    with pytest.raises(ValueError):
        validate_archive(archive([(name, 'x')]))


def test_design_index_must_match_files():
    with pytest.raises(ValueError):
        validate_archive(archive([('designs/index.csv', 'الملف\n../../private.webp')]))
    with pytest.raises(ValueError):
        validate_archive(archive([('designs/batch-01/d01.webp', b'RIFFxxxxWEBP')]))


def test_design_archive():
    entries = [('designs/index.csv', 'الملف\ndesigns/batch-01/d01.webp'), ('designs/batch-01/d01.webp', b'RIFFxxxxWEBP')]
    assert len(validate_archive(archive(entries))) == 2


def test_too_many_and_duplicate():
    with pytest.raises(ValueError):
        validate_archive(archive([(f'content/P1/P1-{i}.md', 'x') for i in range(MAX_FILES + 1)]))
    with pytest.raises(ValueError):
        validate_archive(archive([('content/P1/P1-1.md', 'x'), ('content/P1/P1-1.md', 'x')]))
