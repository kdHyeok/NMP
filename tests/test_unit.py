"""Offline regression tests. No Naver account or external network is used."""

import base64
import contextlib
import imaplib
import io
import json
import os
from pathlib import Path
import shutil
import ssl
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
from email.message import EmailMessage

from mcp import Client, MCPError, StdioServerParameters, types

from naver_mail_mcp import imap_client as ic, smtp_client as sc, server
from tests.test_integration import get_creds, run_tests


class OfflineIMAP(imaplib.IMAP4):
    """Exercise imaplib's real command serializer without opening a socket."""

    def __init__(self, search_results=None):
        self.state = "SELECTED"
        self.untagged_responses = {}
        self.is_readonly = True
        self.literal = None
        self._encoding = "ascii"
        self.debug = 0
        self.tagged_commands = {}
        self.tagnum = 0
        self.tagpre = b"A"
        self.sent = []
        self.search_results = iter(search_results or [b""])

    def _log(self, *args):
        pass

    def _get_response(self):
        return None

    def send(self, data):
        self.sent.append(data)

    def select(self, folder="INBOX", readonly=False):
        self._command("EXAMINE" if readonly else "SELECT", folder)
        return "OK", [b"0"]

    def uid(self, command, *args):
        self._command("UID", command, *args)
        return "OK", [next(self.search_results)]


def message_connection(raw):
    conn = Mock()
    conn.select.return_value = ("OK", [b"1"])
    conn.uid.side_effect = lambda command, uid, query: (
        ("OK", [f"1 (RFC822.SIZE {len(raw)})".encode()])
        if query == "(RFC822.SIZE)"
        else ("OK", [(b"1 (FLAGS (\\Seen) BODY[]<0> {100}", raw), b")"])
    )
    return conn


