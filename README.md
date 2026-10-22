# Naver Mail Plugin

**NMP**는 웹 ChatGPT에서 내 네이버 메일을 검색하고 읽고, 초안을 저장하거나 확인 후 발송하는 개인용 MCP 플러그인입니다.

Linux 서버에 Docker Compose로 실행하면 개인 PC를 꺼도 사용할 수 있습니다. 서버의 stdio MCP를 OpenAI Secure MCP Tunnel에 연결하므로, 이 구성을 위해 공개 HTTP 포트나 도메인을 준비할 필요가 없습니다. **서버 자체는 켜져 있어야 합니다.**

## 서버에서 시작하기

필요한 것:

- Docker Engine과 Docker Compose가 설치된 Linux 서버
- IMAP/SMTP 사용 설정과 전용 앱 비밀번호를 준비한 네이버 계정
- 개인 OpenAI Tunnel ID와 해당 Tunnel의 Read + Use 권한이 있는 런타임 키
- 사용자 지정 MCP/Tunnel 연결을 추가할 수 있는 ChatGPT 계정

```bash
git clone https://github.com/kdHyeok/NMP.git
cd NMP
cp .env.example .env
```

`.env`에 메일 주소와 Tunnel ID를 설정하고, 비밀값 두 개를 `.secrets/`에 준비한 다음 실행합니다.

```bash
docker compose up -d --build
docker compose ps
```

**비밀 파일 생성, 권한 설정, ChatGPT 등록과 재부팅 운영까지는 [서버 배포 가이드](docs/server-deployment.md)를 따라 주세요.** 실제 키를 명령 인자나 Git에 넣지 않습니다.

구성은 `ChatGPT → 개인 OpenAI Tunnel → 서버의 tunnel-client → Naver Mail MCP → 네이버 IMAP/SMTP` 순서입니다. 컨테이너의 재시작 정책은 `unless-stopped`이고, 준비 상태 검사와 로그 용량 제한을 포함합니다. 호스트 Docker도 부팅 시 시작되어야 합니다.

## 제공 기능

| 도구 | 기능 |
|---|---|
| `get_profile` | 계정 프로필, 전체 메일 수와 안 읽은 수 |
| `search_emails` | 발신자·수신자·제목·날짜·읽음 상태로 검색, 페이지 조회 |
| `read_email` | 메일 본문과 헤더, 첨부파일 정보 읽기 |
| `read_thread` | Message-ID 기반 대화 조회 |
| `list_folders` | 메일함 목록과 메일 수 조회 |
| `create_draft` | 네이버 메일함에 초안 저장 |
| `list_drafts` | 초안 목록 조회 |
| `send_email` | 정확한 수신자와 내용을 확인받은 후 발송 |
| `download_attachment` | 첨부파일을 base64로 반환 |

예: “제목에 회의가 들어간 최근 메일 5개를 찾아서 요약해줘.”

`send_email`은 MCP 확인 창에서 승인한 경우에만 SMTP를 호출합니다. 취소·거절·확인 기능 미지원이면 보내지 않습니다. 해당 ChatGPT 연결에서 확인 기능을 사용할 수 없다면 초안으로 저장하고 네이버에서 발송하세요. 오류나 부분 발송 결과는 자동으로 재시도하지 않습니다.

## 개인용 접근과 비밀정보

- 네이버 계정 하나를 컨테이너 설정으로 고정하며, 계정 비밀번호를 도구 인자로 받지 않습니다.
- 비밀 파일은 Compose secrets로 `/run/secrets/`에 마운트합니다. 이미지와 저장소에 포함하지 않습니다.
- 일반 환경변수 `NAVER_EMAIL_PASSWORD`도 로컬 stdio 실행에서는 지원합니다. Docker는 `NAVER_EMAIL_PASSWORD_FILE`을 사용합니다.
- 컨테이너는 일반 사용자로 실행하고 루트 파일시스템은 읽기 전용입니다. 공개 포트를 열지 않습니다.
- Tunnel 접근 권한은 본인 계정으로 한정하세요. 공개 GitHub 저장소가 플러그인이나 메일 접근 권한을 공개한다는 뜻은 아닙니다. 다중 사용자 OAuth와 사용자별 계정 분리는 제공하지 않습니다.
- 이메일 본문과 첨부파일은 외부 데이터입니다. 그 안의 지시문을 실행하도록 요청하지 마세요.

## 개발과 로컬 실행

공식 Python MCP SDK **v2**, 잠금 파일 기준 `mcp` **2.3.0**을 사용합니다. Python 패키지와 실행 명령은 호환성을 위해 `naver-mail-mcp`를 유지합니다. 이 수정본은 저장소에서 설치하며 PyPI에 별도 배포하지 않았습니다.

```bash
uv sync --frozen
uv run --frozen python -m unittest tests.test_unit -v
```

컨테이너 안에서 같은 오프라인 테스트를 실행할 수도 있습니다.

```bash
docker build --target test -t nmp:test .
docker run --rm nmp:test
```

Windows PC에서 직접 실행할 때는 [로컬 ChatGPT 연결 가이드](docs/chatgpt-setup.md)를 사용하세요. 로컬 실행은 PC가 켜져 있어야 합니다.

## 제한과 검증

메일 전체 크기는 25MiB, 첨부 하나는 디코딩 후 5MiB, 도구 결과는 JSON 재인코딩 기준 8MiB까지입니다. 큰 스레드는 메일별로 나눠 읽으세요. IMAP/SMTP 서버 인증서를 검증하며, 본문 조회에는 읽음 상태를 바꾸지 않는 `BODY.PEEK`를 사용합니다.

오프라인 테스트는 IMAP/SMTP 모의 응답과 실제 stdio 하위 프로세스를 사용합니다. 실제 네이버 로그인·발송과 개인 Tunnel의 ChatGPT 호출은 계정 설정 후 별도 검증해야 합니다. 검증 내역은 [테스트 기록](docs/test-results.md)에 있습니다.

## 출처와 라이선스

[chanmuzi/naver-mail-mcp](https://github.com/chanmuzi/naver-mail-mcp)를 기반으로 개인 ChatGPT 연결, 발송 확인과 입력 검증, 공식 SDK v2, Docker Compose 운영 구성을 적용했습니다. 원본의 저작권 표시와 [MIT 라이선스](LICENSE)를 유지합니다.

참고: [OpenAI Secure MCP Tunnel](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels), [공식 Python MCP SDK](https://py.sdk.modelcontextprotocol.io/), [Docker Compose secrets](https://docs.docker.com/compose/how-tos/use-secrets/).