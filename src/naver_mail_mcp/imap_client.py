"""IMAP client for Naver Mail."""

from __future__ import annotations

import base64
import contextlib
import email
import email.header
import email.utils
import imaplib
import re
import ssl
from datetime import date
from typing import Generator

from .models import (
    AttachmentContent,
    AttachmentMeta,
    Email,
    EmailSummary,
    Folder,
    Profile,
    SearchResult,
)

IMAP_HOST = "imap.naver.com"
IMAP_PORT = 993
TIMEOUT = 30
MAX_PAGE_SIZE = 100
MAX_EMAIL_BYTES = 25 * 1024 * 1024
# Base64 and JSON must fit within Secure MCP Tunnel's 10 MiB response limit.
MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024
ALLOWED_BODY_TYPES = {"text/plain", "text/html"}


# --- Exceptions ---


class NaverIMAPError(Exception):
    """Base exception for Naver IMAP operations."""


class AuthenticationError(NaverIMAPError):
    """IMAP login failed."""


class NaverConnectionError(NaverIMAPError):
    """Cannot connect to Naver IMAP server."""


class FolderNotFoundError(NaverIMAPError):
    """Requested folder does not exist."""


class EmailNotFoundError(NaverIMAPError):
    """Email with specified UID not found."""


# --- Input Sanitization ---


def _sanitize_folder_name(folder: str) -> str:
    """Ensure folder name cannot break IMAP quoted-string syntax."""
    if not folder or '"' in folder or any(ord(c) < 32 or ord(c) == 127 for c in folder):
        raise ValueError("Invalid folder name: empty or contains prohibited characters.")
    return folder


def _sanitize_message_id(value: str) -> str:
    """Reject Message-IDs containing characters that could break IMAP search."""
    if not value or not value.isascii() or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError("Invalid Message-ID: contains prohibited characters.")
    return value


def _sanitize_uid(uid: str) -> str:
    """Ensure UID contains only digits."""
    if not re.fullmatch(r"[1-9][0-9]*", uid.strip()):
        raise ValueError(f"Invalid UID: must be a positive integer, got '{uid}'.")
    return uid.strip()


def _quote_imap(value: str) -> str:
    """Quote one IMAP string without allowing command delimiters."""
    if any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError("IMAP value contains prohibited control characters.")
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _folder_arg(folder: str) -> str:
    folder = _sanitize_folder_name(folder)
    return _quote_imap(encode_mutf7(folder) if not folder.isascii() else folder)


def _search_date(value: str) -> str:
    match = re.fullmatch(r"([0-9]{1,2})-([A-Za-z]{3})-([0-9]{4})", value)
    if not match:
        raise ValueError("Search dates must use DD-Mon-YYYY.")
    day, month, year = match.groups()
    months = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
    try:
        date(int(year), months.index(month.title()) + 1, int(day))
    except ValueError as exc:
        raise ValueError("Invalid search date.") from exc
    return f"{int(day):02d}-{month.title()}-{year}"


def _search_uids(conn: imaplib.IMAP4_SSL, *criteria: str, literal: str | None = None) -> list[bytes]:
    """Use a synchronizing literal for UTF-8 text, never drop a failed filter."""
    try:
        if literal is not None:
            conn.literal = literal.encode("utf-8")
            status, data = conn.uid("SEARCH", "CHARSET", "UTF-8", *criteria)
        else:
            status, data = conn.uid("SEARCH", *criteria)
    except imaplib.IMAP4.error as exc:
        raise NaverIMAPError("Search failed; the server may not support the requested charset.") from exc
    finally:
        conn.literal = None
    if status != "OK":
        raise NaverIMAPError("Search failed; filters were not changed or removed.")
    return data[0].split() if data and data[0] else []


def _sanitize_header_value(value: str) -> str:
    """Strip CRLF to prevent header injection."""
    if "\r" in value or "\n" in value:
        raise ValueError("Header value contains prohibited CRLF characters.")
    return value


