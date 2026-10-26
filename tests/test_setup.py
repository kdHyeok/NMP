"""Installer/runtime checks with dummy accounts; no external authentication."""
import asyncio
import contextlib
import getpass
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
import warnings
import zipfile

from cryptography.fernet import Fernet
from mcp import Client, StdioServerParameters, types
from naver_mail_mcp import cli, config, server

ROOT = Path(__file__).resolve().parents[1]


def sample(mode="local"):
    return {"email": "offline@naver.com", "password": "dummy-mail-password", "name": "테스트",
        "mode": mode, "tunnel_id": "tunnel_" + "0" * 32 if mode != "local" else "",
        "tunnel_key": "dummy-runtime-key" if mode != "local" else ""}


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name) / "한글 space's" / ".nmp"
        self.directory.parent.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def save(self, mode="local"):
        data = sample(mode)
        config.save_config(self.directory, data)
        return data

    def test_encrypted_roundtrip_and_private_files(self):
        data = self.save("tunnel")
        self.assertEqual(config.load_config(self.directory), data)
        for path in self.directory.iterdir():
            for field in ("email", "password", "tunnel_key"):
                self.assertNotIn(data[field].encode(), path.read_bytes())
            if os.name != "nt":
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        if os.name != "nt":
            self.assertEqual(stat.S_IMODE(self.directory.stat().st_mode), 0o700)

    def test_wrong_key_corrupt_or_missing_file_fail_closed(self):
        self.save()
        key = (self.directory / "key").read_bytes()
        config.private_write(self.directory / "key", Fernet.generate_key())
        with self.assertRaisesRegex(ValueError, "Cannot load"):
            config.load_config(self.directory)
        config.private_write(self.directory / "key", key)
        config.private_write(self.directory / "config.enc", b"damaged")
        with self.assertRaisesRegex(ValueError, "Cannot load"):
            config.load_config(self.directory)
        (self.directory / "key").unlink()
        with self.assertRaises(ValueError):
            config.save_config(self.directory, sample(), replace=True)

    def test_replace_requires_explicit_opt_in_and_preserves_key(self):
        self.save()
        key = (self.directory / "key").read_bytes()
        original = (self.directory / "config.enc").read_bytes()
        updated = dict(sample(), password="another-dummy-password")
        with self.assertRaisesRegex(ValueError, "Already configured"):
            config.save_config(self.directory, updated)
        self.assertEqual((self.directory / "config.enc").read_bytes(), original)
        config.save_config(self.directory, updated, replace=True)
        self.assertEqual((self.directory / "key").read_bytes(), key)
        self.assertEqual(config.load_config(self.directory), updated)

    @unittest.skipIf(os.name == "nt", "POSIX permissions and symlinks")
    def test_public_permissions_and_symlinks_rejected(self):
        self.save()
        self.directory.chmod(0o755)
        with self.assertRaises(ValueError):
            config.load_config(self.directory)
        self.directory.chmod(0o700)
        key = self.directory / "key"
        key.chmod(0o644)
        with self.assertRaises(ValueError):
            config.load_config(self.directory)
        key.unlink()
        other = self.directory / "other"
        other.write_bytes(Fernet.generate_key())
        key.symlink_to(other)
        with self.assertRaises(ValueError):
            config.load_config(self.directory)
        with self.assertRaises(ValueError):
            config.save_config(self.directory, sample(), replace=True)
        self.assertEqual(other.read_bytes(), key.read_bytes())

    @unittest.skipUnless(os.name == "nt", "Windows DACL")
    def test_windows_dacl_excludes_broad_groups(self):
        self.save()
        for path, kind in ((self.directory, "Directory"), (self.directory / "key", "File")):
            literal = str(path).replace("'", "''")
            script = f"[System.IO.{kind}]::GetAccessControl('{literal}').GetSecurityDescriptorSddlForm([System.Security.AccessControl.AccessControlSections]::Access)"
            result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script], capture_output=True, check=True, text=True)
            for group in ("WD", "BU", "AU", "BA"):
                self.assertNotIn(";;;" + group + ")", result.stdout)

    def test_invalid_input_is_rejected_before_writing(self):
        changes = [{"email": "bad\r\n@naver.com"}, {"password": "bad\npassword"}, {"name": "name\nheader"},
            {"mode": "public-http"}, {"mode": "tunnel", "tunnel_id": "bad", "tunnel_key": "dummy-runtime-key"}]
        for change in changes:
            with self.subTest(change=change), self.assertRaises(ValueError):
                config.save_config(self.directory, dict(sample(), **change))
        self.assertFalse(self.directory.exists())

    def test_configured_account_overrides_legacy_environment_and_never_falls_back(self):
        data = self.save()
        with patch.dict(os.environ, {"NMP_CONFIG_DIR": str(self.directory), "NAVER_EMAIL_ADDRESS": "other@naver.com", "NAVER_EMAIL_PASSWORD": "legacy-password"}):
            self.assertEqual(server._get_credentials(), (data["email"], data["password"], data["name"]))
            from tests.test_integration import test_missing_env_vars
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertTrue(test_missing_env_vars())
            self.assertEqual(os.environ["NMP_CONFIG_DIR"], str(self.directory))
            self.assertEqual(server._get_credentials(), (data["email"], data["password"], data["name"]))
            (self.directory / "key").unlink()
            with self.assertRaises(ValueError):
                server._get_credentials()

    def test_setup_generates_secret_free_client_config_and_rerun_preserves_secrets(self):
        data = sample("tunnel")
        out = io.StringIO()
        with patch("builtins.input", side_effect=[data["email"], data["name"], data["tunnel_id"]]), patch.object(cli.getpass, "getpass", side_effect=[data["password"], data["tunnel_key"]]), patch.object(cli, "ensure_tunnel", return_value="fake-client"), contextlib.redirect_stdout(out):
            cli.setup(self.directory, "tunnel")
        expected = config.load_config(self.directory)
        key = (self.directory / "key").read_bytes()
        with patch("builtins.input", side_effect=AssertionError("Must not prompt")), patch.object(cli, "ensure_tunnel"), contextlib.redirect_stdout(out):
            cli.setup(self.directory, "tunnel")
            cli.doctor(self.directory)
        self.assertEqual(config.load_config(self.directory), expected)
        self.assertEqual((self.directory / "key").read_bytes(), key)
        generated = json.loads((self.directory / "mcp.json").read_text(encoding="utf-8"))
        tool = generated["mcpServers"]["naver-mail"]
        self.assertEqual(tool["command"], str(Path(sys.executable).absolute()))
        self.assertEqual(tool["args"][-1], "stdio")
        for secret in (data["email"], data["password"], data["tunnel_key"]):
            self.assertNotIn(secret, out.getvalue())
            self.assertNotIn(secret, json.dumps(generated))

    def test_echoing_getpass_fallback_is_blocked(self):
        def fallback(*args):
            warnings.warn("no hidden input", getpass.GetPassWarning)
            return "must-not-be-read"
        with patch.object(cli.getpass, "getpass", side_effect=fallback):
            with self.assertRaises(getpass.GetPassWarning):
                cli._hidden("Password: ")

    def test_tunnel_passes_secrets_only_in_child_env_and_stops_after_failed_doctor(self):
        data = self.save("tunnel")
        before = dict(os.environ)
        out = io.StringIO()
        with patch.object(cli.subprocess, "run", return_value=Mock(returncode=0)) as run, contextlib.redirect_stdout(out):
            self.assertEqual(cli.tunnel(self.directory, client="fake-client"), 0)
        self.assertEqual([call.args[0][1] for call in run.call_args_list], ["doctor", "run"])
        for call in run.call_args_list:
            self.assertNotIn(data["tunnel_key"], repr(call.args))
            self.assertNotIn(data["password"], repr(call))
            self.assertEqual(call.kwargs["env"]["CONTROL_PLANE_API_KEY"], data["tunnel_key"])
            self.assertNotIn("NAVER_EMAIL_PASSWORD", call.kwargs["env"])
            self.assertIn("127.0.0.1:", repr(call.args))
        self.assertEqual(dict(os.environ), before)
        self.assertNotIn(data["tunnel_key"], out.getvalue())
        with patch.object(cli.subprocess, "run", return_value=Mock(returncode=7)) as run:
            self.assertEqual(cli.tunnel(self.directory, client="fake-client"), 7)
            self.assertEqual(run.call_count, 1)
        with patch.object(cli.subprocess, "run", return_value=Mock(returncode=0)) as run:
            self.assertEqual(cli.tunnel(self.directory, client="fake-client", check=True), 0)
            self.assertEqual(run.call_count, 1)

    def test_download_checks_checksum_and_extracts_only_known_basenames(self):
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w") as bundle:
            bundle.writestr("tunnel-client", b"dummy executable")
            bundle.writestr("../../escape", b"must not be extracted")
        data = payload.getvalue()
        archive = f"tunnel-client-v{cli.TUNNEL_VERSION}-linux-amd64.zip"
        checksum = hashlib.sha256(data).hexdigest().encode() + b"  " + archive.encode()
        def fetch(url, **kwargs):
            return io.BytesIO(checksum if url.endswith("SHA256SUMS.txt") else data)
        with patch.object(cli.shutil, "which", return_value=None), patch.object(cli.platform, "system", return_value="Linux"), patch.object(cli.platform, "machine", return_value="x86_64"), patch.object(cli.urllib.request, "urlopen", side_effect=fetch):
            path = Path(cli.ensure_tunnel(self.directory.parent))
        self.assertEqual(path.read_bytes(), b"dummy executable")
        self.assertFalse((self.directory.parent / "escape").exists())
        path.unlink()
        def corrupted(url, **kwargs):
            return io.BytesIO(b"0" * 64 + b"  " + archive.encode() if url.endswith("SHA256SUMS.txt") else data)
        with patch.object(cli.shutil, "which", return_value=None), patch.object(cli.platform, "system", return_value="Linux"), patch.object(cli.platform, "machine", return_value="x86_64"), patch.object(cli.urllib.request, "urlopen", side_effect=corrupted):
            with self.assertRaises(ValueError):
                cli.ensure_tunnel(self.directory.parent)
        self.assertFalse(path.exists())

    @unittest.skipUnless(sys.platform == "linux", "Linux server configuration")
    def test_server_configuration_uses_non_root_runtime_and_no_secret_environment(self):
        data = sample("server")
        with patch("builtins.input", side_effect=[data["email"], data["name"], data["tunnel_id"]]), patch.object(cli.getpass, "getpass", side_effect=[data["password"], data["tunnel_key"]]), contextlib.redirect_stdout(io.StringIO()):
            cli.setup(self.directory, "server")
        values = dict(line.split("=", 1) for line in (self.directory / "compose.env").read_text().splitlines())
        self.assertGreater(int(values["NMP_UID"]), 0)
        self.assertEqual(set(values), {"NMP_UID", "NMP_GID"})

    @unittest.skipUnless(os.name == "nt", "Windows installer entry point")
    def test_powershell_installer_preserves_argv_and_location(self):
        script = ROOT / "tests" / "test_install.ps1"
        result = subprocess.run([shutil.which("pwsh") or "powershell", "-NoProfile", "-File", str(script)], capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))

    @unittest.skipUnless(shutil.which("bash") and os.name != "nt", "POSIX installer entry point")
    def test_bash_installer_preserves_argv_and_stops_after_failure(self):
        scratch = Path(self.temp.name) / "installer space's"
        (scratch / "scripts").mkdir(parents=True)
        shutil.copyfile(ROOT / "scripts/install.sh", scratch / "scripts/install.sh")
        binary = scratch / "bin"
        binary.mkdir()
        shim = binary / "uv"
        shim.write_text('#!/usr/bin/env python3\nimport json,os,sys\nwith open(os.environ["NMP_INSTALL_LOG"],"a") as f: f.write(json.dumps(sys.argv[1:])+"\\n")\nsys.exit(9 if os.environ.get("NMP_INSTALL_FAIL") else 0)\n')
        shim.chmod(0o700)
        log = scratch / "log"
        env = dict(os.environ, PATH=str(binary) + os.pathsep + os.environ["PATH"], NMP_INSTALL_LOG=str(log))
        result = subprocess.run(["bash", str(scratch / "scripts/install.sh"), "local"], env=env, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = [json.loads(line) for line in log.read_text().splitlines()]
        self.assertEqual(calls[0], ["sync", "--frozen"])
        self.assertEqual(calls[1][-3:], ["setup", "--mode", "local"])
        log.write_text("")
        env["NMP_INSTALL_FAIL"] = "1"
        result = subprocess.run(["bash", str(scratch / "scripts/install.sh"), "local"], env=env, capture_output=True, timeout=30)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(log.read_text().splitlines()), 1)


class EncryptedStdioTests(unittest.IsolatedAsyncioTestCase):
    async def test_generated_configuration_discovers_tools_and_cancels_send(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "space 한글's" / ".nmp"
            data = sample()
            with patch("builtins.input", side_effect=[data["email"], data["name"]]), patch.object(cli.getpass, "getpass", return_value=data["password"]), contextlib.redirect_stdout(io.StringIO()):
                cli.setup(directory, "local")
            generated = json.loads((directory / "mcp.json").read_text(encoding="utf-8"))["mcpServers"]["naver-mail"]
            params = StdioServerParameters(command=generated["command"], args=generated["args"], cwd=str(ROOT))
            async def decline(context, request):
                return types.ElicitResult(action="decline")
            for mode in ("legacy", "auto"):
                async with Client(params, mode=mode, elicitation_callback=decline) as client:
                    self.assertEqual(len((await client.list_tools()).tools), 9)
                    result = await client.call_tool("send_email", {"to": ["to@example.com"], "subject": "test", "body": "body"})
                    self.assertFalse(result.is_error)
                    self.assertFalse(json.loads(result.content[0].text)["success"])
