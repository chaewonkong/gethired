# spec - docker로 서비스를 띄워 사용
> **보류 (2026-10-17)**. 선행 0008은 완료. 착수 전에 아래 결정이 필요해 뒤로 미룸
> - CLI 로그인 전달 방식 (컨테이너 안 로그인 + named volume vs 호스트 `~/.claude`·`~/.codex` 마운트)
> - 런타임 이미지 (python + node, Claude Code 자동 업데이트 off)
> - codex가 Linux 컨테이너의 seccomp 아래서 `-s read-only`로 도는지 PoC
> - 볼륨 형태 (이력서·DB는 bind mount, CLI 홈은 named volume), 진입 명령 (`docker compose up`)
> - 작업 제약: Docker 소켓은 sandbox 밖에서만, Docker Hub 도메인 allowlist 필요

## 목표
- docker로 서비스를 쉽게 띄울 수 있다
- docker 외에 python, npm 등의 추가적인 설치가 불필요하다

## 구현
- dockerize
- volume을 mapping해서 이력서, sqlite db 저장