def _validate_body_type(body_type: str) -> str:
    """Validate body_type against allowed values."""
    if body_type not in ALLOWED_BODY_TYPES:
        raise ValueError(f"body_type must be one of {ALLOWED_BODY_TYPES}, got '{body_type}'.")
    return body_type


def _validate_pagination(page: int, page_size: int) -> tuple[int, int]:
    """Validate pagination parameters."""
    if page < 1:
        raise ValueError("page must be >= 1.")
    if not (1 <= page_size <= MAX_PAGE_SIZE):
        raise ValueError(f"page_size must be between 1 and {MAX_PAGE_SIZE}.")
    return page, page_size


# --- Connection ---


@contextlib.contextmanager
def imap_connection(email_address: str, password: str) -> Generator[imaplib.IMAP4_SSL, None, None]:
    """Create an authenticated IMAP connection.

    The connection is automatically closed on exit.
    Login errors are caught separately from operation errors.
    """
    try:
        conn = imaplib.IMAP4_SSL(
            IMAP_HOST, IMAP_PORT, ssl_context=ssl.create_default_context(), timeout=TIMEOUT
        )
    except (OSError, imaplib.IMAP4.error) as e:
        raise NaverConnectionError(
            f"Cannot connect to Naver IMAP server ({IMAP_HOST}:{IMAP_PORT}). "
            f"Check your network connection. Error: {e}"
        ) from e

    try:
        conn.login(email_address, password)
    except imaplib.IMAP4.error as e:
        try:
            conn.logout()
        except Exception:
            pass
        raise AuthenticationError(
            "IMAP authentication failed. "
            "Check your Naver email address and app password."
        ) from e

    try:
        yield conn
    finally:
        try:
            conn.logout()
        except Exception:
            pass


# --- Encoding Utilities ---


def decode_header_value(raw: str | None) -> str:
    """Decode RFC 2047 encoded header value, handling Korean charsets."""
    if not raw:
        return ""
    decoded_parts = email.header.decode_header(raw)
    result = []
    for part, charset in decoded_parts:
        if isinstance(part, bytes):
            decoded = _decode_bytes(part, charset)
        else:
            decoded = part
        result.append(decoded)
    return "".join(result)


def _decode_bytes(data: bytes, charset: str | None = None) -> str:
    """Decode bytes with charset fallback chain: given → UTF-8 → EUC-KR → CP949 → latin-1."""
    charsets = []
    if charset:
        charsets.append(charset)
    charsets.extend(["utf-8", "euc-kr", "cp949", "latin-1"])

    for cs in charsets:
        try:
            return data.decode(cs)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("latin-1", errors="replace")


def decode_body(payload: bytes, charset: str | None) -> str:
    """Decode email body with charset fallback chain."""
    return _decode_bytes(payload, charset)


def encode_mutf7(text: str) -> str:
    """Encode a Unicode string to Modified UTF-7 for IMAP folder names."""
    result = []
    buf = ""
    for ch in text:
        if 0x20 <= ord(ch) <= 0x7E:
            if buf:
                encoded = buf.encode("utf-16-be")
                b64 = base64.b64encode(encoded).decode("ascii").rstrip("=")
                result.append("&" + b64.replace("/", ",") + "-")
                buf = ""
            if ch == "&":
                result.append("&-")
            else:
                result.append(ch)
        else:
            buf += ch
    if buf:
        encoded = buf.encode("utf-16-be")
        b64 = base64.b64encode(encoded).decode("ascii").rstrip("=")
        result.append("&" + b64.replace("/", ",") + "-")
    return "".join(result)


def decode_mutf7(data: str) -> str:
    """Decode Modified UTF-7 folder name to Unicode."""
    result = []
    i = 0
    while i < len(data):
        if data[i] == "&":
            j = data.index("-", i + 1)
            if j == i + 1:
                result.append("&")
            else:
                b64_str = data[i + 1 : j].replace(",", "/")
                padding = 4 - (len(b64_str) % 4)
                if padding != 4:
                    b64_str += "=" * padding
                decoded = base64.b64decode(b64_str).decode("utf-16-be")
                result.append(decoded)
            i = j + 1
        else:
            result.append(data[i])
            i += 1
    return "".join(result)


