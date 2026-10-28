# 메인Pi 자동 배포 (autodeploy)

`main` 이 바뀌면 메인Pi 가 스스로 새 버전을 받아 다시 배포한다. 2분마다 GitHub 를 확인하는 **끌어오기 방식**이라 포트·웹훅·GitHub 러너가 필요 없다(공개 리포라 자격 증명도 필요 없다).

| 단계 | 동작 |
|---|---|
| 확인 | `git fetch` → `origin/main` 이 지금 배포본과 같으면 아무것도 안 함 |
| 받기 | `main` 을 **fast-forward 로만** 당긴다. 메인Pi 리포에 손으로 고친 파일이 있거나 갈라져 있으면 건너뛰고 로그만 남긴다 |
| 배포 | `server/`·`web/`·`lora_proto/`·`compose.yaml`·`.dockerignore` 가 바뀌었으면 `docker compose build` → (마이그레이션이 들었으면 DB 를 떠 두고) `up -d` → server·web 가 `healthy` 가 될 때까지(최대 5분) 기다린다. 문서만 바뀌면 리포만 갱신 |
| 실패 | 마지막 정상 배포 커밋으로 되돌려 다시 빌드한다 — 운영은 정상본으로 계속 돈다. 마이그레이션이 든 배포였으면 DB 도 떠 둔 것으로 되돌린다. 실패한 커밋은 다시 시도하지 않고, **새 커밋이 오면** 다시 시도한다 |

DB 마이그레이션은 서버 컨테이너가 시작할 때 자동으로 돈다(`server/Dockerfile`). 모뎀Pi 는 서버가 재시작되면 몇 초 뒤 스스로 재접속한다.

**마이그레이션과 되돌리기** — 새 서버는 켜질 때 `alembic upgrade head` 부터 돌린다. 그 뒤에 실패하면(예: 새 필수 env 누락) DB 만 새 리비전으로 남아, 되돌린 옛 서버가 모르는 리비전이라 켜지지 못한다. 그래서 `server/alembic/` 이 바뀐 배포는:

- 빌드가 끝나고 컨테이너를 바꾸기 **직전에** DB 를 `SERVER_DB` 옆 `.predeploy` 로 떠 둔다(SQLite 백업 API — 돌고 있는 서버와 함께 읽어도 일관된 사본). 떠 두지 못하면 그 커밋은 배포하지 않는다.
- 실패해서 되돌릴 때는 서버를 멈추고 `.predeploy` 를 DB 자리에 복원한 뒤 옛 버전을 띄운다. 떠 둔 뒤 되돌리기까지(새 서버가 뜨지 못한 동안) 들어온 쓰기는 잃는다.

## 설치 (메인Pi, 1회)

`admin` 은 `docker` 그룹이라 `sudo` 가 필요 없다. 리포는 **호스트와 같은 경로**로 마운트한다(compose 가 그 경로로 빌드 컨텍스트·`server/.env` 를 찾는다).

```bash
cd ~/Woo-ESC-Capston
docker build -t woo-esc/autodeploy:local deploy/autodeploy
mkdir -p ~/.autodeploy
docker run -d --name esc-autodeploy --restart unless-stopped \
  --user "$(id -u):$(id -g)" --group-add "$(getent group docker | cut -d: -f3)" \
  -e HOME=/tmp -e REPO="$HOME/Woo-ESC-Capston" \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v "$HOME/Woo-ESC-Capston:$HOME/Woo-ESC-Capston" \
  -v "$HOME/.autodeploy:/state" \
  woo-esc/autodeploy:local
```

`--restart unless-stopped` 라 재부팅 뒤에도 Docker 가 다시 띄운다. 설정은 환경 변수로: `BRANCH`(기본 `main`), `INTERVAL`(초, 기본 120), `HEALTH_TIMEOUT`(초, 기본 300).

## 보기 · 멈추기

```bash
docker logs -f esc-autodeploy          # 무엇을 언제 배포했는지
tail -f ~/.autodeploy/build.log        # 빌드 출력
cat ~/.autodeploy/good                 # 마지막 정상 배포 커밋
cat ~/.autodeploy/failed               # 실패해서 건너뛰는 커밋(있으면)
docker stop esc-autodeploy             # 잠시 멈춤(손으로 작업할 때) — 다시: docker start esc-autodeploy
```

이 스크립트 자체를 고쳤으면 이미지를 다시 만들고 컨테이너를 바꿔 끼운다(`docker rm -f esc-autodeploy` 후 위 두 명령). 스크립트는 이미지에 복사돼 있어서 `main` 이 바뀌어도 저절로 바뀌지 않는다 — 배포 도구가 배포 도중에 바뀌지 않게 하기 위함이다.

## 주의

- 메인Pi 의 `~/Woo-ESC-Capston` 은 **배포 전용**이다. 거기서 파일을 고치면 자동 배포가 멈춘다(로그에 남는다). 고칠 것은 PR 로.
- `server/.env` 는 git 이 추적하지 않아 자동 배포와 무관하다. 새 필수 env 가 생긴 버전은 배포가 실패하고 되돌려진다 — `.env` 를 채운 뒤 `rm ~/.autodeploy/failed` 하면 다음 확인에서 다시 시도한다.
- `docker.sock` 을 가진 컨테이너는 호스트 root 와 같은 권한이다. 이 이미지는 리포의 스크립트만 실행한다.
