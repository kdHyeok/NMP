---
{"name":"setup","description":"Help the user install their own NMP server, configure a private OpenAI Tunnel, and connect or verify their personal ChatGPT Naver Mail plugin."}
---

# 개인 네이버 메일 연결 설정

한국어로 짧게 안내하되 사용자가 쓰는 언어가 있으면 따른다.
이 플러그인은 사용자 자신의 PC/서버와 네이버 계정을 사용한다. 중앙 메일 서비스가 아니다.

## 이미 연결된 경우

이 플러그인의 `get_profile`과 `list_folders`가 사용 가능한지 먼저 확인한다.
사용자가 연결 검사를 요청했다면 두 조회 도구로 검사하고 성공 여부만 요약한다.
이미 작동하는 서버·Tunnel·연결은 재생성하지 않는다. 초안 저장이나 발송으로 검사하지 않는다.
메일 주소·본문·제목 등 개인정보는 검사 결과에 나열하지 않는다.

## 처음 설치하는 경우

1. 사용자의 설치 대상이 PC인지 상시 실행할 Linux 서버인지 확인한다. 운영체제에 맞춰 한 경로만 안내한다.
2. Git과 uv를 설치하고 `https://github.com/kdHyeok/NMP`를 클론한다.
   Windows PC에서는 `scripts/install.ps1 -Mode tunnel`, Linux/macOS PC에서는
   `bash scripts/install.sh tunnel`, Linux 서버에서는 `bash scripts/install.sh server`를 실행한다.
   서버 모드는 Docker Engine과 Compose도 필요하다.
3. 네이버 IMAP/SMTP 활성화와 전용 앱 비밀번호를 준비하도록 안내한다.
   OpenAI의 `https://platform.openai.com/settings/organization/tunnels`에서
   본인 계정/워크스페이스 전용 Tunnel을 만들고 실제 ID를 사용한다.
   생성은 Tunnels Read + Manage, 실행용 API 키와 사용자에게는 Read + Use가 필요하다.
   `https://platform.openai.com/settings/organization/api-keys`에서 Restricted 키의 Tunnels → Use를 선택하면
   Read도 함께 선택되는지 확인한다. 다른 API 권한은 필요하지 않다. 계정/화면 차이가 있으면 현재 공식 안내를 확인한다.
4. 비밀번호와 키는 사용자가 로컬 PowerShell/Bash의 숨김 입력란에 직접 입력한다.
   채팅·스크린샷·명령 인자·플러그인 ZIP·Git에 넣지 않는다. 암호화 파일이나 키 파일을 읽어 출력하지 않는다.
5. PC 모드는 `uv run --frozen nmp tunnel`을 계속 실행한다. 서버 모드는 설치기가 Compose를 실행한다.
   OpenAI 인증·polling을 확인하고, healthy 표시만으로 계정 연결 완료라고 판단하지 않는다.
6. ChatGPT Plugins → 추가 → 사용자 지정 MCP 서버 추가에서 이름 Naver Mail Plugin,
   연결 Tunnel, 본인의 Tunnel ID, 인증 없음으로 개인 연결을 만든다.
   다른 사용자의 Tunnel이나 연결을 복사하거나 공유하지 않는다.
7. 생성된 연결의 상세 페이지 URL을 복사해 저장소 루트에서
   `uv run --frozen nmp package --connection "본인의 실제 ChatGPT 플러그인 상세 URL"`을 실행한다.
   `.nmp/naver-mail-plugin.zip`은 본인의 연결만 참조하며 비밀번호·API 키를 포함하지 않는다.
8. ChatGPT Plugins → 추가 → 플러그인 압축 파일 업로드에서 생성된 개인 ZIP을 설치한다.
   계정의 ZIP 업로드 기능이 제공되지 않으면 기존 MCP 연결을 계속 사용하고 패키지 설치는 미완료로 표시한다.
9. 새 대화에서 Naver Mail Plugin을 선택해 프로필·메일함 조회를 검사한다.
   도구가 보이지 않으면 설치/연결 상태를 확인하고 잠시 후 다시 확인한다. 성공 전에는 완료라고 말하지 않는다.

공용 NMP 설치 도우미 ZIP에는 사용자 메일 도구 연결이 없다. 개인 ZIP을 만든 뒤 사용해야 한다.
패키지는 서버를 호스팅하지 않으며 PC를 끄면 연결이 끊긴다. 호스트 관리자는 실행 중 비밀값에 접근할 수 있다.
자세한 설치 안내: https://github.com/kdHyeok/NMP/blob/main/docs/plugin-distribution.md