def _parse_date(date_str: str | None) -> str:
    """Parse email date to ISO 8601 string."""
    if not date_str:
        return ""
    try:
        return email.utils.parsedate_to_datetime(date_str).isoformat()
    except (ValueError, TypeError, OverflowError):
        return ""


def _parse_address(addr: str | None) -> str:
    """Parse and decode email address with display name."""
    if not addr:
        return ""
    return decode_header_value(addr)


def _parse_address_list(header: str | None) -> list[str]:
    """Parse comma-separated address list."""
    if not header:
        return []
    addresses = header.split(",")
    return [decode_header_value(a.strip()) for a in addresses if a.strip()]


# --- IMAP Operations ---
# All functions accept an authenticated IMAP connection as first parameter.


def get_profile(conn: imaplib.IMAP4_SSL, email_address: str, full_name: str) -> Profile:
    """Get account profile with mailbox statistics."""
    status, data = conn.select("INBOX", readonly=True)
    if status != "OK":
        raise NaverIMAPError("Failed to select INBOX.")

    total = int(data[0])

    status, data = conn.search(None, "UNSEEN")
    if status != "OK":
        raise NaverIMAPError("Failed to search for unseen messages.")

    unseen_uids = data[0].split()
    unseen = len(unseen_uids)

    return Profile(
        email=email_address,
        full_name=full_name,
        total_messages=total,
        unseen_messages=unseen,
    )


def list_folders(conn: imaplib.IMAP4_SSL) -> list[Folder]:
    """List all mailbox folders with message counts."""
    status, folder_data = conn.list()
    if status != "OK":
        raise NaverIMAPError("Failed to list folders.")

    folders = []
    for item in folder_data:
        if item is None:
            continue
        decoded_item = item.decode("utf-8") if isinstance(item, bytes) else item

        match = re.match(r'\((?P<flags>.*?)\)\s+"(?P<sep>.+?)"\s+"?(?P<name>.+?)"?$', decoded_item)
        if not match:
            match = re.match(r'\((?P<flags>.*?)\)\s+"(?P<sep>.+?)"\s+(?P<name>.+)$', decoded_item)
        if not match:
            continue

        raw_name = match.group("name").strip().strip('"')
        display_name = decode_mutf7(raw_name)
        flags = match.group("flags")

        msg_count = 0
        unseen_count = 0
        try:
            status, count_data = conn.status(_folder_arg(raw_name), "(MESSAGES UNSEEN)")
            if status == "OK" and count_data[0]:
                count_str = count_data[0].decode("utf-8") if isinstance(count_data[0], bytes) else count_data[0]
                msg_match = re.search(r"MESSAGES\s+(\d+)", count_str)
                unseen_match = re.search(r"UNSEEN\s+(\d+)", count_str)
                if msg_match:
                    msg_count = int(msg_match.group(1))
                if unseen_match:
                    unseen_count = int(unseen_match.group(1))
        except imaplib.IMAP4.error:
            pass

        folders.append(
            Folder(
                name=display_name,
                raw_name=raw_name,
                message_count=msg_count,
                unseen_count=unseen_count,
            )
        )

    return folders


