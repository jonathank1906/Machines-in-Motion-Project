import asyncio, pytest
from backend import config
from backend.commands import CommandsMixin, EStopActive


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

def test_speed_commands_after_estop_cannot_restart_train():
    async def scenario():
        f = Fake()
        await f.set_speed("l1", 30)
        await f.emergency_stop_all()
        with pytest.raises(EStopActive):
            await f.set_speed("l1", 40)
        return f

    f = run(scenario())
    assert not any('V="40"' in body for body, _ in f.sent)
    assert any('<sys cmd="ebreak"/>' in body for body, _ in f.sent)

def test_speed_command_already_in_flight_is_followed_by_estop_stop():
    async def scenario():
        started = asyncio.Event()
        release = asyncio.Event()

        class DelayedFake(Fake):
            async def send_command(self, body, name):
                if not started.is_set():
                    started.set()
                    await release.wait()
                await super().send_command(body, name)

        f = DelayedFake()
        moving = asyncio.create_task(f.set_speed("l1", 30))
        await started.wait()
        stopping = asyncio.create_task(f.emergency_stop_all())
        await asyncio.sleep(0)
        release.set()
        await moving
        await stopping
        with pytest.raises(EStopActive):
            await f.set_speed("l1", 40)
        return f

    f = run(scenario())
    assert f.sent[-1][1] == "sys"
    assert any('V="0"' in body for body, _ in f.sent)

def test_only_new_speed_command_after_reset_controls_train():
    async def scenario():
        f = Fake()
        await f.emergency_stop_all()
        with pytest.raises(EStopActive):
            await f.set_speed("l1", 25)
        await f.reset_estop()
        await f.set_speed("l1", 25)
        return f

    f = run(scenario())
    assert sum('V="25"' in body for body, _ in f.sent) == 1

def test_zero_speed_always_sends_stop_during_estop():
    async def scenario():
        f = Fake()
        await f.emergency_stop_all()
        await f.set_speed("l1", 0)
        return f

    f = run(scenario())
    assert 'V="0"' in f.sent[-1][0]
    assert f.sent[-1][1] == "lc"

def test_bad_switch_position():
    f = Fake()
    with pytest.raises(ValueError): run(f.throw_switch("s1", "explode"))

def test_id_is_escaped():
    f = Fake(); config.ALLOWED_LOCOS.add('a"b'); run(f.stop('a"b'))
    assert 'id="a"b"' not in f.sent[0][0]