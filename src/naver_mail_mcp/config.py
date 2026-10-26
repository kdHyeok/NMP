"""One account per installation; encrypted secrets never leave this machine."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import secrets
import stat
import subprocess

from cryptography.fernet import Fernet, InvalidToken

TUNNEL_ID = re.compile(r"tunnel_(?:[a-z0-9]{4}_)?[a-z0-9]{32}\Z")


def _regular(path: Path):
    info = path.lstat()
    if path.is_symlink() or getattr(info, "st_file_attributes", 0) & 0x400:
        raise ValueError("Configuration paths must not be symlinks or junctions")
    return info


def secure_directory(directory: Path):
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    info = _regular(directory)
    if not stat.S_ISDIR(info.st_mode):
        raise ValueError("Configuration path must be a directory")
    if os.name == "nt":
        result = subprocess.run(["whoami", "/user", "/fo", "csv", "/nh"], check=True, capture_output=True)
        match = re.search(rb"S-1-[0-9-]+", result.stdout)
        if not match:
            raise ValueError("Cannot identify the current Windows user")
        sid = match.group().decode("ascii")
        # Replace the DACL, including old explicit grants; new files inherit owner/SYSTEM only.
        literal = str(directory).replace("'", "''")
        script = ("$taskAcl=[System.Security.AccessControl.DirectorySecurity]::new();"
                  f"$taskAcl.SetSecurityDescriptorSddlForm('D:P(A;OICI;FA;;;{sid})(A;OICI;FA;;;SY)',[System.Security.AccessControl.AccessControlSections]::Access);"
                  f"[System.IO.Directory]::SetAccessControl('{literal}',$taskAcl)")
        subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script], check=True, capture_output=True)
    else:
        if os.getuid() != 0 and info.st_uid != os.getuid():
            raise ValueError("Configuration must belong to the current user")
        directory.chmod(0o700)


def private_read(path: Path, limit=65536) -> bytes:
    info = _regular(path)
    if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
        raise ValueError("Invalid configuration file")
    if os.name != "nt" and (stat.S_IMODE(info.st_mode) & 0o077 or (os.getuid() != 0 and info.st_uid != os.getuid())):
        raise ValueError("Secret files must be owned by the runtime user with mode 600 or 400")
    return path.read_bytes()


def private_write(path: Path, data: bytes):
    if path.exists() or path.is_symlink():
        _regular(path)
    temporary = path.with_name(path.name + "." + secrets.token_hex(8) + ".tmp")
    try:
        with os.fdopen(os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as target:
            target.write(data)
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def validate_config(config: dict):
    keys = {"email", "password", "name", "mode", "tunnel_id", "tunnel_key"}
    if set(config) != keys or any(not isinstance(value, str) for value in config.values()):
        raise ValueError("Invalid configuration fields")
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,100}@naver\.com", config["email"]):
        raise ValueError("Enter a Naver mail address ending in @naver.com")
    if not 8 <= len(config["password"]) <= 128 or any(not 33 <= ord(c) <= 126 for c in config["password"]):
        raise ValueError("Enter a valid Naver application password")
    if len(config["name"]) > 100 or any(ord(c) < 32 or ord(c) == 127 for c in config["name"]):
        raise ValueError("Invalid display name")
    if config["mode"] not in {"local", "tunnel", "server"}:
        raise ValueError("Choose local, tunnel or server")
    if config["mode"] != "local":
        if not TUNNEL_ID.fullmatch(config["tunnel_id"]):
            raise ValueError("Enter the actual OpenAI Tunnel ID")
        if not 10 <= len(config["tunnel_key"]) <= 4096 or any(not 33 <= ord(c) <= 126 for c in config["tunnel_key"]):
            raise ValueError("Enter the Tunnel runtime API key")
    elif config["tunnel_id"] or config["tunnel_key"]:
        raise ValueError("Local stdio does not need Tunnel credentials")


def save_config(directory: Path, config: dict, *, replace=False):
    validate_config(config)
    secure_directory(directory)
    target, key_path = directory / "config.enc", directory / "key"
    if target.exists() and not replace:
        raise ValueError("Already configured; use setup --replace to change credentials")
    if target.exists() and not key_path.exists():
        raise ValueError("Encryption key missing; restore it before changing configuration")
    if key_path.exists():
        key = private_read(key_path, 256)
        private_write(key_path, key)
    else:
        key = Fernet.generate_key()
        private_write(key_path, key)
    private_write(target, Fernet(key).encrypt(json.dumps(config, ensure_ascii=False).encode("utf-8")))


def load_config(directory: Path) -> dict:
    try:
        info = _regular(directory)
        if not stat.S_ISDIR(info.st_mode) or (os.name != "nt" and (
            stat.S_IMODE(info.st_mode) & 0o077 or (os.getuid() != 0 and info.st_uid != os.getuid())
        )):
            raise ValueError("Configuration directory must be private")
        config = json.loads(Fernet(private_read(directory / "key", 256)).decrypt(private_read(directory / "config.enc")))
        validate_config(config)
        return config
    except (OSError, ValueError, TypeError, InvalidToken):
        raise ValueError("Cannot load encrypted NMP configuration. Check its key, integrity and file permissions.") from None
