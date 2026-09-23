"""S4a §4.1 공개 흐름 + §4.2 관리자 회원 관리(T6). 상태·존재 여부가 응답으로 새지 않게 202/401 통일.
메일은 항상 s.commit() 뒤에 BackgroundTasks 로 — BackgroundTasks 는 get_db 커밋보다 먼저 돈다(§3.4)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app import schemas as S
from app.auth import mailer, password, ratelimit, tokens
from app.auth.deps import AdminUser, CurrentUser
from app.auth.models import HOLDS_STUDENT_NO, User
from app.db import utcnow
from app.deps import _DB
from app.domain.models import School

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth")
admin = APIRouter(prefix="/api/admin")

LINK_INVALID = "링크가 만료되었거나 잘못되었습니다"
SIGNUP_PER_DOMAIN_HOUR = 60  # 가짜 주소 대량 신청이 verify 메일 상한을 다 먹지 못하게 (S4a §3.4)
MAIL_PER_ADDRESS_HOUR = (
    3  # 주소 하나로 도메인·종류별 상한을 고갈시키지 못하게 — 초과는 202 + 발송 생략
)
# IP 당 — 전역 키는 누구나 전원 로그인을 잠근다 (PR #42 🔴3). 전체 부하는 password.SCRYPT_WAIT_S(503)가 맡는다
LOGIN_PER_IP_MINUTE = 30


def _mail_allowed(email: str) -> bool:
    return ratelimit.check(f"mail-to:{email}", limit=MAIL_PER_ADDRESS_HOUR, window_s=3600.0)


def _limit(key: str, limit: int = 5, window_s: float = 60.0) -> None:
    if not ratelimit.check(key, limit=limit, window_s=window_s):
        raise HTTPException(429, "잠시 후 다시 시도하세요")


def _school_by_domain(s: Session, email: str) -> School | None:
    return s.scalar(select(School).where(School.email_domain == email.split("@", 1)[1]))


def send_after_commit(
    bg: BackgroundTasks, s: Session, settings, to: str, subject: str, body: str, kind: str
) -> None:
    """커밋을 먼저 끝내고 발송을 예약한다 — 쓰기 락을 쥔 채 SMTP 를 돌리지 않게 (S4a §3.4)."""
    s.commit()
    bg.add_task(mailer.send, settings, to, subject, body, kind)


@router.post("/signup", status_code=202)
def signup(body: S.EmailIn, request: Request, bg: BackgroundTasks, s: Session = _DB):
    _limit(f"signup:{body.email}")
    school = _school_by_domain(s, body.email)
    if school is None:
        raise HTTPException(400, "학교 웹메일이 아닙니다")
    existing = s.get(User, body.email)
    if (
        (existing is None or existing.status == "rejected")
        and tokens.can_send(s, body.email, "verify")
        and _mail_allowed(body.email)
    ):
        # 도메인 상한은 실제로 보낼 때만 센다 — 60 s 재신청·기존 회원은 세지 않는다
        _limit(f"signup-domain:{school.id}", limit=SIGNUP_PER_DOMAIN_HOUR, window_s=3600.0)
        st = request.app.state.settings
        subj, msg = mailer.verify_mail(st, tokens.issue(s, body.email, "verify"))
        send_after_commit(bg, s, st, body.email, subj, msg, "verify")
    return {"status": "sent"}  # 이미 가입·60 s 이내도 같은 응답 — 존재 여부 숨김


@router.post("/verify/open")
def verify_open(body: S.TokenIn, s: Session = _DB):
    """링크 페이지가 처음 부른다 — 소비하지 않고 확인 + 입력 시간 30분 (S4a §4.1). 메일 스캐너 GET 에 안전."""
    email = tokens.open_verify(s, body.token)
    if email is None:
        raise HTTPException(400, LINK_INVALID)
    return {"email": email}


@router.post("/verify")
def verify(body: S.VerifyIn, request: Request):
    """읽기 확인 → (세션 닫고) scrypt → 짧은 쓰기 트랜잭션. scrypt 동안 커넥션·쓰기 락을 쥐지 않는다 (PR #42 🟡)."""
    with request.app.state.Session() as s:
        email = tokens.peek(s, body.token, "verify")
        existing = s.get(User, email) if email else None
        if email is None or (existing is not None and existing.status != "rejected"):
            raise HTTPException(400, LINK_INVALID)
        school = _school_by_domain(s, email)
        if school is None:  # 발급 뒤 학교 도메인이 바뀐 경우
            raise HTTPException(400, LINK_INVALID)
        # 409 는 토큰을 소비하지 않는다(학번 오타를 고쳐 재제출) — 대신 학번 존재 조회 남용을 막는다
        _limit(f"verify:{email}")
        taken = s.scalar(
            select(User.email).where(
                User.school_id == school.id,
                User.student_no == body.student_no,
                User.email != email,
                text(HOLDS_STUDENT_NO),
            )
        )
        if taken:
            raise HTTPException(409, "이미 등록된 학번입니다")
        school_id = school.id
    pw_hash = password.hash(body.password)
    with request.app.state.Session() as s, s.begin():
        if tokens.consume(s, body.token, "verify") is None:  # 그 사이 다른 요청이 썼다
            raise HTTPException(400, LINK_INVALID)
        existing = s.get(User, email)
        if existing is not None:
            if existing.status != "rejected":
                raise HTTPException(400, LINK_INVALID)
            s.delete(existing)  # 거절 뒤 재신청 — 거절 기록을 새 신청으로 교체
            s.flush()
        s.add(
            User(
                email=email,
                school_id=school_id,
                role="student",
                status="pending_approval",
                name=body.name,
                student_no=body.student_no,
                pw_hash=pw_hash,
            )
        )
        # 재발급으로 남아 있던 다른 verify 링크 정리 (issue 는 죽이지 않는다)
        tokens.invalidate_all(s, email)
    return {"status": "pending_approval"}  # 커밋은 위 with 가 응답 전에 끝냈다


@router.post("/login", response_model=S.LoginOut)
def login(body: S.LoginIn, request: Request):
    _limit(f"login:{body.email}")
    ip = request.client.host if request.client else "unknown"
    _limit(f"login-ip:{ip}", limit=LOGIN_PER_IP_MINUTE)
    # 짧은 세션으로 읽고 닫은 뒤 scrypt — 쥔 채 줄 서면 풀이 말라 허브까지 멈춘다 (PR #42 🔴2)
    # ponytail: 분리된(detached) User 를 값 묶음으로 쓴다 — 컬럼은 get 이 모두 읽어 둔다
    with request.app.state.Session() as s:
        user = s.get(User, body.email)
    if user is None:
        password.dummy_verify(body.password)  # 응답 시간으로 가입 여부가 새지 않게
        log.info("login 실패 %s", body.email)
        raise HTTPException(401, "이메일 또는 비밀번호가 틀립니다")
    if not password.verify(body.password, user.pw_hash):
        log.info("login 실패 %s", body.email)
        raise HTTPException(401, "이메일 또는 비밀번호가 틀립니다")
    if user.status == "pending_approval":
        raise HTTPException(403, "승인 대기 중")
    if user.status != "active":
        raise HTTPException(401, "이메일 또는 비밀번호가 틀립니다")
    return {
        "token": tokens.jwt_encode(request.app.state.settings, user),
        "role": user.role,
        "school_id": user.school_id,
        "name": user.name,
    }


@router.post("/forgot", status_code=202)
def forgot(body: S.EmailIn, request: Request, bg: BackgroundTasks, s: Session = _DB):
    _limit(f"forgot:{body.email}")
    user = s.get(User, body.email)
    if (
        user is not None
        and user.status == "active"
        and tokens.can_send(s, user.email, "reset")
        and _mail_allowed(user.email)
    ):
        st = request.app.state.settings
        subj, msg = mailer.reset_mail(st, tokens.issue(s, user.email, "reset"))
        send_after_commit(bg, s, st, user.email, subj, msg, "reset")
    return {"status": "sent"}


@router.post("/reset")
def reset(body: S.ResetIn, request: Request):
    """verify 와 같은 순서 — 읽기 확인 → scrypt → 원자적 소비·갱신 (PR #42 🟡)."""
    with request.app.state.Session() as s:
        email = tokens.peek(s, body.token, "reset")
        user = s.get(User, email) if email else None
        if user is None or user.status != "active":
            raise HTTPException(400, LINK_INVALID)
    pw_hash = password.hash(body.password)
    with request.app.state.Session() as s, s.begin():
        user = s.get(User, email) if tokens.consume(s, body.token, "reset") else None
        if user is None or user.status != "active":
            raise HTTPException(400, LINK_INVALID)
        user.pw_hash = pw_hash
        user.token_version += 1  # 재설정 전에 발급된 JWT 무효 (S4a §2.3)
        tokens.invalidate_all(s, user.email)
    return {"status": "ok"}


@router.get("/me", response_model=S.UserOut)
def me(user: User = CurrentUser):
    return user


# ---- §4.2 관리자 회원 관리 (자기 학교만) ----


def _scoped_user(s: Session, email: str, admin_user: User) -> User:
    u = s.get(User, email.strip().lower())
    if u is None or u.school_id != admin_user.school_id:
        raise HTTPException(404, "사용자 없음")  # 타 학교는 존재 자체를 숨긴다 (S4a §3.3)
    return u


def _transition(u: User, from_: str, to: str) -> None:
    if u.status != from_:
        raise HTTPException(409, f"{u.status} 상태에서는 불가")
    u.status = to


@admin.get("/users", response_model=list[S.UserOut])
def list_users(status: str | None = None, admin_user: User = AdminUser, s: Session = _DB):
    q = select(User).where(User.school_id == admin_user.school_id).order_by(User.created_at)
    if status is not None:
        q = q.where(User.status == status)
    return s.scalars(q).all()


@admin.post("/users/{email}/approve", response_model=S.UserOut)
def approve(
    email: str,
    request: Request,
    bg: BackgroundTasks,
    admin_user: User = AdminUser,
    s: Session = _DB,
):
    u = _scoped_user(s, email, admin_user)
    _transition(u, "pending_approval", "active")
    u.approved_at, u.approved_by = utcnow(), admin_user.email
    out = S.UserOut.model_validate(u)  # 커밋 뒤에도 응답을 만들 수 있게 먼저 스냅샷
    send_after_commit(
        bg, s, request.app.state.settings, u.email, *mailer.decision_mail(True, None), "decision"
    )
    return out


@admin.post("/users/{email}/reject", response_model=S.UserOut)
def reject(
    email: str,
    body: S.RejectIn,
    request: Request,
    bg: BackgroundTasks,
    admin_user: User = AdminUser,
    s: Session = _DB,
):
    u = _scoped_user(s, email, admin_user)
    _transition(u, "pending_approval", "rejected")
    u.approved_at, u.approved_by, u.reject_reason = utcnow(), admin_user.email, body.reason
    out = S.UserOut.model_validate(u)
    send_after_commit(
        bg,
        s,
        request.app.state.settings,
        u.email,
        *mailer.decision_mail(False, body.reason),
        "decision",
    )
    return out


@admin.post("/users/{email}/disable", response_model=S.UserOut)
def disable(email: str, admin_user: User = AdminUser, s: Session = _DB):
    u = _scoped_user(s, email, admin_user)
    if u.role == "admin":
        raise HTTPException(400, "관리자 계정은 CLI 로")
    _transition(u, "active", "disabled")
    u.token_version += 1
    s.flush()  # 응답 전에 쓰기 — 커밋 실패를 성공으로 보이지 않게 (Global)
    return u


@admin.post("/users/{email}/enable", response_model=S.UserOut)
def enable(email: str, admin_user: User = AdminUser, s: Session = _DB):
    u = _scoped_user(s, email, admin_user)
    _transition(u, "disabled", "active")
    u.token_version += 1  # disabled 동안 탈취된 토큰도 되살아나지 않게
    s.flush()
    return u
