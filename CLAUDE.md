# CLAUDE.md

## Project Overview

네이버 메일 전용 MCP 서버 (Python, 공식 `mcp` SDK v2의 `MCPServer`).
기존 mcp-email-server가 네이버 IMAP과 호환되지 않아 커스텀 구현.

## Tools (9개)

`get_profile`, `search_emails`, `read_email`, `read_thread`, `list_folders`, `create_draft`, `list_drafts`, `send_email`, `download_attachment`

## Security

아래 보호와 회귀 테스트를 유지할 것. 실계정 검증과 모의 검증을 구분한다.
- IMAP/SMTP에 검증용 SSL context 전달
- 검색 입력의 제어문자 거부, ASCII quoting과 UTF-8 literal 사용
- 메일 크기 사전 검사와 bounded BODY.PEEK, 첨부파일·응답 크기 제한
- 발송 도구의 `Resolve`/`Elicit` 확인: 구·신 프로토콜 모두 거절·취소·미지원이면 발송 금지
- 확인 결과는 SDK resolver만 주입하며 모델 입력으로 받지 않는다. 최신 프로토콜에서 직접 `ctx.elicit()`을 호출하지 않는다.
- 개인용 stdio/Tunnel 구성만 제공. 다중 사용자 인증 또는 공개 HTTP 서버는 구현하지 않음
- 암호화 설정은 `.nmp/config.enc`와 별도 키로 저장하고, 비밀번호·Tunnel 키를 로그·도구 인자·생성 MCP 설정에 출력하지 않음
- `NMP_CONFIG_DIR`이 지정되면 암호화 설정 오류 시 기존 환경변수로 우회하지 않음

## Testing

- 오프라인 회귀 테스트: `uv run --frozen python -B -m unittest tests.test_unit tests.test_setup tests.test_plugin_package -v`
- Compose 더미 검사: runtime 이미지 빌드 후 `uv run --frozen python -B -m tests.smoke_compose`
- 실계정 선택 검사: `NMP_CONFIG_DIR`을 설치된 `.nmp` 절대 경로로 지정하고 `uv run --frozen python -m tests.test_integration`
- 실계정 테스트는 발송·초안 저장을 하지 않는다. SKIP은 PASS로 집계하지 않으며 실패 시 종료 코드 1.
- `docs/test-results.md`의 과거 실계정 결과는 현재 변경의 실연결 증거로 취급하지 않는다.

## Server Deployment

- 설치 진입점은 `scripts/install.ps1`(local/tunnel)과 `scripts/install.sh`(local/tunnel/server)
- Linux 상시 실행은 `Dockerfile`과 `compose.yaml`, 암호화한 `.nmp/`를 읽기 전용으로 마운트한다. 이미지·Git에 포함하지 않는다.
- Compose 명령에는 항상 `--env-file .nmp/compose.env`를 지정해 런타임 UID/GID를 맞춘다.
- `.env.example`은 기존 stdio 실행의 호환 설정이다. `NAVER_EMAIL_PASSWORD_FILE`과 일반 비밀번호 환경변수를 동시에 설정하지 않는다.
- 파일 암호화는 호스트 root/관리자로부터 비밀값을 숨기지 못한다. 개인 Tunnel 접근 권한을 다른 사용자에게 공유하지 않는다.
- `healthy`/`readyz`는 OpenAI 인증이나 네이버 로그인 성공을 보장하지 않는다.
- 원격 배포와 실계정 검증은 `docs/server-deployment.md` 절차로 별도 확인한다.

## Plugin Packages

- 패키지 리소스는 `src/naver_mail_mcp/plugin/`, 빌더는 `plugin_package.py`에 둔다.
- `nmp package --public`은 연결 없는 공용 설치 도우미만 생성한다. 개인 설정을 읽지 않는다.
- `nmp package --connection`은 사용자가 지정한 본인 MCP 연결의 `.app.json`만 추가한다. 자격증명은 포함하지 않는다.
- GitHub 릴리스에는 공용 ZIP만 올린다. `.nmp/`의 개인 ZIP과 실제 연결 ID를 올리지 않는다.