def _find_folder_by_role(conn: imaplib.IMAP4_SSL, role: str, fallback_names: list[str]) -> str:
    """Find a folder by its special-use attribute or name matching.

    Args:
        conn: Authenticated IMAP connection.
        role: Special-use attribute to look for (e.g., '\\Drafts').
        fallback_names: List of folder names to try if attribute not found.

    Returns:
        The raw IMAP folder name.
    """
    status, folder_data = conn.list()
    if status != "OK":
        raise NaverIMAPError("Failed to list folders.")

    for item in folder_data:
        if item is None:
            continue
        decoded_item = item.decode("utf-8") if isinstance(item, bytes) else item

        match = re.match(r'\((?P<flags>.*?)\)\s+"(?P<sep>.+?)"\s+"?(?P<name>.+?)"?$', decoded_item)
        if not match:
            match = re.match(r'\((?P<flags>.*?)\)\s+"(?P<sep>.+?)"\s+(?P<name>.+)$', decoded_item)
        if not match:
            continue

        flags = match.group("flags")
        if role.lower() in flags.lower():
            return match.group("name").strip().strip('"')

    for item in folder_data:
        if item is None:
            continue
        decoded_item = item.decode("utf-8") if isinstance(item, bytes) else item

        match = re.match(r'\((?P<flags>.*?)\)\s+"(?P<sep>.+?)"\s+"?(?P<name>.+?)"?$', decoded_item)
        if not match:
            match = re.match(r'\((?P<flags>.*?)\)\s+"(?P<sep>.+?)"\s+(?P<name>.+)$', decoded_item)
        if not match:
            continue

        raw_name = match.group("name").strip().strip('"')
        display_name = decode_mutf7(raw_name)

        for name in fallback_names:
            if display_name.lower() == name.lower() or raw_name.lower() == name.lower():
                return raw_name

    raise FolderNotFoundError(
        f"Could not find folder with role '{role}'. "
        f"Tried names: {fallback_names}. Use list_folders to see available folders."
    )


def _find_drafts_folder(conn: imaplib.IMAP4_SSL) -> str:
    """Find the Drafts folder."""
    return _find_folder_by_role(conn, "\\Drafts", ["Drafts", "임시보관함", "&BCIENA0RBBQ-"])


def _find_sent_folder(conn: imaplib.IMAP4_SSL) -> str:
    """Find the Sent folder."""
    return _find_folder_by_role(conn, "\\Sent", ["Sent Messages", "Sent", "보낸메일함"])


def search_emails(
    conn: imaplib.IMAP4_SSL,
    folder: str = "INBOX",
    sender: str | None = None,
    recipient: str | None = None,
    subject: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    is_read: bool | None = None,
    page: int = 1,
    page_size: int = 20,
) -> SearchResult:
    """Search emails with filters and pagination."""
    page, page_size = _validate_pagination(page, page_size)
    criteria = []
    unicode_filters = []
    for key, value in (("FROM", sender), ("TO", recipient), ("SUBJECT", subject)):
        if value:
            quoted = _quote_imap(value)
            if value.isascii():
                criteria.extend([key, quoted])
            else:
                unicode_filters.append((key, value))
    if date_from:
        criteria.extend(["SINCE", _search_date(date_from)])
    if date_to:
        criteria.extend(["BEFORE", _search_date(date_to)])
    if is_read is True:
        criteria.append("SEEN")
    elif is_read is False:
        criteria.append("UNSEEN")

    if not criteria:
        criteria.append("ALL")

    status, _ = conn.select(_folder_arg(folder), readonly=True)
    if status != "OK":
        raise FolderNotFoundError(f"Folder '{folder}' not found. Use list_folders to see available folders.")

    if unicode_filters:
        key, value = unicode_filters[0]
        uid_list = _search_uids(conn, *criteria, key, literal=value)
        for key, value in unicode_filters[1:]:
            matching = set(_search_uids(conn, key, literal=value))
            uid_list = [uid for uid in uid_list if uid in matching]
    else:
        uid_list = _search_uids(conn, *criteria)
    uid_list.reverse()

    total_count = len(uid_list)
    start = (page - 1) * page_size
    end = start + page_size
    page_uids = uid_list[start:end]

    emails = []
    for uid in page_uids:
        summary = _fetch_email_summary(conn, uid)
        if summary:
            emails.append(summary)

    return SearchResult(
        emails=emails,
        total_count=total_count,
        page=page,
        page_size=page_size,
        has_more=end < total_count,
    )


