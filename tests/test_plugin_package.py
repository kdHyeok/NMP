"""Portable packages: no credentials or developer-specific connection in public ZIPs."""
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from naver_mail_mcp import cli, plugin_package as package


class PluginPackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def contents(self, path):
        with zipfile.ZipFile(path) as bundle:
            self.assertIsNone(bundle.testzip())
            result = {name: bundle.read(name) for name in bundle.namelist()}
            for info in bundle.infolist():
                self.assertFalse(info.filename.startswith(("/", "\\")))
                self.assertNotIn("..", Path(info.filename).parts)
                self.assertFalse(stat.S_ISLNK(info.external_attr >> 16))
        roots = {name.split("/")[0] for name in result}
        self.assertEqual(len(roots), 1)
        prefix = roots.pop() + "/"
        files = {name.removeprefix(prefix): data for name, data in result.items()}
        manifest = json.loads(files["plugin.json"])
        self.assertEqual(prefix, manifest["name"] + "/")
        self.assertEqual(manifest["$schema"], "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json")
        options = manifest["extensions"]["com.openai"]
        self.assertLessEqual(len(options["interface"]["shortDescription"]), 30)
        self.assertIn(options["onboardingSkill"].removeprefix("./"), files)
        for field in ("logo", "composerIcon"):
            self.assertIn(options["interface"][field].removeprefix("./"), files)
        self.assertTrue(files["assets/logo.png"].startswith(b"\x89PNG\r\n\x1a\n"))
        for name, data in files.items():
            if not name.startswith("assets/"):
                data.decode("utf-8")
            if name.endswith("SKILL.md"):
                # JSON frontmatter is a YAML 1.2 subset, parsed without another dependency.
                frontmatter = json.loads(data.decode().split("---", 2)[1])
                self.assertEqual(frontmatter["name"], Path(name).parent.name)
                self.assertTrue(frontmatter["description"])
        return files, manifest

    def test_public_package_has_only_onboarding_and_no_personal_binding(self):
        path = package.build_package(self.root / "setup.zip")
        files, manifest = self.contents(path)
        self.assertEqual(manifest["name"], "nmp-setup")
        self.assertEqual(set(files), {"plugin.json", "skills/setup/SKILL.md", "README.md", "LICENSE", "assets/logo.png"})
        self.assertNotIn("apps", manifest["extensions"]["com.openai"])
        self.assertNotIn(b"asdk_app_", b"".join(files.values()))
        original = path.read_bytes()
        package.build_package(path)
        self.assertEqual(path.read_bytes(), original)

    def test_private_package_contains_only_the_selected_app_and_both_skills(self):
        first = "asdk_app_" + "a" * 32
        second = "asdk_app_" + "b" * 32
        for selected in (first, second):
            with self.subTest(selected=selected):
                path = package.build_package(self.root / "private.zip", "https://chatgpt.com/plugins/plugin_" + selected + "?directoryTab=personal")
                files, manifest = self.contents(path)
                self.assertEqual(manifest["name"], "naver-mail-plugin")
                self.assertEqual(json.loads(files[".app.json"]), {"apps": {"naver-mail": {"id": selected}}})
                self.assertEqual(manifest["extensions"]["com.openai"]["apps"], "./.app.json")
                self.assertIn("skills/naver-mail/SKILL.md", files)
                self.assertNotIn((second if selected == first else first).encode(), b"".join(files.values()))

    def test_invalid_connection_never_overwrites_an_existing_package(self):
        target = self.root / "private.zip"
        target.write_bytes(b"keep-existing")
        for value in ("https://evil.example/plugins/plugin_asdk_app_a", "https://user:secret@chatgpt.com/plugins/plugin_asdk_app_a",
                      "https://chatgpt.com/plugins/plugin_asdk_app_a/extra", "tunnel_not_an_app", "connector_gmail", "asdk_app_a\nb"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                package.build_package(target, value)
        self.assertEqual(target.read_bytes(), b"keep-existing")

    def test_version_override_supports_host_updates_and_rejects_invalid_versions(self):
        path = package.build_package(self.root / "setup.zip", version="0.2.2")
        self.assertEqual(self.contents(path)[1]["version"], "0.2.2")
        before = path.read_bytes()
        for value in ("v0.2.2", "0.2", "01.2.3", "1.2.3\n", "../1.2.3"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                package.build_package(path, version=value)
        self.assertEqual(path.read_bytes(), before)

    def test_extra_files_and_credential_environment_are_never_packaged(self):
        resources = self.root / "resources"
        shutil.copytree(package.RESOURCES, resources)
        (resources / ".env").write_text("PRIVATE_CANARY_DO_NOT_EXPORT")
        with patch.object(package, "RESOURCES", resources), patch.dict(os.environ, NAVER_EMAIL_PASSWORD="PRIVATE_CANARY_DO_NOT_EXPORT", CONTROL_PLANE_API_KEY="PRIVATE_CANARY_DO_NOT_EXPORT"):
            files, _ = self.contents(package.build_package(self.root / "setup.zip"))
        self.assertNotIn(b"PRIVATE_CANARY_DO_NOT_EXPORT", b"".join(files.values()))

    @unittest.skipIf(os.name == "nt", "POSIX symlink fixture")
    def test_symlink_resource_is_rejected(self):
        resources = self.root / "resources"
        shutil.copytree(package.RESOURCES, resources)
        (resources / "LICENSE").unlink()
        (resources / "LICENSE").symlink_to(resources / "README.md")
        with patch.object(package, "RESOURCES", resources), self.assertRaises(ValueError):
            package.build_package(self.root / "setup.zip")
        self.assertFalse((self.root / "setup.zip").exists())

    def test_public_cli_never_reads_private_config(self):
        with patch.object(Path, "cwd", return_value=self.root), patch.object(cli, "load_config", side_effect=AssertionError("No credentials needed")), patch.object(sys, "argv", ["nmp", "package", "--public"]), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main(), 0)
        self.contents(self.root / "dist/nmp-setup.zip")

    def test_private_cli_requires_tunnel_config_and_generates_credential_free_zip(self):
        directory = self.root / ".nmp"
        directory.mkdir()
        settings = {"mode": "tunnel", "email": "offline@naver.com", "password": "dummy-password", "tunnel_key": "dummy-runtime-key"}
        argv = ["nmp", "--config-dir", str(directory), "package", "--connection", "asdk_app_" + "c" * 32]
        with patch.object(cli, "load_config", return_value=settings), patch.object(sys, "argv", argv), contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(cli.main(), 0)
        files, _ = self.contents(directory / "naver-mail-plugin.zip")
        for value in (settings["email"], settings["password"], settings["tunnel_key"]):
            self.assertNotIn(value, output.getvalue())
            self.assertNotIn(value.encode(), b"".join(files.values()))
        with patch.object(cli, "load_config", return_value={"mode": "local"}), patch.object(sys, "argv", argv), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(cli.main(), 1)
