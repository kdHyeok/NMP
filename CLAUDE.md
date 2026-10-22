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

## Testing

- 오프라인 회귀 테스트: `uv run --frozen python -m unittest tests.test_unit -v`
- 실계정 선택 검사: `uv run --frozen --env-file .env python -m tests.test_integration`
- 실계정 테스트는 발송·초안 저장을 하지 않는다. SKIP은 PASS로 집계하지 않으며 실패 시 종료 코드 1.
- `docs/test-results.md`의 과거 실계정 결과는 현재 변경의 실연결 증거로 취급하지 않는다.

## Server Deployment

- Linux 상시 실행은 `Dockerfile`과 `compose.yaml`, 설정은 `.env.example` 참고
- 비밀값은 `.secrets/` 파일을 Compose secrets로 마운트. 이미지·Git에 포함하지 않는다.
- `NAVER_EMAIL_PASSWORD_FILE`과 일반 비밀번호 환경변수를 동시에 설정하지 않는다.
- `healthy`/`readyz`는 OpenAI 인증이나 네이버 로그인 성공을 보장하지 않는다.
- 원격 배포와 실계정 검증은 `docs/server-deployment.md` 절차로 별도 확인한다.