class MailTests(unittest.TestCase):
    def test_password_file_and_existing_environment_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            secret = Path(directory) / "password"
            secret.write_bytes(b"dummy-password\r\n")
            with patch.dict(os.environ, {"NAVER_EMAIL_ADDRESS": "user@naver.com", "NAVER_EMAIL_PASSWORD_FILE": str(secret)}, clear=True):
                self.assertEqual(server._get_credentials(), ("user@naver.com", "dummy-password", ""))
                self.assertEqual(get_creds(), ("user@naver.com", "dummy-password", ""))
            with patch.dict(os.environ, {"NAVER_EMAIL_ADDRESS": "user@naver.com", "NAVER_EMAIL_PASSWORD": "dummy", "NAVER_FULL_NAME": "User"}, clear=True):
                self.assertEqual(server._get_credentials(), ("user@naver.com", "dummy", "User"))

    def test_password_file_rejects_ambiguous_missing_and_empty_secrets(self):
        with tempfile.TemporaryDirectory() as directory:
            secret = Path(directory) / "password"
            env = {"NAVER_EMAIL_ADDRESS": "user@naver.com", "NAVER_EMAIL_PASSWORD_FILE": str(secret)}
            with patch.dict(os.environ, dict(env, NAVER_EMAIL_PASSWORD="dummy"), clear=True):
                with self.assertRaisesRegex(ValueError, "Set only one"):
                    server._get_credentials()
            with patch.dict(os.environ, env, clear=True):
                with self.assertRaisesRegex(ValueError, "Cannot read"):
                    server._get_credentials()
                secret.write_text("\n", encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "Missing required"):
                    server._get_credentials()
                secret.write_bytes(b"\xff")
                with self.assertRaisesRegex(ValueError, "Cannot read"):
                    server._get_credentials()

    def smtp(self, refused=None):
        smtp = Mock()
        smtp.__enter__ = Mock(return_value=smtp)
        smtp.__exit__ = Mock(return_value=False)
        smtp.send_message.return_value = refused or {}
        return smtp

    def test_imap_validates_server_certificate(self):
        with patch.object(ic.imaplib, "IMAP4_SSL") as factory:
            with ic.imap_connection("user@naver.com", "dummy"):
                pass
        ctx = factory.call_args.kwargs["ssl_context"]
        self.assertEqual(ctx.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(ctx.check_hostname)
        factory.return_value.logout.assert_called_once()

    def test_smtp_validates_certificate_and_reports_all_recipients(self):
        smtp = self.smtp()
        with patch.object(sc.smtplib, "SMTP_SSL", return_value=smtp) as factory:
            result = sc.send_email("user@naver.com", "dummy", "", ["to@example.com"], "test", "body", cc=["cc@example.com"])
        ctx = factory.call_args.kwargs["context"]
        self.assertEqual(ctx.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(ctx.check_hostname)
        self.assertTrue(result["success"])
        self.assertEqual(result["accepted_recipients"], ["to@example.com", "cc@example.com"])

    def test_partial_delivery_is_not_full_success(self):
        smtp = self.smtp({"bad@example.com": (550, b"No such user")})
        with patch.object(sc.smtplib, "SMTP_SSL", return_value=smtp):
            result = sc.send_email("user@naver.com", "dummy", "", ["ok@example.com", "bad@example.com"], "test", "body")
        self.assertFalse(result["success"])
        self.assertEqual(result["accepted_recipients"], ["ok@example.com"])
        self.assertEqual(result["refused_recipients"]["bad@example.com"]["code"], 550)
        smtp.send_message.assert_called_once()

    def test_invalid_recipients_never_open_smtp(self):
        with patch.object(sc.smtplib, "SMTP_SSL") as factory:
            for recipients in ([], ["not-an-email"], ["x@example.com\r\nBcc: y@example.com"]):
                with self.subTest(recipients=recipients), self.assertRaises(ValueError):
                    sc.send_email("user@naver.com", "dummy", "", recipients, "test", "body")
        factory.assert_not_called()

    def test_search_rejects_command_delimiters_in_all_filters(self):
        for field in ("sender", "recipient", "subject", "date_from", "date_to"):
            for value in ("x\r\nX999 NOOP", "x\x00", "x\x7f"):
                conn = Mock()
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    ic.search_emails(conn, **{field: value})
                conn.uid.assert_not_called()

    def test_search_quotes_spaces_quotes_and_backslashes(self):
        conn = OfflineIMAP()
        ic.search_emails(conn, subject='a "quoted" \\ term')
        self.assertIn(b'SUBJECT "a \\"quoted\\" \\\\ term"\r\n', conn.sent[-1])
        self.assertEqual(conn.sent[-1].count(b"\r\n"), 1)

    def test_korean_search_uses_real_utf8_literal(self):
        conn = OfflineIMAP()
        ic.search_emails(conn, subject="회의")
        self.assertIn(b"CHARSET UTF-8 ALL SUBJECT {6}\r\n", conn.sent[1])
        self.assertEqual(conn.sent[2], "회의".encode("utf-8"))
        self.assertIsNone(conn.literal)

    def test_multiple_korean_filters_are_intersected(self):
        conn = OfflineIMAP([b"1 2", b"2 3"])
        with patch.object(ic, "_fetch_email_summary", return_value=Mock()) as fetch:
            result = ic.search_emails(conn, sender="홍길동", subject="회의")
        self.assertEqual(result.total_count, 1)
        fetch.assert_called_once_with(conn, b"2")

    def test_failed_unicode_search_does_not_drop_filter(self):
        conn = Mock()
        conn.select.return_value = ("OK", [b"0"])
        conn.uid.return_value = ("NO", [b"BADCHARSET"])
        with self.assertRaises(ic.NaverIMAPError):
            ic.search_emails(conn, subject="회의")
        conn.uid.assert_called_once()
        self.assertIsNone(conn.literal)

    def test_folder_names_are_encoded_and_raw_names_still_work(self):
        name = "내게쓴메일함"
        raw = ic.encode_mutf7(name)
        for folder in (name, raw):
            conn = OfflineIMAP()
            ic.search_emails(conn, folder=folder)
            self.assertIn(('EXAMINE "' + raw + '"').encode("ascii"), conn.sent[0])

    def test_folder_backslash_is_escaped(self):
        self.assertEqual(ic._folder_arg("a\\b"), '"a\\\\b"')

    def test_search_dates_validate_calendar_and_format(self):
        self.assertEqual(ic._search_date("1-jan-2026"), "01-Jan-2026")
        for value in ("31-Feb-2026", "01-Foo-2026", "2026-01-01", "01-Jan-2026 ALL"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                ic._search_date(value)

    def test_uids_are_positive_ascii_integers(self):
        self.assertEqual(ic._sanitize_uid(" 12 "), "12")
        for value in ("", "0", "-1", "１２", "1:9", "1\r\nNOOP"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                ic._sanitize_uid(value)

    def test_invalid_date_does_not_break_summary(self):
        conn = Mock()
        conn.uid.return_value = ("OK", [(b"1 (FLAGS ())", b"Date: nonsense\r\nSubject: hello\r\n\r\n")])
        self.assertEqual(ic._fetch_email_summary(conn, b"1").date, "")

    def test_large_message_rejected_before_body_fetch_for_both_readers(self):
        for reader in (lambda c: ic.read_email(c, "1"), lambda c: ic.download_attachment(c, "1", "2")):
            conn = Mock()
            conn.select.return_value = ("OK", [b"1"])
            conn.uid.return_value = ("OK", [f"1 (RFC822.SIZE {ic.MAX_EMAIL_BYTES + 1})".encode()])
            with self.assertRaises(ic.NaverIMAPError):
                reader(conn)
            conn.uid.assert_called_once_with("FETCH", "1", "(RFC822.SIZE)")

    def test_read_and_attachment_roundtrip_use_bounded_peek(self):
        msg = EmailMessage()
        msg["Subject"] = "한글 첨부"
        msg["Date"] = "invalid"
        msg.set_content("본문")
        msg.add_attachment(b"attachment bytes", maintype="application", subtype="octet-stream", filename="자료.bin")
        raw = msg.as_bytes()
        conn = message_connection(raw)
        mail = ic.read_email(conn, "1")
        self.assertEqual(mail.subject, "한글 첨부")
        self.assertEqual(mail.date, "")
        self.assertIn("본문", mail.body_text)
        self.assertEqual(mail.flags, ["\\Seen"])
        self.assertEqual(len(mail.attachments), 1)
        attachment = ic.download_attachment(conn, "1", mail.attachments[0].part_number)
        self.assertEqual(base64.b64decode(attachment.content_base64), b"attachment bytes")
        queries = [call.args[2] for call in conn.uid.call_args_list]
        self.assertTrue(all(q == "(RFC822.SIZE)" or "BODY.PEEK[]<0." in q for q in queries))

    def test_message_growing_during_fetch_is_rejected(self):
        conn = Mock()
        conn.uid.side_effect = [("OK", [b"1 (RFC822.SIZE 5)"]), ("OK", [(b"1 (FLAGS ())", b"123456789")])]
        with patch.object(ic, "MAX_EMAIL_BYTES", 8), self.assertRaises(ic.NaverIMAPError):
            ic._fetch_message(conn, "1")

    def test_missing_size_and_incomplete_download_are_rejected(self):
        conn = Mock()
        conn.uid.return_value = ("OK", [b"1 ()"])
        with self.assertRaises(ic.NaverIMAPError):
            ic._fetch_message(conn, "1")
        conn.uid.side_effect = [("OK", [b"1 (RFC822.SIZE 6)"]), ("OK", [(b"1 (FLAGS ())", b"short")])]
        with self.assertRaises(ic.NaverIMAPError):
            ic._fetch_message(conn, "1")

    def test_attachment_size_limit(self):
        msg = EmailMessage()
        msg.set_content("body")
        msg.add_attachment(b"12345", maintype="application", subtype="octet-stream", filename="big.bin")
        with patch.object(ic, "MAX_ATTACHMENT_BYTES", 4), self.assertRaises(ic.NaverIMAPError):
            ic.download_attachment(message_connection(msg.as_bytes()), "1", "3")

    def test_json_response_budget_includes_escaping(self):
        with self.assertRaises(ValueError):
            server._json_result("\\" * (3 * 1024 * 1024))
        payload = {"content_base64": base64.b64encode(b"x" * ic.MAX_ATTACHMENT_BYTES).decode("ascii")}
        text = server._json_result(payload)
        self.assertLess(len(json.dumps({"content": [{"type": "text", "text": text}]}).encode()), 10 * 1024 * 1024)

    def test_live_runner_counts_skip_and_returns_failure(self):
        def skip():
            raise unittest.SkipTest("no fixture")
        def error():
            raise RuntimeError("test error")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            result = run_tests([("pass", lambda: True), ("skip", skip), ("fail", lambda: False), ("error", error)])
        self.assertEqual(result, 1)
        self.assertIn("1 passed, 2 failed, 1 skipped", out.getvalue())

    def test_missing_credentials_fail_before_server_start(self):
        env = dict(os.environ, NAVER_EMAIL_ADDRESS="", NAVER_EMAIL_PASSWORD="", NAVER_EMAIL_PASSWORD_FILE="")
        result = subprocess.run([sys.executable, "-m", "naver_mail_mcp.server"], env=env, capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 1)
        self.assertIn(b"Missing required environment variables", result.stderr)

    @unittest.skipUnless(os.name == "nt", "Windows PowerShell launcher")
    def test_launcher_restores_environment_and_stops_after_failed_doctor(self):
        shell = shutil.which("pwsh") or shutil.which("powershell")
        if not shell:
            self.skipTest("PowerShell not installed")
        script = Path(__file__).with_name("test_launcher.ps1")
        result = subprocess.run([shell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)], capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", errors="replace"))


class MCPTests(unittest.IsolatedAsyncioTestCase):
    async def test_annotations_and_context_schema(self):
        tools = {tool.name: tool for tool in await server.mcp.list_tools()}
        self.assertEqual(len(tools), 9)
        for name, tool in tools.items():
            self.assertEqual(tool.annotations.read_only_hint, name not in {"send_email", "create_draft"})
            self.assertEqual(tool.annotations.destructive_hint, name == "send_email")
            self.assertEqual(tool.annotations.open_world_hint, name == "send_email")
            self.assertIsNone(tool.output_schema)
            self.assertIn("readOnlyHint", tool.annotations.model_dump(by_alias=True))
        properties = tools["send_email"].input_schema["properties"]
        self.assertNotIn("ctx", properties)
        self.assertNotIn("confirmation", properties)

    async def test_sending_requires_positive_confirmation(self):
        for mode in ("legacy", "auto"):
            for action, content in (("decline", None), ("cancel", None), ("accept", {"send": False})):
                async def answer(context, params):
                    return types.ElicitResult(action=action, content=content)
                with self.subTest(mode=mode, action=action), patch.object(server.smtp_client, "send_email") as send:
                    async with Client(server.mcp, mode=mode, elicitation_callback=answer) as client:
                        result = await client.call_tool("send_email", {"to": ["to@example.com"], "subject": "subject", "body": "body"})
                    self.assertFalse(result.is_error)
                    self.assertFalse(json.loads(result.content[0].text)["success"])
                    send.assert_not_called()

    async def test_unsupported_confirmation_never_sends(self):
        for mode in ("legacy", "auto"):
            with self.subTest(mode=mode), patch.object(server.smtp_client, "send_email") as send:
                async with Client(server.mcp, mode=mode) as client:
                    with self.assertRaises(MCPError) as raised:
                        await client.call_tool("send_email", {"to": ["to@example.com"], "subject": "subject", "body": "body"})
                self.assertEqual(raised.exception.code, -32021)
                self.assertIn("elicitation", raised.exception.message.lower())
                send.assert_not_called()

    async def test_confirmed_message_is_sent_once_with_exact_preview(self):
        for mode in ("legacy", "auto"):
            prompts = []
            async def approve(context, params):
                prompts.append(params.message)
                return types.ElicitResult(action="accept", content={"send": True})
            with self.subTest(mode=mode), patch.object(server, "_get_credentials", return_value=("user@naver.com", "dummy", "")), patch.object(server.smtp_client, "send_email", return_value={"success": True}) as send:
                async with Client(server.mcp, mode=mode, elicitation_callback=approve) as client:
                    if mode == "auto":
                        self.assertGreaterEqual(client.protocol_version, "2026-07-28")
                    result = await client.call_tool("send_email", {"to": ["to@example.com"], "subject": "subject", "body": "exact body", "cc": ["cc@example.com"]})
                self.assertFalse(result.is_error)
                self.assertTrue(json.loads(result.content[0].text)["success"])
                send.assert_called_once()
                self.assertEqual(send.call_args.args[3:6], (["to@example.com"], "subject", "exact body"))
                self.assertEqual(len(prompts), 1)
                self.assertIn('"cc": ["cc@example.com"]', prompts[0])
                self.assertIn('"body": "exact body"', prompts[0])

    async def test_confirmation_cannot_be_supplied_by_the_model(self):
        async def decline(context, params):
            return types.ElicitResult(action="decline")
        for mode in ("legacy", "auto"):
            with self.subTest(mode=mode), patch.object(server.smtp_client, "send_email") as send:
                async with Client(server.mcp, mode=mode, elicitation_callback=decline) as client:
                    result = await client.call_tool("send_email", {
                        "to": ["to@example.com"], "subject": "subject", "body": "body",
                        "confirmation": {"action": "accept", "data": {"send": True}},
                    })
                self.assertFalse(result.is_error)
                self.assertFalse(json.loads(result.content[0].text)["success"])
                send.assert_not_called()

    async def test_confirmation_is_not_reused_after_recipient_changes(self):
        async def decline(context, params):
            return types.ElicitResult(action="decline")
        arguments = {"to": ["original@example.com"], "subject": "subject", "body": "body"}
        with patch.object(server.smtp_client, "send_email") as send:
            async with Client(server.mcp, elicitation_callback=decline) as client:
                question = await client.session.call_tool("send_email", arguments, allow_input_required=True)
                self.assertIsInstance(question, types.InputRequiredResult)
                send.assert_not_called()
                changed_arguments = dict(arguments, to=["changed@example.com"])
                with self.assertRaises(MCPError) as raised:
                    await client.session.call_tool(
                        "send_email", changed_arguments,
                        input_responses={key: types.ElicitResult(action="accept", content={"send": True}) for key in question.input_requests},
                        request_state=question.request_state,
                        allow_input_required=True,
                    )
                self.assertEqual(raised.exception.message, "Invalid or expired requestState")
                send.assert_not_called()

    async def test_real_stdio_discovery_and_cancelled_send(self):
        async def decline(context, params):
            self.assertIn("body", params.message)
            return types.ElicitResult(action="decline")
        params = StdioServerParameters(
            command=sys.executable,
            args=["-B", "-m", "naver_mail_mcp.server"],
            cwd=str(Path(__file__).resolve().parents[1]),
            env={"NAVER_EMAIL_ADDRESS": "offline@example.com", "NAVER_EMAIL_PASSWORD": "dummy-not-a-password"},
        )
        for mode in ("legacy", "auto"):
            with self.subTest(mode=mode):
                async with Client(params, mode=mode, elicitation_callback=decline) as client:
                    if mode == "auto":
                        self.assertGreaterEqual(client.protocol_version, "2026-07-28")
                    tools = await client.list_tools()
                    self.assertEqual(len(tools.tools), 9)
                    result = await client.call_tool("send_email", {"to": ["to@example.com"], "subject": "offline test", "body": "body"})
                    self.assertFalse(result.is_error)
                    self.assertIsNone(result.structured_content)
                    self.assertFalse(json.loads(result.content[0].text)["success"])


if __name__ == "__main__":
    unittest.main()
