"""Install and run a private stdio/OpenAI Tunnel instance of NMP."""
from __future__ import annotations

import argparse
import getpass
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import shlex
import shutil
import subprocess
import sys
import urllib.request
import warnings
import zipfile

from .config import TUNNEL_ID, load_config, private_write, save_config

TUNNEL_VERSION = "0.0.17"


def ensure_tunnel(root: Path) -> str:
    installed = shutil.which("tunnel-client")
    if installed:
        return installed
    system = {"Windows": "windows", "Linux": "linux", "Darwin": "darwin"}.get(platform.system())
    arch = {"AMD64": "amd64", "x86_64": "amd64", "arm64": "arm64", "aarch64": "arm64"}.get(platform.machine())
    if not system or not arch:
        raise ValueError("Install the official tunnel-client for this operating system manually")
    suffix = ".exe" if system == "windows" else ""
    directory = root / ".tools" / "tunnel-client"
    target = directory / ("tunnel-client" + suffix)
    if target.is_file():
        return str(target)
    archive = f"tunnel-client-v{TUNNEL_VERSION}-{system}-{arch}.zip"
    release = f"https://github.com/openai/tunnel-client/releases/download/v{TUNNEL_VERSION}"
    def fetch(name, limit):
        with urllib.request.urlopen(release + "/" + name, timeout=60) as response:
            data = response.read(limit + 1)
        if len(data) > limit:
            raise ValueError("Tunnel download exceeded its expected size")
        return data
    checksums = fetch("SHA256SUMS.txt", 65536).decode().splitlines()
    expected = [line.split()[0] for line in checksums if len(line.split()) == 2 and line.split()[1].lstrip("*") == archive]
    data = fetch(archive, 128 * 1024 * 1024)
    if len(expected) != 1 or hashlib.sha256(data).hexdigest() != expected[0]:
        raise ValueError("Tunnel archive checksum verification failed")
    directory.mkdir(parents=True, exist_ok=True)
    # Extract exact flat filenames only, never archive paths supplied by the ZIP.
    with zipfile.ZipFile(io.BytesIO(data)) as bundle:
        names = ["tunnel-client" + suffix, "cloudflared" + suffix, "LICENSE", "NOTICE"]
        for name in names:
            if name in bundle.namelist():
                destination = directory / name
                private_write(destination, bundle.read(name))
                destination.chmod(0o700 if name.endswith(suffix) and name not in {"LICENSE", "NOTICE"} else 0o600)
        if not target.is_file():
            raise ValueError("Tunnel archive did not contain the executable")
    return str(target)


def _hidden(prompt):
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        return getpass.getpass(prompt)


def setup(directory: Path, mode: str, replace=False):
    if mode == "server" and sys.platform != "linux":
        raise ValueError("Server mode requires Linux; use tunnel mode on Windows or macOS")
    if (directory / "config.enc").exists() and not replace:
        config = load_config(directory)
        if config["mode"] != mode:
            raise ValueError("Use setup --replace to change the installation mode")
        print("Existing encrypted configuration preserved.")
    else:
        print("Secrets stay on this machine. Do not paste them into ChatGPT.")
        config = {"mode": mode, "email": input("Naver mail address: ").strip(), "name": input("Display name (optional): ").strip(),
            "password": _hidden("Naver application password (hidden): "), "tunnel_id": "", "tunnel_key": ""}
        if mode != "local":
            print("Use a private Tunnel associated only with your own OpenAI account/workspace.")
            config["tunnel_id"] = input("OpenAI Tunnel ID: ").strip()
            config["tunnel_key"] = _hidden("OpenAI Tunnel runtime key (hidden): ")
        save_config(directory, config, replace=replace)
    client = {"mcpServers": {"naver-mail": {"command": str(Path(sys.executable).absolute()),
        "args": ["-B", "-m", "naver_mail_mcp.cli", "--config-dir", str(directory.resolve()), "stdio"]}}}
    private_write(directory / "mcp.json", (json.dumps(client, ensure_ascii=False, indent=2) + "\n").encode())
    if mode == "server":
        uid, gid = (10001, 10001) if os.getuid() == 0 else (os.getuid(), os.getgid())
        private_write(directory / "compose.env", f"NMP_UID={uid}\nNMP_GID={gid}\n".encode())
        if os.getuid() == 0:
            for path in directory.iterdir():
                if path.is_file():
                    os.chown(path, uid, gid)
            os.chown(directory, uid, gid)
    if mode == "tunnel":
        ensure_tunnel(directory.parent)
    info(directory, config)


def info(directory: Path, config=None):
    config = config or load_config(directory)
    print("Mode:", config["mode"])
    print("Local MCP configuration:", directory / "mcp.json")
    if config["mode"] != "local":
        print("ChatGPT connection: Tunnel")
        print("Tunnel ID:", config["tunnel_id"])
        print("Authentication: No authentication (private, single-owner Tunnel only)")
        print("Tunnel and custom MCP permissions are required in your OpenAI account.")
    print("No public MCP endpoint, domain or inbound port is created.")
    if config["mode"] != "local":
        print("After registering your own MCP connection: nmp package --connection <your ChatGPT plugin URL>")


