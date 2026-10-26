# 로컬 MCP와 개인 웹 ChatGPT 연결

각 사용자가 자기 장비와 자기 계정을 설정한다. 중앙 회원가입이나 네이버 OAuth 애플리케이션 등록은 필요하지 않다.

## 준비

1. 네이버 메일 환경설정에서 IMAP/SMTP를 활성화하고 2단계 인증의 전용 앱 비밀번호를 만든다.
2. Git과 [uv](https://docs.astral.sh/uv/getting-started/installation/)를 설치한다. Python 3.12를 권장한다.
3. 웹 ChatGPT를 연결하려면 [OpenAI Tunnels](https://platform.openai.com/settings/organization/tunnels)에서 개인 Tunnel과 런타임 키를 준비한다. 생성은 Read + Manage, 실행·선택은 Read + Use 권한이 필요하다. 본인 Platform 조직과 대상 ChatGPT 워크스페이스에만 연결한다.
4. ChatGPT에서 사용자 지정 MCP를 추가할 수 있는지 확인한다. 계정·워크스페이스 제한은 설치 스크립트로 해결할 수 없다.

## 설치와 설정

저장소 루트에서 실행한다.

```powershell
# Windows: 로컬 MCP
.\scripts\install.ps1 -Mode local

# Windows: 웹 ChatGPT
.\scripts\install.ps1 -Mode tunnel
```

```bash
# Linux/macOS: 로컬 MCP 또는 웹 ChatGPT
bash scripts/install.sh local
bash scripts/install.sh tunnel
```

위 명령 중 필요한 것 하나를 선택한다. 비밀번호와 키는 숨김 입력하며 파이프 입력으로 대체하지 않는다. 숨김 입력이 불가능하면 실패하도록 구현했다. PowerShell 실행 정책에 막히면 해당 프로세스에만 적용한다.

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File .\scripts\install.ps1 -Mode tunnel
```

설정은 `.nmp/`에 저장한다. 해당 디렉터리는 Git과 이미지 빌드 컨텍스트에서 제외한다. 실행 경로가 바뀌면 설치기를 다시 실행해 `.nmp/mcp.json`을 갱신한다. 기존 자격증명과 키는 보존된다. 모드나 자격증명 변경은 명시적으로 요청한다.

```bash
uv run --frozen nmp setup --mode tunnel --replace
```

## 로컬 MCP 클라이언트

`.nmp/mcp.json`의 `mcpServers` 항목을 클라이언트 설정에 병합한다. 이 파일에는 절대 실행 경로와 암호화 설정 경로만 있다. 다른 클라이언트의 기존 서버 설정을 덮어쓰지 않는다. CLI가 생성한 Python 경로는 가상환경을 유지해야 한다.

다른 장비에 이 설정 파일만 복사하면 작동하지 않는다. 해당 장비에도 설치하거나 웹 ChatGPT에서는 아래 Tunnel을 사용한다.

## 웹 ChatGPT

이 절차는 실행 중인 MCP 서버 연결을 ChatGPT의 **개인용 플러그인**으로 생성한다.
공용 설치 도우미 ZIP과 각자의 MCP 연결을 참조하는 개인 플러그인 ZIP도 제공한다.
[패키지 설치 안내](plugin-distribution.md)를 따른다. 각 사용자가 자기 서버와 Tunnel을 설정하며,
ChatGPT 공개 디렉터리 배포와는 별개다.

```bash
uv run --frozen nmp info
uv run --frozen nmp doctor
uv run --frozen nmp tunnel
```

마지막 명령은 터미널에서 계속 실행한다. 종료는 Ctrl+C다. `nmp tunnel --check`는 공식 Tunnel doctor만 실행하며 실제 키 인증·메일 로그인을 보장하지 않는다. 다운로드는 기본 v0.0.17 공식 아카이브와 체크섬을 사용한다. 수동 설치한 `tunnel-client`가 PATH에 있으면 이를 사용한다.

ChatGPT 웹에서 Plugins → + → Add custom MCP server를 연다.

| 항목 | 설정 |
|---|---|
| 이름 | Naver Mail Plugin |
| Connection | Tunnel |
| Tunnel | `nmp info`가 출력한 실제 ID |
| Authentication | No authentication |

본인 계정에 설치하고 대화에서 선택한다. No authentication은 NMP의 추가 OAuth가 없다는 뜻이며 접근 경계는 OpenAI 계정과 Tunnel 권한이다. 개인 소유자 외에는 접근을 허용하지 않는다. 같은 ID로 PC와 서버를 동시에 실행하지 않는다.

먼저 프로필·메일함 조회와 최근 메일 5개 검색을 요청한다. 본문 읽기까지 성공해야 실제 계정 연결을 확인한 것이다. 발송 확인 기능 미지원이면 초안으로 저장한 후 네이버에서 보낸다. 발송 결과가 불확실하면 보낸메일함을 확인한 뒤 재시도를 판단한다.

health URL은 실행 중 `.nmp/health.url`에서 확인할 수 있다. loopback 전용이며 서버의 `/readyz`가 성공해도 OpenAI 인증이나 메일 로그인 성공을 뜻하지 않는다.

[공식 Tunnel 안내](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels), [ChatGPT 등록 절차](https://developers.openai.com/api/docs/guides/custom-mcp-server).
