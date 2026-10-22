# Test Results — Naver Mail Plugin

## 2026-10-22 Docker Compose 서버 구성 검증

- Windows / Python 3.12.12: `python -B -m unittest tests.test_unit -q` 32개 PASS
- Linux amd64 / Python 3.12.15: Docker test target에서 같은 테스트 31개 PASS,
  Windows 실행기 전용 1개 SKIP. UID 10001, 읽기 전용 루트 파일시스템과 tmpfs에서 실행
- 공식 MCP SDK 2.3.0, tunnel-client v0.0.17 Linux amd64 배포 체크섬 검사와 runtime/test 이미지 빌드 PASS
- 파일 비밀번호 읽기, 기존 환경변수 호환, 중복 설정·누락·빈 파일·잘못된 UTF-8 거부 검사 PASS
- Windows 실행기의 비밀번호 파일 사용과 실계정 검사 도구의 공통 자격증명 처리 검사 PASS
- 더미 키와 `network_mode: none`, 닫힌 로컬 control-plane 주소를 사용하는 별도 Compose 프로젝트에서 검사:
  - Compose 설정 해석, 일반 사용자, 읽기 전용 루트, 비밀 파일 읽기 전용 마운트, 게시 포트 없음 PASS
  - 앱 비밀번호 파일을 서버가 읽고, 비밀값이 컨테이너 환경변수에 없는 것 확인
  - `/healthz`·`/readyz` 응답과 상세 상태의 control-plane `degraded`, stdio child `running` 확인
  - Tunnel 프로세스를 SIGKILL로 종료한 후 `unless-stopped` 정책의 자동 재시작 확인
  - 검사 종료 후 테스트 컨테이너 제거 확인
- `/readyz`는 stdio 초기 통신 전과 OpenAI 접속 실패 중에도 200일 수 있음을 실제 확인했다.
  Compose의 `healthy`를 키 인증·도구 검색·메일 로그인 성공으로 해석하지 않는다.
- `uv --cache-dir .uv-cache lock --check --offline`, `git diff --check` PASS
- 실제 네이버 로그인·발송, 개인 OpenAI Tunnel 인증, 웹 ChatGPT 호출과 원격 서버 배포는 미실행
- arm64 이미지는 배포 아카이브와 빌드 분기를 제공하지만 실제 빌드·실행은 amd64에서만 검증했다.
  호스트 재부팅은 실행하지 않았으며 Docker 부팅 설정은 배포 문서로 제공한다.

## 2026-10-22 공식 MCP SDK v2 마이그레이션 검증

- Windows / Python 3.12.12 / 공식 `mcp` 2.3.0 및 `mcp-types` 2.3.0
- `python -B -m unittest tests.test_unit -v`: 30개 PASS
- `uv lock --check --offline`: 잠금 파일 일치, `uv pip check`: 설치된 패키지 호환성 PASS
- `MCPServer`, snake_case 프로토콜 필드, v2 `Client`로 서버·테스트 마이그레이션
- `Resolve`/`Elicit` 발송 확인을 기존 초기화 프로토콜과 2026-07-28 프로토콜에서 검증
- 승인 시 모의 SMTP를 정확히 한 번 호출하고 거절·취소·확인 미지원 시 호출하지 않음
- 확인 결과를 도구 인자로 주입할 수 없고, 수신자가 바뀐 확인 재개 요청은 SDK의
  requestState 검증에서 거부됨을 확인
- 두 프로토콜에서 실제 stdio 하위 프로세스의 도구 9개 검색과 발송 취소 PASS
- 실제 네이버 로그인·발송 및 OpenAI Tunnel/ChatGPT 웹 연동은 실행하지 않음

