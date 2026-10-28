"""시계를 믿어도 되는가 — TIME 을 내기 전에 본다 (S6 spec §3, v2 §5.2 clockValid).

모뎀Pi(Raspberry Pi)는 RTC 가 없다. 전원이 나갔다 켜지면 fake-hwclock 이 **마지막으로 저장한 옛 시각**을
복원하는데, 이 값은 "2023 년 이후" 임계값을 넉넉히 넘는다. 임계값만 보면 밤새 꺼져 있던 모뎀Pi 가 아침에
켜지자마자 틀린 시각을 모든 ESP노드에 방송해 노드 시계를 망가뜨린다. 그래서 systemd-timesyncd 가 있으면
그 동기 표시(`/run/systemd/timesync/synchronized`, 부팅마다 지워지는 tmpfs)가 생긴 뒤에만 믿는다.
"""

from __future__ import annotations

import os

CLOCK_VALID_AFTER = 1_700_000_000  # v2 §5.2 clockValid 와 같은 기준
TIMESYNC_DIR = "/run/systemd/timesync"


def clock_trusted(now: float, *, timesync_dir: str | None = None) -> bool:
    """임계값을 넘고, timesyncd 가 있으면 이번 부팅에서 동기를 마쳤을 때 True.

    timesyncd 디렉터리 자체가 없으면(개발 PC·CI·chrony 를 쓰는 Pi) 임계값만 본다 — 그 경우의
    보장은 운영 쪽(S11 Pi 이식)에서 timesyncd 를 쓰는 것으로 맞춘다.
    """
    if now <= CLOCK_VALID_AFTER:
        return False
    d = timesync_dir or TIMESYNC_DIR
    if os.path.isdir(d):
        return os.path.exists(os.path.join(d, "synchronized"))
    return True
