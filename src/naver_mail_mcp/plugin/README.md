# Naver Mail Plugin

NMP 설치 도우미는 서버 설치와 개인 ChatGPT 연결을 안내하는 공용 플러그인이다.
메일 도구는 사용자가 자신의 MCP 연결로 만든 개인 플러그인 ZIP에만 포함된다.

설치: https://github.com/kdHyeok/NMP/blob/main/docs/plugin-distribution.md
소스: https://github.com/kdHyeok/NMP

개인 ZIP의 `.app.json`은 생성 명령에 사용자가 지정한 연결을 참조한다.
빌더의 형식 검사는 연결의 소유권이나 서버 실행 상태를 확인하지 않는다. 설치할 ChatGPT 계정에서 직접 확인해야 한다.
개인 ZIP을 GitHub에 올리거나 다른 사용자에게 배포하지 않는다. 각 사용자가 자기 연결로 생성한다.
서버 비밀번호·API 키와 암호화 설정은 패키지에 포함하지 않는다.

로고 표시 제한 (2026-10-27): NMP 원본 로고 PNG와 공식 logo·composerIcon 설정이 포함되지만,
검사한 ChatGPT 웹 화면은 기본 아이콘을 표시했다. 파일 포함과 화면 표시 성공은 별개이며,
이 버전은 ChatGPT 로고 표시 문제를 해결했다고 보장하지 않는다. 상세 내용은 위 설치 문서를 참고한다.

원본 서버: https://github.com/chanmuzi/naver-mail-mcp (MIT).
