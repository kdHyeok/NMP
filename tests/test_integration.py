"""Integration tests for Naver Mail MCP Server.

Run with: python -m tests.test_integration
Set NMP_CONFIG_DIR to the encrypted config directory, or use legacy environment variables.
"""

from __future__ import annotations

import os
import sys
from unittest import SkipTest
from unittest.mock import patch

from naver_mail_mcp import imap_client


def get_creds():
    if not os.environ.get("NMP_CONFIG_DIR") and (not os.environ.get("NAVER_EMAIL_ADDRESS") or not (
        os.environ.get("NAVER_EMAIL_PASSWORD") or os.environ.get("NAVER_EMAIL_PASSWORD_FILE")
    )):
        raise SkipTest("Set NMP_CONFIG_DIR or legacy Naver credentials to run live tests.")
    from naver_mail_mcp.server import _get_credentials
    return _get_credentials()


def test_get_profile():
    email, password, full_name = get_creds()
    with imap_client.imap_connection(email, password) as conn:
        profile = imap_client.get_profile(conn, email, full_name)
    print(f"  email: {profile.email}")
    print(f"  full_name: {profile.full_name}")
    print(f"  total_messages: {profile.total_messages}")
    print(f"  unseen_messages: {profile.unseen_messages}")
    assert profile.total_messages >= 0
    return True


def test_list_folders():
    email, password, _ = get_creds()
    with imap_client.imap_connection(email, password) as conn:
        folders = imap_client.list_folders(conn)
    for f in folders:
        print(f"  {f.name} (raw: {f.raw_name}) — {f.message_count} msgs, {f.unseen_count} unseen")
    assert len(folders) > 0
    return True


def test_search_emails():
    email, password, _ = get_creds()
    with imap_client.imap_connection(email, password) as conn:
        result = imap_client.search_emails(conn, folder="INBOX", page=1, page_size=5)
    print(f"  total: {result.total_count}, page: {result.page}, has_more: {result.has_more}")
    for e in result.emails:
        print(f"  [{e.uid}] {e.subject[:50]} — {e.from_address} ({e.date})")
    return True


def test_read_email():
    email, password, _ = get_creds()
    with imap_client.imap_connection(email, password) as conn:
        result = imap_client.search_emails(conn, folder="INBOX", page=1, page_size=1)
        if not result.emails:
            raise SkipTest("No emails in INBOX")
        uid = result.emails[0].uid
        mail = imap_client.read_email(conn, uid, "INBOX")
    print(f"  uid: {mail.uid}")
    print(f"  subject: {mail.subject}")
    print(f"  from: {mail.from_address}")
    print(f"  to: {mail.to_addresses}")
    print(f"  date: {mail.date}")
    print(f"  body_text length: {len(mail.body_text)}")
    print(f"  body_html length: {len(mail.body_html)}")
    print(f"  attachments: {len(mail.attachments)}")
    print(f"  message_id: {mail.message_id}")
    return True


def test_list_drafts():
    email, password, _ = get_creds()
    with imap_client.imap_connection(email, password) as conn:
        drafts = imap_client.list_drafts(conn)
    print(f"  {len(drafts)} drafts found")
    for d in drafts[:5]:
        print(f"  [{d.uid}] {d.subject[:50]}")
    return True


def test_read_thread():
    email, password, _ = get_creds()
    with imap_client.imap_connection(email, password) as conn:
        result = imap_client.search_emails(conn, folder="INBOX", page=1, page_size=1)
        if not result.emails:
            raise SkipTest("No emails in INBOX")
        uid = result.emails[0].uid
        mail = imap_client.read_email(conn, uid, "INBOX")
        if not mail.message_id:
            raise SkipTest("No Message-ID on first email")
        thread = imap_client.read_thread(conn, mail.message_id, "INBOX")
    print(f"  Thread has {len(thread)} emails")
    for t in thread:
        print(f"  [{t.uid}] {t.subject[:50]} — {t.date}")
    return True


def test_download_attachment():
    email, password, _ = get_creds()
    with imap_client.imap_connection(email, password) as conn:
        result = imap_client.search_emails(conn, folder="INBOX", page=1, page_size=20)
        for summary in result.emails:
            mail = imap_client.read_email(conn, summary.uid, "INBOX")
            if mail.attachments:
                att = mail.attachments[0]
                print(f"  Found attachment: {att.filename} ({att.content_type}, {att.size} bytes)")
                content = imap_client.download_attachment(conn, mail.uid, att.part_number, "INBOX")
                print(f"  Downloaded: {content.filename}, base64 length: {len(content.content_base64)}")
                return True
    raise SkipTest("No emails with attachments found in first 20 emails")


def test_missing_env_vars():
    """Check missing credentials independently of the configured live account."""
    with patch.dict(os.environ, NMP_CONFIG_DIR="", NAVER_EMAIL_ADDRESS="", NAVER_EMAIL_PASSWORD="", NAVER_EMAIL_PASSWORD_FILE=""):
        from naver_mail_mcp.server import _get_credentials
        try:
            _get_credentials()
            print("  FAIL: Should have raised ValueError")
            return False
        except ValueError as e:
            print(f"  Correct error: {e}")
            return True


def test_wrong_password():
    email, _, _ = get_creds()
    try:
        with imap_client.imap_connection(email, "wrong_password") as conn:
            pass
        print("  FAIL: Should have raised AuthenticationError")
        return False
    except imap_client.AuthenticationError as e:
        print(f"  Correct error: {e}")
        return True


ALL_TESTS = [
    ("get_profile", test_get_profile),
    ("list_folders", test_list_folders),
    ("search_emails", test_search_emails),
    ("read_email", test_read_email),
    ("read_thread", test_read_thread),
    ("list_drafts", test_list_drafts),
    ("download_attachment", test_download_attachment),
    ("missing_env_vars", test_missing_env_vars),
    ("wrong_password", test_wrong_password),
]


def run_tests(tests=ALL_TESTS) -> int:
    print("=" * 60)
    print("Naver Mail MCP Server — Integration Tests")
    print("=" * 60)

    passed = 0
    failed = 0
    skipped = 0

    for name, test_fn in tests:
        print(f"\n--- {name} ---")
        try:
            result = test_fn()
            if result:
                print(f"  RESULT: PASS")
                passed += 1
            else:
                print(f"  RESULT: FAIL")
                failed += 1
        except SkipTest as e:
            print(f"  RESULT: SKIP — {e}")
            skipped += 1
        except Exception as e:
            print(f"  RESULT: ERROR — {type(e).__name__}: {e}")
            failed += 1

    print(f"\n{'=' * 60}")
    print(f"Results: {passed} passed, {failed} failed, {skipped} skipped")
    print(f"{'=' * 60}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(run_tests())
