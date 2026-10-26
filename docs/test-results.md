# Test Results — Naver Mail Plugin

## 2026-10-27 배포용 플러그인 패키지 검증

- Windows / Python 3.12.12: 전체 55개 중 51 PASS, OS 전용 4 SKIP
- 공용 ZIP에 개인 연결이 없고, 개인 ZIP에는 지정한 연결 1개와 스킬 2개만 포함되는지 검사
- 비밀번호·API 키·메일 주소·Tunnel ID가 ZIP에 포함되지 않음 확인. 환경변수와 임의 `.env` 파일도 수집하지 않음
- 잘못된 URL·ID·버전 거부와 기존 ZIP 보존, 경로 이탈·심볼릭 링크 제외,
  반복 빌드 결과 일치, 공식 Agent Plugins 매니페스트 스키마 검사 PASS
- Linux 비 root·읽기 전용·네트워크 차단 컨테이너에서 설치된 패키지 리소스와 회귀 검사 PASS
- 실제 ChatGPT에서 공용 ZIP의 setup 스킬 1개, 개인 ZIP의 setup·naver-mail 스킬 2개와
  기존 MCP 앱 연결 1개가 인식되는 것 확인
- 개인 패키지를 선택한 새 웹 대화에서 연결 재생성 없이 get_profile·list_folders 실제 조회 성공
- ChatGPT의 이전 버전 ZIP 거부를 확인하고 `--version`으로 더 높은 버전을 지정한 업데이트 성공 확인
- 제공받은 로고는 내용·크기 변경 없이 1254×1254 PNG로 변환해 README와 ZIP에 포함했다.
  매니페스트의 logo·composerIcon 참조와 파일 보존은 확인했으나 검사한 ChatGPT 웹 상세 화면은 기본 아이콘으로 표시됐다.
- 공개 배포 대상은 연결 없는 설치 도우미 ZIP과 체크섬이다. 개인 ZIP은 `.nmp/`에만 보관한다.
- 별도 타인의 계정 설치와 공개 디렉터리 심사는 수행하지 않았다. SMTP 발송·초안 저장도 미실행

## 2026-10-27 Windows 실계정·개인 Tunnel·웹 ChatGPT 연결 검증

