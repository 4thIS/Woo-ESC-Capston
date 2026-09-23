"""운영 CLI (S4a §4.4). uv run --env-file .env python -m app.cli create-school … / update-school … / create-admin …
DB 는 SERVER_DB. 실행 전에 alembic upgrade head 로 스키마를 맞춘다. 비밀번호는 argv 에 받지 않는다."""

from __future__ import annotations

import argparse
import getpass
import re
import sys
from pathlib import Path

from alembic.config import Config

from alembic import command
from app.auth import password, tokens
from app.auth.models import User
from app.db import make_engine, make_session_factory
from app.domain.models import School
from app.schemas import EMAIL_RE
from app.settings import Settings

SERVER = Path(__file__).resolve().parents[1]
PW_MIN = 8


def _session():
    st = Settings()
    cfg = Config(str(SERVER / "alembic.ini"))
    cfg.set_main_option("script_location", str(SERVER / "alembic"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{st.db_path}")
    command.upgrade(cfg, "head")
    return make_session_factory(make_engine(st.db_path))


def _domain(v: str) -> str:
    """`' WSU.ac.kr '` → `wsu.ac.kr`. 가입 판별은 소문자 정규화된 이메일의 도메인과 정확히 비교한다."""
    d = v.strip().lower()
    if not re.fullmatch(r"[a-z0-9-]+(\.[a-z0-9-]+)+", d):
        raise argparse.ArgumentTypeError(f"도메인 형식이 아닙니다: {v!r}")
    return d


def _read_password() -> str:
    pw = getpass.getpass("비밀번호: ") if sys.stdin.isatty() else sys.stdin.readline().rstrip("\n")
    if len(pw) < PW_MIN:
        sys.exit(f"비밀번호는 {PW_MIN}자 이상")
    return pw


def create_school(a: argparse.Namespace) -> None:
    with _session()() as s, s.begin():
        sch = School(name=a.name, net_id=a.net_id, email_domain=a.email_domain)
        s.add(sch)
        s.flush()
        print(
            f"school id={sch.id} name={sch.name} net_id={sch.net_id} email_domain={sch.email_domain}"
        )


def update_school(a: argparse.Namespace) -> None:
    with _session()() as s, s.begin():
        sch = s.get(School, a.id)
        if sch is None:
            sys.exit(f"school {a.id} 없음")
        for k in ("name", "net_id", "email_domain"):
            if getattr(a, k) is not None:
                setattr(sch, k, getattr(a, k))
        s.flush()  # 제약 위반을 성공 출력 전에
        print(
            f"school id={sch.id} name={sch.name} net_id={sch.net_id} email_domain={sch.email_domain}"
        )


def create_admin(a: argparse.Namespace) -> None:
    email = a.email.strip().lower()
    if not EMAIL_RE.fullmatch(email):
        sys.exit("이메일 형식이 아닙니다")
    pw = _read_password()
    with _session()() as s, s.begin():
        if s.get(School, a.school_id) is None:
            sys.exit(f"school {a.school_id} 없음")
        if s.get(User, email) is not None:
            sys.exit(f"{email} 은 이미 있음")
        s.add(
            User(
                email=email,
                school_id=a.school_id,
                role="admin",
                status="active",
                name=a.name,
                student_no=None,
                pw_hash=password.hash(pw),
            )
        )
    print(f"admin {email} (school {a.school_id})")


def set_user(a: argparse.Namespace) -> None:
    """관리자 계정 복구·정지 — 웹의 disable 은 관리자에게 400 이고, 관리자 메일함이 없으면 forgot 도 못 쓴다.
    바뀌면 token_version += 1 (기존 JWT 무효)."""
    email = a.email.strip().lower()
    pw = _read_password() if a.password else None
    with _session()() as s, s.begin():
        u = s.get(User, email)
        if u is None:
            sys.exit(f"{email} 없음")
        if a.status:
            u.status = a.status
        if pw:
            u.pw_hash = password.hash(pw)
            tokens.invalidate_all(s, email)  # 남아 있던 reset 링크로 되돌리지 못하게 (PR #42 🟡)
        u.token_version += 1
    print(f"user {email} status={a.status or '(유지)'} password={'변경' if pw else '(유지)'}")


def assign_modem(a: argparse.Namespace) -> None:
    """school_id 가 NULL 로 남은 모뎀(마이그레이션 전 미배정·등록 직후 실패)을 학교에 붙인다 — 웹으로는 되돌릴 길이 없다."""
    from app.lora_service.models import Modem

    with _session()() as s, s.begin():
        m = s.get(Modem, a.modem_id)
        if m is None or s.get(School, a.school_id) is None:
            sys.exit("모뎀 또는 학교 없음")
        m.school_id = a.school_id
    print(f"modem {a.modem_id} → school {a.school_id}")


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="app.cli")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create-school")
    c.add_argument("--name", required=True)
    c.add_argument("--net-id", type=int, required=True)
    c.add_argument("--email-domain", default=None, type=_domain)
    c.set_defaults(fn=create_school)
    u = sub.add_parser("update-school")
    u.add_argument("--id", type=int, required=True)
    u.add_argument("--name")
    u.add_argument("--net-id", type=int)
    u.add_argument("--email-domain", type=_domain)
    u.set_defaults(fn=update_school)
    a = sub.add_parser("create-admin")
    a.add_argument("--school-id", type=int, required=True)
    a.add_argument("--email", required=True)
    a.add_argument("--name", required=True)
    a.set_defaults(fn=create_admin)
    su = sub.add_parser("set-user")
    su.add_argument("--email", required=True)
    su.add_argument("--status", choices=("active", "disabled"))
    su.add_argument("--password", action="store_true", help="새 비밀번호를 getpass 로 받는다")
    su.set_defaults(fn=set_user)
    am = sub.add_parser("assign-modem")
    am.add_argument("--modem-id", required=True)
    am.add_argument("--school-id", type=int, required=True)
    am.set_defaults(fn=assign_modem)
    args = p.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
