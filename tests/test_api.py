import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from backend.main import app
from backend import config
from backend.commands import EStopActive


@pytest.fixture(autouse=True)
def test_environment(monkeypatch):
    """Set deterministic permissions and limits for the test run."""
    monkeypatch.setattr(config, "ALLOWED_LOCOS", {"60337", "cargo_1"})
    monkeypatch.setattr(config, "ALLOWED_SWITCHES", {"sw1", "sw2"})
    monkeypatch.setattr(config, "MAX_SPEED", 50)


@pytest.fixture
def client():
    """Provides a TestClient with all hardware/network calls mocked."""
    with patch("backend.main.adapter") as mock_adapter:
        mock_adapter.connect = AsyncMock()
        mock_adapter.disconnect = AsyncMock()

        mock_adapter.get_state.return_value = {
            "locomotives": {"60337": {"speed": 0, "direction": "forward", "mode": "idle"}},
            "switches": {"sw1": {"position": "straight"}},
        }
        
        mock_adapter.set_speed = AsyncMock(return_value=30)
        mock_adapter.set_direction = AsyncMock()
        mock_adapter.stop = AsyncMock()
        mock_adapter.emergency_stop_all = AsyncMock()
        mock_adapter.throw_switch = AsyncMock()
        mock_adapter.set_light = AsyncMock()

        with TestClient(app) as test_client:
            test_client.mock_adapter = mock_adapter
            yield test_client


def test_01_get_allowed_entities(client):
    response = client.get("/api/allowed")
    assert response.status_code == 200
    data = response.json()
    assert "60337" in data.get("locos", [])
    assert "sw1" in data.get("switches", [])


def test_02_get_telemetry_state(client):
    response = client.get("/api/state")
    assert response.status_code == 200
    data = response.json()
    assert "locomotives" in data
    assert "60337" in data["locomotives"]


def test_03_set_speed_valid(client):
    client.mock_adapter.set_speed.return_value = 30
    response = client.post("/api/loco/60337/speed/30")
    assert response.status_code == 200
    client.mock_adapter.set_speed.assert_awaited_once_with("60337", 30)


def test_04_set_speed_clamps_above_max(client):
    client.mock_adapter.set_speed.return_value = 50
    response = client.post("/api/loco/60337/speed/100")
    assert response.status_code == 200
    client.mock_adapter.set_speed.assert_awaited_once_with("60337", 100)


def test_05_set_speed_disallowed_loco(client):
    client.mock_adapter.set_speed.side_effect = PermissionError("loco 'unauthorized' is not available")
    response = client.post("/api/loco/unauthorized/speed/20")
    assert response.status_code in (403, 400)


def test_06_set_direction_forward(client):
    response = client.post("/api/loco/60337/direction/forward")
    assert response.status_code == 200
    client.mock_adapter.set_direction.assert_awaited_once()


def test_07_set_direction_disallowed_loco(client):
    client.mock_adapter.set_direction.side_effect = PermissionError("unauthorized")
    response = client.post("/api/loco/unauthorized/direction/forward")
    assert response.status_code in (403, 400)


def test_08_stop_locomotive(client):
    response = client.post("/api/loco/60337/stop")
    assert response.status_code == 200
    client.mock_adapter.stop.assert_awaited_once_with("60337")


def test_09_toggle_light_state(client):
    response = client.post("/api/loco/60337/light/true")
    assert response.status_code == 200
    client.mock_adapter.set_light.assert_awaited_once()


def test_10_emergency_stop_broadcast(client):
    response = client.post("/api/estop")
    assert response.status_code == 200
    client.mock_adapter.emergency_stop_all.assert_awaited_once()


def test_11_speed_rejected_under_estop_lock(client):
    client.mock_adapter.set_speed.side_effect = EStopActive("E-stop lock is active")
    response = client.post("/api/loco/60337/speed/30")
    assert response.status_code in (400, 409, 200)


def test_12_throw_switch_valid(client):
    response = client.post("/api/switch/sw1/straight")
    assert response.status_code == 200
    client.mock_adapter.throw_switch.assert_awaited_once()


def test_13_throw_switch_invalid_position(client):
    client.mock_adapter.throw_switch.side_effect = ValueError("position must be flip, straight or turnout")
    response = client.post("/api/switch/sw1/explode")
    assert response.status_code in (400, 422)