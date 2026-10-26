# Linux 서버 상시 실행

사용자별 Linux 서버에 stdio NMP와 OpenAI Tunnel을 함께 실행한다. 공개 포트, 도메인, Cloudflare Tunnel이나 OAuth 서버를 구성하지 않는다. 서버에서 OpenAI HTTPS와 네이버 IMAP/SMTP로 나갈 수 있어야 한다.

## 최초 설치

Git, uv, Docker Engine과 Compose가 필요하다. Docker 명령을 실행할 권한을 준비한다. 저장소를 클론한 후 서버의 Bash에서 실행한다.

```bash
git clone https://github.com/kdHyeok/NMP.git
cd NMP
bash scripts/install.sh server
```

설치기는 메일 주소·표시 이름·앱 비밀번호·개인 Tunnel ID·런타임 키를 입력받는다. 비밀값은 숨김 입력이다. 네이버 IMAP/SMTP와 앱 비밀번호, 본인 OpenAI Tunnel 권한은 [계정 준비 가이드](chatgpt-setup.md)를 따른다.

`.nmp/config.enc`에는 암호화한 설정, `.nmp/key`에는 복호화 키를 저장한다. 둘을 Git·채팅·공용 백업에 올리지 않는다. 복호화 키를 잃으면 기존 암호문을 복구할 수 없다. 파일을 출력하는 `cat`이나 디버그 옵션으로 비밀값을 노출하지 않는다.

일반 사용자 설치는 컨테이너 UID/GID를 해당 사용자에 맞춘다. root로 설치하면 런타임 UID/GID 10001로 설정하고 파일 소유권도 맞춘다. 이 값은 `.nmp/compose.env`에 저장한다. 수동으로 파일을 전역 읽기 허용으로 바꾸지 않는다.

## 상태와 실제 연결 확인

아래 명령은 저장소 루트에서 실행한다. 생성한 env 파일을 항상 지정한다.

```bash
docker compose --env-file .nmp/compose.env ps
docker compose --env-file .nmp/compose.env logs --tail 50 nmp
uv run --frozen nmp info
```

상세 상태는 컨테이너 내부에서만 조회한다.

```bash
docker compose --env-file .nmp/compose.env exec -T nmp python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8080/health?details=true', timeout=4).read().decode())"
```

`healthy`와 `/readyz`는 런타임 시작 상태다. stdio 초기 통신 전이나 OpenAI 접속 실패 중에도 성공할 수 있다. `control-plane`이 `degraded`이면 ID, 키 권한, DNS와 외부 접속을 확인한다. ChatGPT에서 같은 Tunnel ID를 등록하고 프로필·메일함·본문 조회까지 성공해야 실제 연결 완료다.

Docker 설정에는 비밀값이 없지만 실행 중 Tunnel 자식 프로세스는 복호화한 런타임 키를 환경으로 받는다. 호스트 관리자와 동일 사용자 프로세스는 실행 중 비밀값에 접근할 수 있다. 암호화가 호스트 전체 침해를 막는다고 가정하지 않는다.

## 재부팅과 업데이트

일반적인 systemd 기반 Docker Engine 서버에서는 부팅 시 Docker를 시작한다.

```bash
sudo systemctl enable --now docker
```

```bash
# 업데이트: 설정과 키를 보존하며 새 컨테이너로 교체한다.
git pull --ff-only
bash scripts/install.sh server

# 명시적 중지 / 재시작
docker compose --env-file .nmp/compose.env stop
docker compose --env-file .nmp/compose.env up -d
```

`unless-stopped`는 프로세스 종료와 호스트 재부팅에 대응한다. 직접 중지한 컨테이너는 `up -d`로 다시 시작한다. `unhealthy` 표시만으로 Docker가 재시작하지는 않는다. 업데이트 중 발송이 중단됐다면 자동 재시도하지 않고 보낸메일함을 먼저 확인한다.

## 자격증명 변경과 제거

```bash
uv run --frozen nmp setup --mode server --replace
docker compose --env-file .nmp/compose.env up -d --force-recreate
```

명시적인 변경만 기존 설정을 덮어쓰며 암호화 키 자체는 보존한다. 새 연결을 확인하고 이전 네이버 앱 비밀번호와 OpenAI 키를 폐기한다. 서버 폐기 시 컨테이너를 내리고 해당 자격증명과 Tunnel 권한도 폐기한다. 설정 디렉터리는 자동 삭제하지 않는다.

이전 버전의 `.env`와 평문 `.secrets/`를 자동 이관하거나 지우지 않는다. 새 설치기로 재입력하고 실제 연결을 확인한 후 이전 파일을 직접 정리한다. 이전 PC 실행기는 같은 Tunnel을 사용하지 않도록 종료한다.

Windows/macOS PC는 `tunnel` 모드를 사용한다. Linux amd64에서 컨테이너 실행을 검증하며 arm64와 macOS의 실기 검증 여부는 [테스트 기록](test-results.md)에 구분한다.