# 메인Pi 자동 배포 컨테이너 — docker CLI(compose 플러그인 포함) + git. 호스트의 docker.sock 으로 compose 를 다룬다.
# 빌드·실행: deploy/autodeploy/README.md
FROM docker:29.0-cli
RUN apk add --no-cache git tzdata
ENV TZ=Asia/Seoul
COPY autodeploy.sh /usr/local/bin/autodeploy
RUN chmod +x /usr/local/bin/autodeploy
ENTRYPOINT ["/usr/local/bin/autodeploy"]
