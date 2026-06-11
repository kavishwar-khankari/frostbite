from core.filesystem import BYTES_PER_GIB
from core import transfer_manager


def test_cold_transfer_gate_uses_gib(monkeypatch):
    monkeypatch.setattr(transfer_manager.settings, "cold_transfer_min_nas_used_gb", 3000.0)
    monkeypatch.setattr(transfer_manager, "nas_used_bytes", lambda: int(2999.5 * BYTES_PER_GIB))

    status = transfer_manager.cold_transfer_gate_status()

    assert status.can_start is False
    assert status.paused is True
    assert status.nas_used_gib == 2999.5
    assert status.limit_gib == 3000.0
    assert status.limit_bytes == 3000 * BYTES_PER_GIB
    assert "GiB" in (status.reason or "")


def test_cold_transfer_gate_opens_at_limit(monkeypatch):
    monkeypatch.setattr(transfer_manager.settings, "cold_transfer_min_nas_used_gb", 3000.0)
    monkeypatch.setattr(transfer_manager, "nas_used_bytes", lambda: 3000 * BYTES_PER_GIB)

    status = transfer_manager.cold_transfer_gate_status()

    assert status.can_start is True
    assert status.paused is False
    assert status.reason is None


def test_cold_transfer_gate_can_be_disabled(monkeypatch):
    monkeypatch.setattr(transfer_manager.settings, "cold_transfer_min_nas_used_gb", 0.0)
    monkeypatch.setattr(transfer_manager, "nas_used_bytes", lambda: None)

    status = transfer_manager.cold_transfer_gate_status()

    assert status.can_start is True
    assert status.paused is False
    assert status.limit_bytes == 0


def test_cold_transfer_gate_blocks_when_usage_unavailable(monkeypatch):
    monkeypatch.setattr(transfer_manager.settings, "cold_transfer_min_nas_used_gb", 3000.0)
    monkeypatch.setattr(transfer_manager, "nas_used_bytes", lambda: None)

    status = transfer_manager.cold_transfer_gate_status()

    assert status.can_start is False
    assert status.paused is True
    assert status.nas_used_gib is None
    assert "could not be read" in (status.reason or "")
