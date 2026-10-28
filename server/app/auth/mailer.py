"""메일 발송 — Gmail SMTP 또는 HTTP 발송 API(stdlib) + 템플릿 3개 (S4a §6). 호출은 BackgroundTasks 에서 — 실패는 로그만.

`MAIL_BACKEND=http`: `MAIL_API_URL` 에 `{"to","subject","text"}` JSON 을 POST 한다(`Authorization: Bearer
MAIL_API_KEY`, 요청마다 새 `Idempotency-Key`). 재시도는 하지 않는다 — 실패하면 사용자가 다시 요청한다.
"""

from __future__ import annotations

import json
import logging
import smtplib
import urllib.error
import urllib.request
import uuid
from email.message import EmailMessage

from app.auth import ratelimit
from app.settings import Settings

log = logging.getLogger(__name__)


# 종류별 시간당 상한 — Gmail 일일 한도(500) 보호 + 가짜 가입이 재설정·승인 메일을 굶기지 못하게 (S4a §3.4)
MAIL_PER_HOUR = {"verify": 60, "reset": 30, "decision": 200}
# 종류별 일일 상한 — 합 450 < Gmail 500/일 (PR #42 🟡). 시간 상한만으론 하루 수천 통
MAIL_PER_DAY = {"verify": 250, "reset": 100, "decision": 100}


def send(settings: Settings, to: str, subject: str, body: str, kind: str) -> None:
    day = (f"mail-day:{kind}", MAIL_PER_DAY[kind], 86400.0)
    if ratelimit.saturated(*day) or not ratelimit.check(
        f"mail:{kind}", limit=MAIL_PER_HOUR[kind], window_s=3600.0
    ):
        log.warning("메일 상한 초과(%s) — 발송 생략 to=%s", kind, to)
        return
    ratelimit.check(*day)  # 실제로 보낼 때만 하루 카운트를 쓴다
    if settings.mail_backend == "console":
        print(f"[mail] to={to} subject={subject}\n{body}")
        return
    if settings.mail_backend == "http":
        _send_http(settings, to, subject, body)
        return
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = settings.mail_from, to, subject
    msg.set_content(body)
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=10) as smtp:
            smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(msg)
    except (smtplib.SMTPException, OSError):
        log.exception(
            "메일 발송 실패 to=%s subject=%s", to, subject
        )  # 토큰은 body 에만 — 로그에 안 남김


def _send_http(settings: Settings, to: str, subject: str, body: str) -> None:
    req = urllib.request.Request(
        settings.mail_api_url,
        data=json.dumps({"to": to, "subject": subject, "text": body}).encode(),
        method="POST",
        headers={
            "Authorization": f"Bearer {settings.mail_api_key}",
            "Content-Type": "application/json",
            "Idempotency-Key": uuid.uuid4().hex,
            # 기본 "Python-urllib/x" 는 Cloudflare 가 봇으로 막는다(403, error code 1010 — 2026-10-28 실측)
            "User-Agent": "woo-esc-server/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            r.read()
    except (urllib.error.URLError, OSError, ValueError) as e:
        # 토큰은 body 에, API 키는 헤더에만 — 둘 다 로그에 남기지 않는다
        log.error("메일 발송 실패 to=%s subject=%s (%s)", to, subject, type(e).__name__)


def verify_mail(settings: Settings, token: str) -> tuple[str, str]:
    return (
        "[강의실 게시] 이메일 확인",
        f"아래 링크를 5분 안에 열어 주세요. 연 뒤 30분 안에 이름·학번·비밀번호를 입력하면 가입 신청이 끝납니다.\n\n{settings.student_web_url}/verify#token={token}\n",
    )


def reset_mail(settings: Settings, token: str) -> tuple[str, str]:
    return (
        "[강의실 게시] 비밀번호 재설정",
        f"아래 링크를 5분 안에 열어 새 비밀번호를 설정하세요.\n\n{settings.student_web_url}/reset#token={token}\n",
    )


def decision_mail(approved: bool, reason: str | None) -> tuple[str, str]:
    if approved:
        return "[강의실 게시] 가입 승인", "가입이 승인되었습니다. 이제 로그인할 수 있습니다.\n"
    return "[강의실 게시] 가입 거절", f"가입이 거절되었습니다.\n사유: {reason or '(없음)'}\n"
