import importlib.util
from pathlib import Path
import pytest
from app.domain.image_derivative import jpeg_preview

def test_missing_color_engine_is_actionable_not_an_opaque_failure(monkeypatch):
    from PIL import features
    monkeypatch.setattr(features,'check',lambda feature:False)
    with pytest.raises(ValueError,match='لا تتأثر'):jpeg_preview(b'irrelevant','#ffffff')

def test_missing_color_engine_does_not_block_startup(monkeypatch,capsys):
    path=Path(__file__).resolve().parents[2]/'scripts/check_arabic_renderer.py'
    spec=importlib.util.spec_from_file_location('runtime_preflight',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    original=module.features.check
    monkeypatch.setattr(module.features,'check',lambda key:False if key=='littlecms2' else original(key))
    module.main()
    assert 'Existing publishing remains available' in capsys.readouterr().out
