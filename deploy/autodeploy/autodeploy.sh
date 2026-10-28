#!/bin/sh
# 메인Pi 자동 배포 — origin/main 이 바뀌면 메인Pi 리포를 앞으로 당기고 compose 를 다시 빌드한다.
#
# 끌어오기(pull) 방식이다: 메인Pi 가 INTERVAL 초마다 GitHub 를 확인한다. 들어오는 포트·웹훅·러너가 필요 없고
# (공개 리포라 fetch 에 자격 증명도 필요 없다), 메인Pi 가 꺼져 있었으면 켜진 뒤 다음 확인에서 따라잡는다.
#
# 한 번의 배포:
#   1. git fetch → origin/main 이 지금 배포본과 같으면 끝
#   2. 직전에 실패한 커밋이면 건너뜀(같은 실패를 2분마다 반복하지 않는다 — 새 커밋이 오면 다시 시도)
#   3. 리포에 손으로 고친 파일이 있으면 건너뜀(덮어쓰지 않는다)
#   4. main 을 fast-forward 로만 당김(되감기·강제 리셋 없음)
#   5. 배포에 영향 있는 경로(server/·web/·lora_proto/·compose.yaml·.dockerignore)가 바뀌었으면
#      docker compose build → (마이그레이션이 들었으면 DB 를 떠 두고) up -d → server·web 가 healthy 가 될 때까지 기다림
#   6. 실패하면 마지막 정상 배포 커밋으로 되돌려(분리 HEAD) 다시 빌드 — 운영은 정상본으로 계속 돈다.
#      마이그레이션이 든 배포였으면 DB 도 떠 둔 것으로 되돌린다
set -u

REPO=${REPO:?REPO 필요 — 메인Pi 리포 경로(호스트와 같은 경로로 마운트)}
BRANCH=${BRANCH:-main}
INTERVAL=${INTERVAL:-120}
HEALTH_TIMEOUT=${HEALTH_TIMEOUT:-300}
STATE=${STATE:-/state}
DEPLOY_PATHS="server/ web/ lora_proto/ compose.yaml .dockerignore"
MIGRATIONS=server/alembic/

mkdir -p "$STATE"
log() { echo "$(date '+%F %T') $*" | tee -a "$STATE/autodeploy.log"; }
g() { git -C "$REPO" "$@"; }
dc() { docker compose -f "$REPO/compose.yaml" "$@"; }

healthy() {  # server·web 둘 다 healthy 가 될 때까지 HEALTH_TIMEOUT 초 기다린다
  end=$(( $(date +%s) + HEALTH_TIMEOUT ))
  while [ "$(date +%s)" -lt "$end" ]; do
    s=$(docker inspect -f '{{.State.Health.Status}}' esc-server 2>/dev/null)
    w=$(docker inspect -f '{{.State.Health.Status}}' esc-web 2>/dev/null)
    [ "$s" = healthy ] && [ "$w" = healthy ] && return 0
    sleep 5
  done
  log "  healthy 대기 시간 초과 (server=$s web=$w)"
  return 1
}

# 서버는 켜질 때 alembic upgrade head 를 먼저 돌린다(server/Dockerfile). 마이그레이션이 든 버전이 그 뒤에 실패하면
# DB 만 새 리비전으로 남아, 되돌린 옛 서버가 모르는 리비전이라 켜지지 못한다. 그래서 마이그레이션이 든 배포는
# 컨테이너를 바꾸기 직전(빌드 뒤 — 빌드 동안의 쓰기도 담긴다)에 DB 를 떠 두고, 되돌릴 때 서버를 멈추고 복원한다.
# SQLite 백업 API 라 돌고 있는 서버와 함께 읽어도 일관된 사본이다. 경로는 compose 의 SERVER_DB
backup_db() {
  dc run --rm --no-deps -T --entrypoint python server -c '
import os, sqlite3
db = os.environ["SERVER_DB"]
src, dst = sqlite3.connect(db), sqlite3.connect(db + ".predeploy")
src.backup(dst)
dst.close()
src.close()'
}
restore_db() {  # 서버를 멈춘 뒤에만 — 남은 -wal·-shm 은 새 리비전 것이라 지운다
  dc run --rm --no-deps -T --entrypoint sh server -c \
    'rm -f "$SERVER_DB-wal" "$SERVER_DB-shm" && cp "$SERVER_DB.predeploy" "$SERVER_DB"'
}