def _fetch_email_summary(conn: imaplib.IMAP4_SSL, uid: bytes) -> EmailSummary | None:
    """Fetch summary data for a single email by UID."""
    status, data = conn.uid("FETCH", uid, "(FLAGS BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
    if status != "OK" or not data or data[0] is None:
        return None

    flags_str = ""
    header_data = b""
    for part in data:
        if isinstance(part, tuple):
            meta = part[0].decode("utf-8", errors="replace") if isinstance(part[0], bytes) else part[0]
            if "FLAGS" in meta:
                flags_match = re.search(r"FLAGS \(([^)]*)\)", meta)
                if flags_match:
                    flags_str = flags_match.group(1)
            header_data = part[1] if isinstance(part[1], bytes) else part[1].encode()

    msg = email.message_from_bytes(header_data)
    subject = decode_header_value(msg.get("Subject"))
    from_addr = _parse_address(msg.get("From"))
    date_str = _parse_date(msg.get("Date"))
    is_read = "\\Seen" in flags_str

    return EmailSummary(
        uid=uid.decode("utf-8") if isinstance(uid, bytes) else str(uid),
        subject=subject,
        from_address=from_addr,
        date=date_str,
        is_read=is_read,
        has_attachments=False,
    )


def _fetch_message(conn: imaplib.IMAP4_SSL, uid: str) -> tuple[str, bytes]:
    """Check the size before downloading and bound the fetch even if it changes."""
    status, data = conn.uid("FETCH", uid, "(RFC822.SIZE)")
    if status != "OK" or not data or data[0] is None:
        raise EmailNotFoundError(f"Email with UID '{uid}' not found.")
    meta = b" ".join(part for part in data if isinstance(part, bytes))
    match = re.search(rb"RFC822.SIZE\s+(\d+)", meta)
    if not match:
        raise NaverIMAPError("The server did not return the email size.")
    size = int(match.group(1))
    if size > MAX_EMAIL_BYTES:
        raise NaverIMAPError(f"Email exceeds the {MAX_EMAIL_BYTES:,}-byte download limit.")

    # shortcut: fetch the whole message up to 25 MiB; use BODYSTRUCTURE for larger mail.
    status, data = conn.uid("FETCH", uid, f"(FLAGS BODY.PEEK[]<0.{MAX_EMAIL_BYTES + 1}>)")
    if status != "OK" or not data or data[0] is None:
        raise EmailNotFoundError(f"Email with UID '{uid}' not found.")

    flags_str = ""
    raw_email = b""
    for part in data:
        if isinstance(part, tuple):
            meta = part[0].decode("utf-8", errors="replace") if isinstance(part[0], bytes) else part[0]
            flags_match = re.search(r"FLAGS \(([^)]*)\)", meta)
            if flags_match:
                flags_str = flags_match.group(1)
            raw_email = part[1] if isinstance(part[1], bytes) else part[1].encode()

    if len(raw_email) > MAX_EMAIL_BYTES:
        raise NaverIMAPError("Email exceeded the download limit during fetch.")
    if len(raw_email) != size:
        raise NaverIMAPError("The server returned an incomplete email; retry the read.")
    return flags_str, raw_email


def read_email(conn: imaplib.IMAP4_SSL, uid: str, folder: str = "INBOX") -> Email:
    """Read a full email by UID without changing its read status."""
    uid = _sanitize_uid(uid)
    status, _ = conn.select(_folder_arg(folder), readonly=True)
    if status != "OK":
        raise FolderNotFoundError(f"Folder '{folder}' not found. Use list_folders to see available folders.")
    flags_str, raw_email = _fetch_message(conn, uid)
    msg = email.message_from_bytes(raw_email)

    subject = decode_header_value(msg.get("Subject"))
    from_addr = _parse_address(msg.get("From"))
    to_addrs = _parse_address_list(msg.get("To"))
    cc_addrs = _parse_address_list(msg.get("Cc"))
    date_str = _parse_date(msg.get("Date"))
    message_id = msg.get("Message-ID", "")
    in_reply_to = msg.get("In-Reply-To", "")
    refs = msg.get("References", "")
    references = refs.split() if refs else []
    flags = flags_str.split() if flags_str else []

    body_text = ""
    body_html = ""
    attachments = []
    part_counter = 0

    for part in msg.walk():
        content_type = part.get_content_type()
        content_disposition = str(part.get("Content-Disposition", ""))
        part_counter += 1

        if "attachment" in content_disposition:
            filename = part.get_filename()
            if filename:
                filename = decode_header_value(filename)
            else:
                filename = f"attachment_{part_counter}"

            payload = part.get_payload(decode=True)
            size = len(payload) if payload else 0

            attachments.append(
                AttachmentMeta(
                    filename=filename,
                    content_type=content_type,
                    size=size,
                    part_number=str(part_counter),
                )
            )
        elif content_type == "text/plain" and not body_text:
            payload = part.get_payload(decode=True)
            if payload:
                charset = part.get_content_charset()
                body_text = decode_body(payload, charset)
        elif content_type == "text/html" and not body_html:
            payload = part.get_payload(decode=True)
            if payload:
                charset = part.get_content_charset()
                body_html = decode_body(payload, charset)

    return Email(
        uid=uid,
        message_id=message_id,
        subject=subject,
        from_address=from_addr,
        to_addresses=to_addrs,
        cc_addresses=cc_addrs,
        date=date_str,
        body_text=body_text,
        body_html=body_html,
        flags=flags,
        references=references,
        in_reply_to=in_reply_to,
        attachments=attachments,
    )


def read_thread(conn: imaplib.IMAP4_SSL, message_id: str, folder: str = "INBOX") -> list[Email]:
    """Read an email thread by Message-ID.

    Finds all related emails via References and In-Reply-To headers.
    All operations use a single connection.
    """
    message_id = _sanitize_message_id(message_id)
    status, _ = conn.select(_folder_arg(folder), readonly=True)
    if status != "OK":
        raise FolderNotFoundError(f"Folder '{folder}' not found.")

    target_uid = None
    status, data = conn.uid("SEARCH", None, "HEADER", "Message-ID", _quote_imap(message_id))
    if status == "OK" and data[0]:
        uids = data[0].split()
        if uids:
            target_uid = uids[0]

    all_message_ids = {message_id}

    if target_uid:
        status, data = conn.uid("FETCH", target_uid, "(BODY.PEEK[HEADER.FIELDS (REFERENCES IN-REPLY-TO)])")
        if status == "OK" and data and data[0] is not None:
            for part in data:
                if isinstance(part, tuple) and len(part) > 1:
                    header_data = part[1] if isinstance(part[1], bytes) else part[1].encode()
                    msg = email.message_from_bytes(header_data)
                    refs = msg.get("References", "")
                    if refs:
                        all_message_ids.update(refs.split())
                    irt = msg.get("In-Reply-To", "")
                    if irt:
                        all_message_ids.add(irt.strip())

    all_uids = set()
    for mid in all_message_ids:
        try:
            safe_mid = _quote_imap(_sanitize_message_id(mid.strip()))
        except ValueError:
            continue
        try:
            status, data = conn.uid("SEARCH", None, "HEADER", "Message-ID", safe_mid)
            if status == "OK" and data[0]:
                all_uids.update(data[0].split())
        except imaplib.IMAP4.error:
            continue

        try:
            status, data = conn.uid("SEARCH", None, "HEADER", "References", safe_mid)
            if status == "OK" and data[0]:
                all_uids.update(data[0].split())
        except imaplib.IMAP4.error:
            continue

        try:
            status, data = conn.uid("SEARCH", None, "HEADER", "In-Reply-To", safe_mid)
            if status == "OK" and data[0]:
                all_uids.update(data[0].split())
        except imaplib.IMAP4.error:
            continue

    thread_emails = []
    for uid in all_uids:
        uid_str = uid.decode("utf-8") if isinstance(uid, bytes) else str(uid)
        try:
            mail = read_email(conn, uid_str, folder)
            thread_emails.append(mail)
        except EmailNotFoundError:
            continue

    thread_emails.sort(key=lambda e: e.date)
    return thread_emails


def list_drafts(conn: imaplib.IMAP4_SSL) -> list[EmailSummary]:
    """List all drafts in the Drafts folder."""
    drafts_folder = _find_drafts_folder(conn)

    status, _ = conn.select(_folder_arg(drafts_folder), readonly=True)
    if status != "OK":
        raise FolderNotFoundError("Could not select Drafts folder.")

    status, data = conn.uid("SEARCH", None, "ALL")
    if status != "OK":
        return []

    uid_list = data[0].split() if data[0] else []
    uid_list.reverse()

    drafts = []
    for uid in uid_list:
        summary = _fetch_email_summary(conn, uid)
        if summary:
            drafts.append(summary)

    return drafts


def create_draft(
    conn: imaplib.IMAP4_SSL,
    email_address: str,
    full_name: str,
    to: list[str],
    subject: str,
    body: str,
    body_type: str = "text/plain",
    cc: list[str] | None = None,
) -> dict:
    """Save an email draft to the Drafts folder."""
    body_type = _validate_body_type(body_type)
    drafts_folder = _find_drafts_folder(conn)

    msg = email.message.EmailMessage()
    if full_name:
        safe_name = _sanitize_header_value(full_name.strip())
        msg["From"] = f"{safe_name} <{email_address}>"
    else:
        msg["From"] = email_address
    msg["To"] = ", ".join(to)
    msg["Subject"] = subject
    if cc:
        msg["Cc"] = ", ".join(cc)

    if body_type == "text/html":
        msg.set_content(body, subtype="html", charset="utf-8")
    else:
        msg.set_content(body, charset="utf-8")

    raw_msg = msg.as_bytes()

    status, _ = conn.append(
        _folder_arg(drafts_folder),
        "\\Draft",
        None,
        raw_msg,
    )

    if status != "OK":
        raise NaverIMAPError("Failed to save draft.")

    return {"success": True, "message": "Draft saved successfully."}


def download_attachment(
    conn: imaplib.IMAP4_SSL,
    uid: str,
    part_number: str,
    folder: str = "INBOX",
) -> AttachmentContent:
    """Download an email attachment by UID and part number.

    Returns the attachment content as base64-encoded string.
    """
    uid = _sanitize_uid(uid)
    if not re.fullmatch(r"[1-9][0-9]*", part_number):
        raise ValueError("part_number must be a positive integer from read_email.")
    status, _ = conn.select(_folder_arg(folder), readonly=True)
    if status != "OK":
        raise FolderNotFoundError(f"Folder '{folder}' not found.")

    _, raw_email = _fetch_message(conn, uid)
    msg = email.message_from_bytes(raw_email)

    counter = 0
    for part in msg.walk():
        counter += 1
        if str(counter) == part_number:
            payload = part.get_payload(decode=True)
            if payload is None:
                raise NaverIMAPError(f"Attachment part '{part_number}' has no content.")

            if len(payload) > MAX_ATTACHMENT_BYTES:
                raise NaverIMAPError(
                    f"Attachment size ({len(payload):,} bytes) exceeds the "
                    f"{MAX_ATTACHMENT_BYTES:,}-byte limit."
                )

            filename = part.get_filename()
            if filename:
                filename = decode_header_value(filename)
            else:
                filename = f"attachment_{part_number}"

            content_type = part.get_content_type()
            content_b64 = base64.b64encode(payload).decode("ascii")

            return AttachmentContent(
                filename=filename,
                content_type=content_type,
                size=len(payload),
                content_base64=content_b64,
            )

    raise NaverIMAPError(
        f"Attachment part '{part_number}' not found in email UID '{uid}'. "
        "Check the part_number from read_email attachment metadata."
    )