- 검증 코드: `7e401f0` (`feature: 개인별 암호화 설정과 비공개 Tunnel 설치 지원`)
- 해당 커밋의 GitHub Actions에서 Windows·Ubuntu·macOS 오프라인 회귀 검사 PASS
  ([실행 기록](https://github.com/kdHyeok/NMP/actions/runs/40399354276)).
  Windows/Ubuntu는 각각 44 PASS·3 SKIP, macOS arm64는 43 PASS·4 SKIP
- Windows의 숨김 입력으로 실제 자격증명을 설정하고 암호화 파일 읽기와 도구 등록 검사 PASS
- 생성된 `.nmp/mcp.json`의 stdio 명령으로 도구 9개 검색, 실제 네이버 로그인·프로필·메일함 조회 PASS
- 실제 받은메일함에서 5개 검색 및 1개 BODY.PEEK 읽기 PASS. 메일 내용·계정 정보는 검사 출력에 기록하지 않음
- 공식 Windows tunnel-client v0.0.17 doctor PASS. 실제 키 인증 후 control-plane `polling`, 연속 실패 0 확인
- ChatGPT 웹의 사용자 지정 MCP 추가에서 같은 Tunnel을 연결해 개인용 `Naver Mail Plugin` 생성 및 연결 PASS
- 웹 대화에서 `get_profile`, `list_folders` 실제 호출 성공 확인. 서버 측에서도 요청 7건 완료·응답 7건 수락,
  요청 오류·타임아웃·최종 응답 전송 실패 모두 0 확인. 이는 해당 검사 시점의 누적 값이다.
- 실제 메일 발송·초안 생성은 수행하지 않음. 현재 기록에서 실계정 SMTP 발송, 첨부 다운로드,
  대화 조회, 원격 서버 배포와 재부팅 후 복구까지 검증했다고 해석하지 않는다.
- 계정 비밀값·Tunnel ID·메일 내용·개인 ChatGPT 대화는 Git에 포함하지 않는다.
- 현재 배포물은 셀프 호스팅 MCP 서버와 설치기다. ChatGPT의 개인용 MCP 연결은 생성했지만,
  별도 플러그인 패키지 배포나 공개 디렉터리 제출은 수행하지 않았다.

## 2026-10-27 개인별 설치·암호화 설정·비공개 Tunnel 검증

- Windows / Python 3.12.12: `python -B -m unittest tests.test_unit tests.test_setup -v`
  47개 중 44개 PASS, POSIX/Linux 전용 3개 SKIP
- Linux amd64 / Python 3.12.15: 같은 테스트를 네트워크 차단, UID 10001,
  읽기 전용 루트와 임시 tmpfs에서 실행. 47개 중 44개 PASS, Windows 전용 3개 SKIP
- Fernet 암호화 왕복, 암호문 손상·키 누락·잘못된 키 거부, 명시적 변경과 기존 키 보존 PASS
- POSIX 디렉터리 700·파일 600, 공개 읽기 권한·심볼릭 링크 거부 PASS
- Windows 현재 사용자/SYSTEM DACL 설정 및 광범위 그룹 권한 부재 PASS
- Bash/PowerShell 설치기의 공백·작은따옴표 경로, 인자 경계, 실패 시 중단 PASS
- 생성한 `.nmp/mcp.json` 명령으로 실제 stdio 하위 프로세스 실행, 구·신 프로토콜의
  도구 9개 검색과 발송 거절 PASS. Linux 가상환경 Python 경로도 유지됨
- 생성 설정·출력·명령 인자에 앱 비밀번호/Tunnel 키 부재, Tunnel 자식 환경으로만 키 전달,
  부모 환경 유지와 doctor 실패 시 실행 중단 PASS
- Tunnel 자동 다운로드의 SHA256 검증, 불일치 거부와 ZIP 경로 이탈 방지 PASS
- 공식 tunnel-client v0.0.17 Windows doctor로 암호화 설정과 한글·공백·작은따옴표 경로 검사 PASS
  (더미 ID/키, 닫힌 로컬 control-plane 주소. 실제 키 인증 증거가 아님)
- 공식 Linux amd64 아카이브 체크섬 검사, runtime/test 이미지 빌드 PASS
- `python -B -m tests.smoke_compose`: 더미 자격증명과 `network_mode: none`을 사용하는
  일회성 Compose 프로젝트에서 다음 항목 PASS
  - 비 root UID, 읽기 전용 루트·암호화 설정 마운트, 게시 포트 없음
  - Docker 설정 환경변수에 평문 자격증명 없음, 서버의 암호화 설정 읽기
  - stdio child `running`, 닫힌 control-plane `degraded`, health 상태 확인
  - 프로세스 SIGKILL 후 `unless-stopped` 자동 재시작과 설정 재사용
  - 검사 종료 후 전용 컨테이너·볼륨 제거
- `uv --cache-dir .uv-cache lock --check --offline`, `uv --cache-dir .uv-cache pip check`,
  `git diff --check` PASS
- Windows/Linux/macOS용 CI 정의를 추가했으며 GitHub Actions 실행은 아직 하지 않았다.
- 실제 네이버 로그인·초안 저장·발송, 개인 OpenAI Tunnel 인증, 웹 ChatGPT 호출,
  donh-ser 배포와 호스트 재부팅은 미실행. macOS/arm64 실기 검증도 하지 않았다.
- `/readyz`와 `healthy`는 OpenAI 인증이나 메일 로그인 성공을 보장하지 않는다.
  키와 암호문이 같은 장비에 있으므로 호스트 관리자 접근은 방어 범위에 포함하지 않는다.

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
