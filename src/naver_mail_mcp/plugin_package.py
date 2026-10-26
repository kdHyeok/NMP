"""Build an onboarding ZIP or a private plugin bound to the user's MCP app."""
from __future__ import annotations

import io
import json
from pathlib import Path
import re
from urllib.parse import urlsplit
import zipfile

from .config import _regular, private_write

RESOURCES = Path(__file__).with_name("plugin")


def resource(name: str) -> bytes:
    path = RESOURCES
    for part in (".", *Path(name).parts):
        path = path / part
        _regular(path)
    if not path.is_file() or path.stat().st_size > 1024 * 1024:
        raise ValueError("Invalid plugin resource")
    return path.read_bytes()


def app_id(connection: str) -> str:
    value = connection.strip()
    if any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError("Invalid MCP connection identifier")
    if value.startswith("https://"):
        url = urlsplit(value)
        if url.netloc != "chatgpt.com" or not url.path.startswith("/plugins/"):
            raise ValueError("Use your own ChatGPT plugin detail URL")
        value = url.path.removeprefix("/plugins/").rstrip("/")
    # ChatGPT's plugin_asdk_app_<id> URL maps to asdk_app_<id> in .app.json.
    value = value.removeprefix("plugin_")
    if not re.fullmatch(r"asdk_app_[A-Za-z0-9][A-Za-z0-9_-]{0,119}", value):
        raise ValueError("Enter your own registered NMP MCP connection URL or asdk_app ID")
    return value


def build_package(destination: Path, connection: str | None = None, *, version: str | None = None) -> Path:
    if version is not None and not re.fullmatch(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)", version):
        raise ValueError("Use a plugin version in major.minor.patch format")
    bound_id = app_id(connection) if connection is not None else None
    manifest = json.loads(resource("plugin.json"))
    if version is not None:
        manifest["version"] = version
    options = manifest["extensions"]["com.openai"]
    files = {}
    if bound_id:
        options["apps"] = "./.app.json"
        files[".app.json"] = json.dumps({"apps": {"naver-mail": {"id": bound_id}}}).encode()
        files["skills/naver-mail/SKILL.md"] = resource("skills/naver-mail/SKILL.md")
    else:
        manifest["name"] = "nmp-setup"
        manifest["description"] = "Set up your own Naver Mail server and personal ChatGPT plugin."
        options["interface"]["displayName"] = "NMP 설치 도우미"
        options["interface"]["shortDescription"] = "개인 네이버 메일 연결 설치 안내"
        options["interface"]["longDescription"] = "NMP 서버 설치, 개인 Tunnel 설정, 본인 ChatGPT 연결과 개인용 ZIP 생성을 안내합니다. 이 설치 도우미 자체에는 메일 도구가 없습니다."
        options["interface"]["capabilities"] = []
        options["interface"]["defaultPrompt"] = "내 PC에 NMP를 설치하고 ChatGPT에 연결하는 순서를 안내해줘."
    files["plugin.json"] = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode()
    for name in ("skills/setup/SKILL.md", "README.md", "LICENSE", "assets/logo.png"):
        files[name] = resource(name)
    archive = io.BytesIO()
    # Only named package resources are included, never a checkout or credential directory.
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for name, data in sorted(files.items()):
            entry = zipfile.ZipInfo(manifest["name"] + "/" + name)
            entry.create_system = 3
            entry.external_attr = 0o100600 << 16
            entry.compress_type = zipfile.ZIP_DEFLATED
            bundle.writestr(entry, data)
    destination.parent.mkdir(parents=True, exist_ok=True)
    private_write(destination, archive.getvalue())
    return destination