def mcp_command(directory: Path) -> str:
    args = [str(Path(sys.executable).absolute()), "-B", "-m", "naver_mail_mcp.cli", "--config-dir", str(directory.resolve()), "stdio"]
    if os.name == "nt":
        return subprocess.list2cmdline([value.replace("\\", "/") for value in args])
    return shlex.join(args)


def tunnel(directory: Path, *, client=None, check=False) -> int:
    config = load_config(directory)
    if config["mode"] == "local" or not TUNNEL_ID.fullmatch(config["tunnel_id"]):
        raise ValueError("Configure tunnel or server mode first")
    executable = client or ensure_tunnel(directory.parent)
    value = os.environ.get("NMP_HEALTH_PORT", "0")
    if not value.isascii() or not value.isdecimal() or not 0 <= int(value) <= 65535:
        raise ValueError("Invalid health port")
    port = int(value)
    health_file = Path(os.environ.get("NMP_HEALTH_URL_FILE", str(directory / "health.url")))
    args = ["--control-plane.tunnel-id", config["tunnel_id"], "--control-plane.api-key", "env:CONTROL_PLANE_API_KEY",
        "--mcp.command", mcp_command(directory), "--mcp.max-concurrent-requests", "1",
        "--mcp.stdio-send-initialized-notification", "--health.listen-addr", f"127.0.0.1:{port}", "--health.url-file", str(health_file)]
    # Only the Tunnel child receives its decrypted key; Docker config and argv contain no key.
    environment = {key: value for key, value in os.environ.items() if not key.startswith("NAVER_")}
    environment.update(CONTROL_PLANE_API_KEY=config["tunnel_key"], PYTHONUTF8="1")
    result = subprocess.run([executable, "doctor", *args], env=environment)
    if result.returncode or check:
        return result.returncode
    print("Starting private Tunnel. Health URL file:", health_file, flush=True)
    try:
        return subprocess.run([executable, "run", *args], env=environment).returncode
    finally:
        health_file.unlink(missing_ok=True)


def doctor(directory: Path):
    load_config(directory)
    from . import server
    import asyncio
    tools = asyncio.run(server.mcp.list_tools())
    if len(tools) != 9:
        raise ValueError("Unexpected MCP tool registry")
    print("PASS: encrypted configuration and 9 stdio tools; POSIX permissions checked where applicable.")
    print("This offline check does not validate Naver login or OpenAI Tunnel access.")


def main():
    parser = argparse.ArgumentParser(description="Private Naver Mail MCP setup and runtime")
    parser.add_argument("--config-dir", type=Path, default=Path(os.environ.get("NMP_CONFIG_DIR", str(Path.cwd() / ".nmp"))))
    commands = parser.add_subparsers(dest="command", required=True)
    configure = commands.add_parser("setup", help="Configure one account using hidden secret prompts")
    configure.add_argument("--mode", choices=["local", "tunnel", "server"], default="local")
    configure.add_argument("--replace", action="store_true", help="Explicitly replace credentials, preserving the encryption key")
    commands.add_parser("info", help="Print connection settings without credentials")
    commands.add_parser("doctor", help="Check local configuration without external network calls")
    commands.add_parser("stdio", help="Run the configured stdio server")
    connect = commands.add_parser("tunnel", help="Run the private OpenAI Tunnel")
    connect.add_argument("--client", help="Path to an already installed official tunnel-client")
    connect.add_argument("--check", action="store_true", help="Run Tunnel doctor without starting the daemon")
    package = commands.add_parser("package", help="Build an installable ChatGPT plugin ZIP without credentials")
    kind = package.add_mutually_exclusive_group(required=True)
    kind.add_argument("--connection", help="Your registered NMP MCP plugin detail URL or asdk_app ID")
    kind.add_argument("--public", action="store_true", help="Build the connection-free onboarding ZIP for distribution")
    package.add_argument("--version", help="Use a higher major.minor.patch version when updating an installed plugin")
    args = parser.parse_args()
    directory = args.config_dir.absolute()
    try:
        if args.command == "setup":
            setup(directory, args.mode, args.replace)
        elif args.command == "info":
            info(directory)
        elif args.command == "doctor":
            doctor(directory)
        elif args.command == "tunnel":
            return tunnel(directory, client=args.client, check=args.check)
        elif args.command == "package":
            from .plugin_package import build_package
            if args.public:
                target = Path.cwd() / "dist" / "nmp-setup.zip"
            else:
                if load_config(directory)["mode"] == "local":
                    raise ValueError("Configure tunnel or server mode for web ChatGPT first")
                target = directory / "naver-mail-plugin.zip"
            print("Plugin ZIP:", build_package(target, args.connection, version=args.version))
            print("Upload in ChatGPT Plugins > + > Upload plugin archive.")
            if args.public:
                print("Setup guidance only; each user must generate their own connected ZIP.")
            else:
                print("Private package: use only in your own ChatGPT account. Do not publish this ZIP.")
        else:
            os.environ["NMP_CONFIG_DIR"] = str(directory)
            from .server import main as serve
            serve()
        return 0
    except ValueError as exc:
        print("NMP:", str(exc), file=sys.stderr)
        return 1
    except (OSError, EOFError, getpass.GetPassWarning, subprocess.CalledProcessError, zipfile.BadZipFile):
        print("NMP operation failed. Check permissions, network and prerequisites; secrets were not printed.", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
