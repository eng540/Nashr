import pytest
from app.main import schedule_trigger_interval


@pytest.mark.parametrize('raw,expected',[(None,30.0),('30',30.0),('5',5.0),('5.5',5.5),('600',600.0),('',30.0),('bad',30.0),('0',30.0),('-5',30.0),('4.999',30.0),('nan',30.0),('NaN',30.0),('inf',30.0),('-inf',30.0),('Infinity',30.0),('1e1000',30.0)])
def test_scheduler_interval_is_finite_and_not_below_minimum(monkeypatch,raw,expected):
    if raw is None:
        monkeypatch.delenv('SCHEDULE_TRIGGER_INTERVAL_SECONDS',raising=False)
    else:
        monkeypatch.setenv('SCHEDULE_TRIGGER_INTERVAL_SECONDS',raw)
    assert schedule_trigger_interval()==expected
