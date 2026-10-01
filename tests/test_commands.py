import asyncio, pytest
from backend import config
from backend.commands import CommandsMixin


class Fake(CommandsMixin):
    def __init__(self): self.sent = []
    async def send_command(self, body, name): self.sent.append((body, name))

@pytest.fixture(autouse=True)
def cfg(monkeypatch):
    monkeypatch.setattr(config, "ALLOWED_LOCOS", {"l1"})
    monkeypatch.setattr(config, "ALLOWED_SWITCHES", {"s1"})
    monkeypatch.setattr(config, "MAX_SPEED", 50)

def run(c): return asyncio.run(c)

def test_speed_capped():
    f = Fake(); assert run(f.set_speed("l1", 100)) == 50
    assert 'V="50"' in f.sent[0][0]

def test_negative_speed_floored():
    f = Fake(); assert run(f.set_speed("l1", -5)) == 0

def test_disallowed_loco_rejected():
    f = Fake()
    with pytest.raises(PermissionError): run(f.set_speed("other", 10))
    assert f.sent == []

def test_disallowed_switch_rejected():
    f = Fake()
    with pytest.raises(PermissionError): run(f.throw_switch("nope"))

def test_direction_is_single_command_at_speed_zero():
    f = Fake(); run(f.set_direction("l1", False))
    assert len(f.sent) == 1
    assert 'V="0"' in f.sent[0][0] and 'dir="false"' in f.sent[0][0] and 'cmd="velocity"' in f.sent[0][0]

def test_stop_sends_velocity_zero():
    f = Fake(); run(f.stop("l1"))
    assert 'V="0"' in f.sent[0][0] and 'cmd="velocity"' in f.sent[0][0]

def test_bad_switch_position():
    f = Fake()
    with pytest.raises(ValueError): run(f.throw_switch("s1", "explode"))

def test_id_is_escaped():
    f = Fake(); config.ALLOWED_LOCOS.add('a"b'); run(f.stop('a"b'))
    assert 'id="a"b"' not in f.sent[0][0]