공식 기준: [v1 → v2 마이그레이션](https://py.sdk.modelcontextprotocol.io/migration/),
[Resolver 기반 확인](https://py.sdk.modelcontextprotocol.io/handlers/elicitation/)

## 2026-10-22 개인용 ChatGPT 연결 준비 검증

- Windows / Python 3.12.12 / MCP SDK 1.26.0
- `python -B -m unittest tests.test_unit -v`: 28개 PASS
- 실제 stdio 하위 프로세스 초기화, 도구 9개 검색, elicitation 거절 시 발송 취소 확인
- 검증용 SSL context, IMAP 명령 삽입 거부, UTF-8 literal 및 한글 폴더명,
  날짜 검증·잘못된 메일 날짜 복구, bounded 다운로드, 부분 발송 결과,
  발송 확인·취소·미지원, 응답 크기 제한, 실계정 테스트의 실패/SKIP 집계 검사
- PowerShell 실행기의 doctor → run 순서, 검사 전용 모드, 실패 시 중단, 환경 복원,
  비밀값을 명령 인자에 전달하지 않는 동작 검사
- Windows tunnel-client v0.0.17 공식 배포 체크섬 확인 및 doctor 로컬 설정 검사 PASS
  (더미 ID/키와 닫힌 로컬 control-plane 주소 사용; 실제 키나 Tunnel 접근 검증은 아님)
- 메일 서버는 모의 응답으로 검사했다. 실제 네이버 접속·초안 저장·메일 발송은 실행하지 않았다.
- 개인 OpenAI Tunnel과 ChatGPT 웹에서의 실제 도구 호출은 자격증명 설정 후 확인해야 한다.

아래는 원 저장소의 2026-03-16 기록이며, 현재 수정본에 대한 실계정 재검증 결과가 아니다.

## Environment
- Date: 2026-03-16
- Python: 3.12.12
- MCP SDK: 1.26.0
- OS: macOS (Darwin 25.3.0)

## Unit Tests (Encoding Utilities)

| Test | Status | Notes |
|------|--------|-------|
| mUTF-7 encode ASCII | PASS | INBOX, Sent Messages, Drafts roundtrip |
| mUTF-7 encode Korean | PASS | 받은메일함 roundtrip |
| mUTF-7 ampersand | PASS | & → &- → & |
| RFC 2047 UTF-8 header | PASS | =?UTF-8?B?...?= → 한글 메일 테스트 |
| EUC-KR decode | PASS | charset 명시 시 정상 |
| Charset fallback chain | PASS | charset 없이도 한글 디코딩 |

## Security Tests

| Test | Status | Notes |
|------|--------|-------|
| Folder name injection | PASS | `"` 포함 시 ValueError |
| Message-ID injection | PASS | `"` 포함 시 ValueError |
| UID validation | PASS | 비숫자 거부 |
| Header CRLF injection | PASS | `\r\n` 포함 시 ValueError |
| body_type whitelist | PASS | text/plain, text/html만 허용 |
| Pagination bounds | PASS | page<1, page_size>100 거부 |
| Missing env vars | PASS | 명확한 에러 메시지 |
| Wrong password | PASS | AuthenticationError 정상 발생 |

## Integration Tests (Real Naver Server)

| Tool | Status | Notes |
|------|--------|-------|
| get_profile | PASS | total: 5000, unseen: 0 정상 반환 |
| list_folders | PASS | 10개 폴더 — INBOX, Sent Messages, Drafts, Deleted Messages, Junk, 내게쓴메일함, 깃허브, papers, 결제, 보안 |
| search_emails | PASS | 5000건 중 page=1, page_size=5 반환, 한글 제목 정상 |
| read_email | PASS | UID 13979, 한글 제목, HTML 본문 4673자 |
| read_thread | PASS | Message-ID 기반 스레드 조회 (1건 스레드) |
| create_draft | PASS | 한글 제목 초안 저장 성공, Drafts 폴더에 정상 추가 확인 |
| list_drafts | PASS | 4개 초안 정상 조회, 한글 제목 포함 |
| send_email | PASS | chanmuzi22@gmail.com으로 테스트 메일 발송 성공 |
| download_attachment | PASS | PNG 303,778 bytes → base64 405,040자 정상 |

## Korean Encoding Tests

| Scenario | Status | Notes |
|----------|--------|-------|
| Korean subject display | PASS | [카카오뮤직] D-7 탈퇴 예정 안내 |
| Korean body (UTF-8) | PASS | HTML 본문 한글 정상 |
| Korean folder names | PASS | 내게쓴메일함, 깃허브, 결제, 보안 — mUTF-7 디코딩 정상 |
| Korean search term | - | 추후 테스트 필요 |

## Error Handling Tests

| Scenario | Status | Notes |
|----------|--------|-------|
| Wrong password | PASS | "IMAP authentication failed. Check your Naver email address and app password." |
| Missing env vars | PASS | "Missing required environment variables: ..." |
| Nonexistent UID | - | 추후 테스트 필요 |
| Invalid folder name | - | 추후 테스트 필요 |

## Naver IMAP 특이사항

- 폴더명은 영문으로 반환됨 (INBOX, Sent Messages, Drafts, Deleted Messages, Junk)
- 사용자 생성 폴더는 mUTF-7로 인코딩 (내게쓴메일함 → &sLSsjMT0ulTHfNVo-)
- SEARCH ALL 정상 동작 확인
- UID FETCH (FLAGS RFC822) 정상 동작 확인
- Drafts 폴더명은 "Drafts" (영문)
- Sent 폴더명은 "Sent Messages"

## Issues Found

(none)

## Changelog

| Date | Changes |
|------|---------|
| 2026-03-16 | 초기 테스트: 인코딩 유닛 6개, 보안 8개, 통합 8개 PASS |
| 2026-03-16 | send_email 테스트 PASS (chanmuzi22@gmail.com 발송 확인) — 9/9 전부 PASS |
