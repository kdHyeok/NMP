# 다른 사용자의 설치와 개인 플러그인 패키지

NMP는 사용자별 서버·네이버 계정·OpenAI Tunnel을 사용하는 오픈소스다.
작성자의 메일 서비스에 접속하는 공용 플러그인이 아니다.

## 배포 파일 선택

| 파일 | 용도 | 배포 범위 |
|---|---|---|
| `nmp-setup.zip` | ChatGPT에서 서버 설치와 개인 연결 생성을 안내하는 온보딩 플러그인 | 누구나 다운로드·설치 가능 |
| `.nmp/naver-mail-plugin.zip` | 본인이 등록한 MCP 연결과 메일 사용 스킬을 묶은 개인 플러그인 | 본인 ChatGPT에만 업로드 |

[설치 도우미 다운로드](https://github.com/kdHyeok/NMP/releases/latest/download/nmp-setup.zip) ·
[릴리스와 체크섬](https://github.com/kdHyeok/NMP/releases/latest)

공용 ZIP은 메일 접근 권한이나 특정 사용자 연결을 포함하지 않는다. 이것만 업로드하면
메일이 연결되는 것은 아니다. 개인 서버 설치와 아래 연결 과정이 필요하다.
서버의 앱 비밀번호·Tunnel 키·암호화 설정은 어느 ZIP에도 포함하지 않는다.

## 1. 설치 도우미 설치 — 선택 사항

ChatGPT Plugins → 추가 → **플러그인 압축 파일 업로드**에서 `nmp-setup.zip`을 선택한다.
설치 후 설정 실행 또는 대화에서 NMP 설치 도우미를 선택해 설치 안내를 요청한다.
직접 설치하려면 이 단계는 건너뛰어도 된다.

## 2. 자기 PC나 서버에 NMP 설치

Git과 [uv](https://docs.astral.sh/uv/getting-started/installation/)를 먼저 설치한다.
Linux 서버 모드는 Docker Engine과 Compose도 필요하다.

```bash
git clone https://github.com/kdHyeok/NMP.git
cd NMP
```

| 설치 대상 | 명령 |
|---|---|
| Windows PC | `.\scripts\install.ps1 -Mode tunnel` |
| Linux/macOS PC | `bash scripts/install.sh tunnel` |
| Linux 서버 상시 실행 | `bash scripts/install.sh server` |

네이버 IMAP/SMTP와 전용 앱 비밀번호를 준비하고, 자신의 OpenAI 계정에서
[Tunnel](https://platform.openai.com/settings/organization/tunnels)과
[실행용 API 키](https://platform.openai.com/settings/organization/api-keys)를 만든다.
키는 Restricted로 제한하고 Tunnels의 Read·Use만 부여한다.
계정의 조직 권한과 키 권한이 모두 필요하다. 발급 화면과 계정별 제한은
[OpenAI 공식 안내](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels)를 확인한다.

비밀번호와 키는 설치기의 숨김 입력란에 직접 입력한다. 채팅이나 명령 인자에 넣지 않는다.
PC 모드는 설치 후 아래 명령을 실행해 둔다. 서버 모드는 설치기가 Compose를 실행한다.

```bash
uv run --frozen nmp tunnel
```

## 3. 자신의 ChatGPT MCP 연결 생성

1. ChatGPT의 Plugins → 추가 → **사용자 지정 MCP 서버 추가**를 연다.
2. 이름은 `Naver Mail Plugin`, 연결은 **Tunnel**, ID는 본인의 실제 Tunnel ID를 지정한다.
3. 인증은 **인증 없음**을 선택하고 개인용으로 생성·연결한다. 접근 통제는 본인 OpenAI 계정과 Tunnel 권한이다.
4. 생성된 연결의 상세 페이지를 열고 브라우저 URL을 복사한다.
   URL의 경로는 `/plugins/plugin_asdk_app_`으로 시작한다. 작성자나 다른 사람의 URL을 복사하지 않는다.

## 4. 개인 플러그인 ZIP 생성과 설치

NMP 저장소 루트에서 실행하고, 대괄호 부분을 **본인의 실제 상세 페이지 URL**로 바꾼다.

```bash
uv run --frozen nmp package --connection "<본인의 ChatGPT MCP 연결 상세 URL>"
```

생성 파일은 `.nmp/naver-mail-plugin.zip`이다. 여기에는 다음이 포함된다.

- Agent Plugins 형식의 `plugin.json` 매니페스트
- 처음 설치 및 연결 확인용 `setup` 스킬
- 검색·읽기·초안·발송 절차와 확인 규칙을 제공하는 `naver-mail` 스킬
- 본인의 등록된 MCP 연결만 참조하는 `.app.json`
- 패키지 안내와 원본 MIT 라이선스

ChatGPT Plugins → 추가 → **플러그인 압축 파일 업로드**에서 개인 ZIP을 선택한다.
설치된 패키지에서 설정을 실행해 도구를 확인하고, 새 대화에서도 Naver Mail Plugin을 선택한다.
먼저 연결 상태와 메일함 개수만 조회한다. 검색이나 본문 읽기는 필요한 메일에 한정한다.
초안 저장·발송은 실제 계정을 변경하며, 발송에는 별도 대화형 확인이 필요하다.

개인 ZIP의 ID 형식 검사는 연결의 소유권·권한·서버 정상 실행을 검증하지 않는다.
본인 계정에서 실제 도구 조회가 성공해야 완료다. ZIP 업로드가 제공되지 않는 계정에서는
기존 MCP 연결을 사용할 수 있지만, 패키지 설치는 미완료다.

개인 ZIP은 공유하지 않는다. 다른 사용자는 자기 계정으로 위 과정을 수행한다.
연결을 새로 만들면 새 URL로 개인 ZIP을 다시 생성한다. 같은 연결의 코드를 업데이트했다면
MCP 연결의 도구 갱신도 확인한다. 기존 개인 패키지가 있으면 그 패키지를 업데이트하고 중복 설치를 피한다.

설치된 플러그인의 버전이 더 높아 업데이트가 거부되면 현재 버전보다 큰 값을 지정해 재생성한다.
예를 들어 현재 버전이 `0.2.1`이면 위 생성 명령 끝에 `--version 0.2.2`를 추가한다.

## 유지보수자: 공용 배포 파일 재생성

```bash
uv run --frozen nmp package --public
uv run --frozen python -B -m unittest tests.test_unit tests.test_setup tests.test_plugin_package -v
```

공용 ZIP은 설정 파일을 읽지 않고 `dist/nmp-setup.zip`에 생성된다. 패키징은 명시한 리소스만 사용하며
작업 디렉터리·환경변수·`.nmp`·`.env`·실행 로그를 수집하지 않는다. 소스 수정 후 ZIP을 다시 빌드하고 검사한다.
릴리스에는 공용 ZIP과 SHA256 체크섬만 첨부한다. 개인 ZIP이나 연결 ID는 첨부하지 않는다.

GitHub의 ZIP 배포는 ChatGPT 공개 디렉터리 등록과 다르다. 현재 개인 Tunnel 구성은
공개 디렉터리 제출용이 아니다. 이 패키지는 서버를 자동 호스팅하거나 다른 사용자의 계정 권한을 발급하지 않는다.
호스트 관리자에게 실행 중 비밀값을 숨기지는 못하며, 로컬 PC를 끄면 해당 연결도 끊긴다.
