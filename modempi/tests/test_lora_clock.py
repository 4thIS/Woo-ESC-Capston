"""시계 신뢰 판정 — RTC 없는 모뎀Pi 가 옛 시각을 노드에 뿌리지 않게 (S6 spec §3)."""

from modempi.lora.clock import CLOCK_VALID_AFTER, clock_trusted

NOW = 1_800_000_000.0


def test_before_threshold_is_untrusted(tmp_path):
    assert clock_trusted(CLOCK_VALID_AFTER - 1.0, timesync_dir=str(tmp_path / "none")) is False


def test_without_timesyncd_falls_back_to_threshold(tmp_path):
    """개발 PC·CI 처럼 systemd-timesyncd 가 없으면 임계값만 본다."""
    assert clock_trusted(NOW, timesync_dir=str(tmp_path / "none")) is True


def test_timesyncd_present_but_not_yet_synced_is_untrusted(tmp_path):
    """fake-hwclock 이 복원한 옛 시각은 임계값을 넘는다 — 동기 표시가 없으면 믿지 않는다."""
    d = tmp_path / "timesync"
    d.mkdir()
    assert clock_trusted(NOW, timesync_dir=str(d)) is False


def test_timesyncd_synced_is_trusted(tmp_path):
    d = tmp_path / "timesync"
    d.mkdir()
    (d / "synchronized").touch()
    assert clock_trusted(NOW, timesync_dir=str(d)) is True