touches_deploy() {  # $1..$2 사이에 배포 경로가 바뀌었나
  for p in $DEPLOY_PATHS; do
    [ -n "$(g diff --name-only "$1" "$2" -- "$p")" ] && return 0
  done
  return 1
}

deploy_once() {
  g fetch -q origin "$BRANCH" || { log "fetch 실패 — 네트워크 확인, 다음에 다시"; return; }
  remote=$(g rev-parse "origin/$BRANCH")
  cur=$(g rev-parse HEAD)
  [ "$remote" = "$cur" ] && return
  [ "$remote" = "$(cat "$STATE/failed" 2>/dev/null)" ] && return
  if ! g diff --quiet || ! g diff --cached --quiet; then
    log "리포에 손으로 고친 파일이 있다 — 배포 건너뜀 ($(g status --short | head -3 | tr '\n' ' '))"
    return
  fi
  g checkout -q "$BRANCH" 2>/dev/null || { log "브랜치 $BRANCH 로 전환 실패"; return; }
  base=$(cat "$STATE/good" 2>/dev/null || g rev-parse HEAD)  # 롤백할 지점 = 마지막으로 정상 배포된 커밋
  if ! g merge -q --ff-only "origin/$BRANCH"; then
    log "fast-forward 불가(메인Pi 의 $BRANCH 가 갈라짐) — 손으로 확인 필요"
    return
  fi
  short=$(g rev-parse --short HEAD)
  log "새 버전 $short: $(g log -1 --format=%s)"
  if ! touches_deploy "$base" HEAD; then
    log "  배포 대상 경로 변경 없음 — 리포만 갱신"
    rm -f "$STATE/failed"
    g rev-parse HEAD >"$STATE/good"
    return
  fi
  t0=$(date +%s)
  mig=
  [ -n "$(g diff --name-only "$base" HEAD -- "$MIGRATIONS")" ] && mig=1
  swapped=
  if dc build >>"$STATE/build.log" 2>&1; then
    if [ -n "$mig" ] && ! backup_db >>"$STATE/build.log" 2>&1; then
      log "  DB 를 떠 두지 못했다 — 마이그레이션이 든 $short 는 배포하지 않는다 (build.log 확인)"
      echo "$remote" >"$STATE/failed"
      g checkout -q --detach "$base"
      dc build >>"$STATE/build.log" 2>&1  # 이미지 태그를 지금 도는 버전으로 되돌린다 — 컨테이너는 바꾸지 않았다
      return
    fi
    swapped=1
    if dc up -d >>"$STATE/build.log" 2>&1 && healthy; then
      log "  배포 완료 $short ($(( $(date +%s) - t0 )) s)"
      rm -f "$STATE/failed"
      g rev-parse HEAD >"$STATE/good"
      return
    fi
  fi
  log "  배포 실패 $short — 직전 $(g rev-parse --short "$base") 로 되돌린다 (build.log 확인)"
  echo "$remote" >"$STATE/failed"
  g checkout -q --detach "$base"
  if [ -n "$swapped" ] && [ -n "$mig" ]; then
    # 새 서버가 켜지며 마이그레이션을 이미 돌렸을 수 있다 — 옛 서버는 모르는 리비전이라 켜지지 못하니 DB 도 되돌린다
    if dc build >>"$STATE/build.log" 2>&1 && dc stop server >>"$STATE/build.log" 2>&1 &&
      restore_db >>"$STATE/build.log" 2>&1; then
      log "  DB 를 배포 직전에 떠 둔 것으로 되돌렸다 — 그 뒤 쓰기는 잃는다"
    else
      log "  DB 되돌리기 실패 — 옛 서버가 켜지지 못할 수 있다 (build.log 확인)"
    fi
  fi
  if dc up -d --build >>"$STATE/build.log" 2>&1 && healthy; then
    log "  되돌리기 완료 — $(g rev-parse --short HEAD) 로 운영 중. 새 커밋이 오면 다시 시도"
  else
    log "  되돌리기도 실패 — 손으로 확인 필요 (docker compose ps / logs)"
  fi
}

[ -s "$STATE/good" ] || g rev-parse HEAD >"$STATE/good"  # 처음 켤 때 지금 돌고 있는 것을 정상본으로
log "자동 배포 시작: $REPO ($BRANCH, ${INTERVAL}s 마다), 정상본 $(cut -c1-7 "$STATE/good")"
while :; do
  deploy_once
  sleep "$INTERVAL"
done
