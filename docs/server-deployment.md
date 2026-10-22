# 서버에서 Naver Mail Plugin 상시 실행

Linux 서버에서 실행하는 개인용 구성이다. PC를 꺼도 서버와 Docker가 실행 중이면 웹 ChatGPT에서 사용할 수 있다. 서버 생성이나 실제 계정 등록은 이 저장소를 올리는 것과 별개다.

## 1. 준비

- Linux amd64 또는 arm64 서버에 [Docker Engine](https://docs.docker.com/engine/install/)과 [Compose 플러그인](https://docs.docker.com/compose/install/linux/)을 설치한다. Docker를 실행할 수 있는 사용자로 아래 명령을 수행한다.
- 서버에서 OpenAI `api.openai.com:443` HTTPS, 네이버 `imap.naver.com:993`, `smtp.naver.com:465`에 나갈 수 있어야 한다. 빌드할 때 Docker Hub, GHCR, GitHub Releases, Debian 저장소와 Python 패키지 저장소에도 접근한다.
- 네이버 메일 환경설정에서 IMAP/SMTP를 활성화하고 전용 앱 비밀번호를 만든다. [네이버 공식 안내](https://help.naver.com/service/30029/contents/24347?lang=ko&osType=COMMONOS)를 참고한다.
- [OpenAI Platform Tunnels](https://platform.openai.com/settings/organization/tunnels)에서 개인 Tunnel을 준비하고 본인의 Platform 조직 및 ChatGPT 워크스페이스에 연결한다. Tunnel 생성에는 Read + Manage, 실행에는 Read + Use 권한이 필요하다.
- [Runtime API keys](https://platform.openai.com/settings/organization/api-keys)에서 해당 Tunnel에 Read + Use 권한이 있는 런타임 키를 만든다. 상시 실행용으로 관리자 키를 사용하지 않는다.
- ChatGPT 계정에서 사용자 지정 MCP와 Tunnel 연결을 사용할 수 있어야 한다. 기능 노출과 조직 권한은 계정에서 확인한다.

MCP 공개 포트나 도메인, 별도의 TLS 프록시는 이 구성에 필요하지 않다. 서버의 외부 접속을 이용한다. [OpenAI 공식 네트워크 요구사항](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels#network-requirements)을 참고한다.

## 2. 코드와 일반 설정

```bash
git clone https://github.com/kdHyeok/NMP.git
cd NMP
cp .env.example .env
chmod 600 .env
```

`.env`를 편집한다. Tunnel ID는 발급된 실제 값을 그대로 사용한다.

```dotenv
NAVER_EMAIL_ADDRESS=your_id@naver.com
NAVER_FULL_NAME=Your Name
CONTROL_PLANE_TUNNEL_ID=tunnel_replace_with_your_id
```

여기에는 비밀번호와 API 키를 넣지 않는다. `.env`는 Git에서 제외되어 있다.

## 3. 비밀 파일 생성

아래는 **Bash** 명령이다. 입력은 화면과 명령 기록에 표시되지 않으며, 비밀값을 명령 인자로 전달하지 않는다. 채팅에 값을 붙여 넣지 않는다.

```bash
umask 077
install -d -m 700 .secrets
read -rsp 'Naver app password: ' nmp_password
printf '\n'
printf '%s' "$nmp_password" > .secrets/naver_email_password
unset nmp_password
read -rsp 'OpenAI Tunnel runtime key: ' nmp_tunnel_key
printf '\n'
printf '%s' "$nmp_tunnel_key" > .secrets/openai_tunnel_api_key
unset nmp_tunnel_key
chmod 444 .secrets/naver_email_password .secrets/openai_tunnel_api_key
```

`.secrets` 디렉터리는 반드시 **700**으로 유지한다. 호스트의 다른 일반 사용자는 디렉터리에 들어갈 수 없다. 파일의 **444**는 컨테이너 일반 사용자 UID 10001이 읽기 위해 필요하다. Compose의 파일 기반 secrets는 호스트 파일을 마운트하므로 `uid`/`mode` 설정만으로 소유권이 바뀐다고 가정하면 안 된다.

두 파일은 컨테이너에 읽기 전용으로 마운트된다. Compose secrets는 호스트 파일을 암호화하지 않으며 Docker 관리자와 호스트 root는 읽을 수 있다. `.secrets/`는 Git과 Docker 빌드 컨텍스트에서 제외했다. 서버 백업에서도 비밀 파일의 접근 권한을 유지한다.

## 4. 실행과 준비 상태 확인

```bash
docker compose config --quiet
docker compose up -d --build
docker compose ps
docker compose logs --tail 50 nmp
```

최초 빌드에서 Python 3.12.15, uv 0.11.32, 잠금 파일의 MCP SDK 2.3.0을 설치한다. 공식 tunnel-client v0.0.17의 해당 CPU 아카이브를 다운로드하고 배포 체크섬을 검사한다.

`docker compose ps`에서 `healthy`를 확인한다. 직접 검사할 수도 있다.

```bash
docker compose exec -T nmp python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8080/readyz', timeout=4).read().decode())"
```

`/readyz`와 Compose의 `healthy`는 런타임 시작 상태다. stdio에서는 첫 MCP 통신 전이나 OpenAI 접속이 실패하는 동안에도 성공할 수 있다. **Tunnel 키 인증, 도구 검색과 네이버 로그인 성공을 보장하지 않는다.** 접속 문제는 아래 상세 상태의 `control-plane`과 로그를 확인하고, 반드시 ChatGPT에서 실제 읽기 도구를 호출해 검증한다.

```bash
docker compose exec -T nmp python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8080/health?details=true', timeout=4).read().decode())"
```

`control-plane`이 `degraded`이면 ID, 키 권한, DNS와 외부 접속을 확인한다. 상태는 관측 당시 정보이며 계속 연결된다는 보장은 아니다. 로그에 원시 HTTP 본문을 기록하는 디버그 옵션은 켜지 않는다. 로그를 공유할 때는 메일 주소와 내용을 확인한다. [공식 상태 검사 설명](https://github.com/openai/tunnel-client/blob/master/docs/health.md)을 참고한다.

설정은 포트를 게시하지 않으며 health/admin 주소도 컨테이너 내부 loopback으로 한정한다. 상태 확인은 `docker compose exec`로 한다.

## 5. 웹 ChatGPT 등록

1. ChatGPT 웹에서 Plugins → + → Add custom MCP server를 연다.
2. 이름을 `Naver Mail Plugin`, Connection을 `Tunnel`로 선택하고 동일한 Tunnel ID를 입력한다.
3. 이 stdio MCP에는 추가 OAuth가 없으므로 Authentication을 `No authentication`으로 설정한다.
4. 본인 계정에 설치하고 대화에서 선택한다. Tunnel과 플러그인을 다른 사용자나 워크스페이스에 공유하지 않는다.

접근 경계는 OpenAI 계정과 Tunnel 권한이다. 공개 URL에 인증 없이 이 서버를 노출하는 방식은 제공하지 않는다. 같은 Tunnel ID로 PC 실행기와 서버를 동시에 실행하지 않는다. 서버로 옮겼다면 PC 실행기를 종료한다.

먼저 “메일 계정 프로필과 메일함 목록을 보여줘”로 실제 로그인을 확인한다. 다음으로 메일 1~5개 검색과 읽기를 확인한다. 발송은 수신자와 본문을 확인하는 MCP form elicitation을 지원해야 한다. 확인 기능 미지원·취소·거절이면 발송하지 않는다. 초안 저장도 네이버 계정을 변경하는 작업이다.

## 6. 재부팅, 업데이트와 키 교체

systemd 기반 서버에서는 Docker의 부팅 시 시작을 활성화한다.

```bash
sudo systemctl enable --now docker
```

컨테이너는 `restart: unless-stopped`를 사용한다. 프로세스 종료나 호스트 재부팅 후 Docker가 시작되면 다시 실행한다. `docker compose stop`으로 직접 멈춘 컨테이너는 자동으로 재시작하지 않으므로 `docker compose up -d`로 다시 시작한다.

```bash
# 상태와 최근 로그
docker compose ps
docker compose logs --tail 100 nmp

# 코드 업데이트: 새 컨테이너로 교체되므로 짧은 중단 발생
git pull --ff-only
docker compose up -d --build

# 명시적 재시작 / 중지
docker compose restart nmp
docker compose stop
```

준비 상태 검사는 자동 복구 기능이 아니다. `unhealthy`만으로 Docker가 재시작하지는 않는다. 설정과 네트워크를 고친 뒤 필요하면 명시적으로 재시작한다. 중단 중이던 발송은 자동 재시도하지 말고 보낸메일함을 먼저 확인한다.

키 교체 시 파일을 `chmod 600`으로 변경하고 3단계 숨김 입력으로 새 값을 쓴 뒤 다시 `chmod 444`로 설정한다. `docker compose up -d --force-recreate` 후 `healthy`와 실제 조회를 확인하고 이전 키를 폐기한다. 서버 폐기 시에도 네이버 앱 비밀번호와 OpenAI 런타임 키를 폐기한다.

## 검증 범위

Docker 빌드, 오프라인 회귀 테스트와 더미 키를 사용한 컨테이너 검사는 실제 계정 연결 성공을 의미하지 않는다. 계정 설정 후 Tunnel 준비 상태와 ChatGPT의 읽기 도구 호출까지 확인해야 배포 완료다. 구체적인 실행 결과는 [검증 기록](test-results.md)을 참고한다.
