import json
import subprocess
import html
import ipaddress
import math
from queue import Empty, Queue
import re
import shutil
import signal
import socket
import time
import uuid
import hmac
import shlex
from importlib.metadata import PackageNotFoundError, version as package_version
from datetime import datetime, timedelta
from collections import defaultdict, deque
from contextvars import ContextVar
from functools import wraps
from bottle import run, Bottle, LocalRequest, LocalResponse, request, static_file, response, route, post, redirect, template, get, abort, HTTPError, HTTPResponse
from threading import Event, Lock, RLock, Thread, get_ident
from bottle_websocket import DownloadWorkerFailed, GeventWebSocketServer
from bottle_websocket import websocket
from socket import error
from geventwebsocket.exceptions import WebSocketError
from i18n import (
    LOCALE_COOKIE,
    catalog_json,
    get_translator,
    locale_options,
    normalize_locale,
    select_locale,
)
import os
import secrets
from urllib.error import HTTPError as URLHTTPError, URLError
from urllib.parse import parse_qsl, quote, urlencode, urljoin, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener
from collections_backend import (
    APIError, CollectionService, ConnectionStore, COMMIT_TIMEOUT_SECONDS,
    PLAN_TTL_SECONDS, PREVIEW_TIMEOUT_SECONDS, PREVIEW_WORK_TIMEOUT_SECONDS, StateError,
    atomic_json_write, batch_limit, delete_media_file, ensure_media_directory,
    is_direct_metadata, metadata_upload_date, nonblocking_auth_io, nonblocking_io,
    normalize_date_policy, open_media_file,
    policy_rejection, read_state, reject_client_paths, relative_media_path,
    safe_media_path, valid_collection_target,
)

DOWNFOLDER_DIR = os.environ.get("DOWNLOAD_DIR", "./downfolder")
STATE_DIR = os.path.abspath(os.environ.get("STATE_DIR", "./metadata"))
AUTH_FILE = os.environ.get("AUTH_FILE", "Auth.json")
APP_STATE_FILE = os.path.join(STATE_DIR, "app_state.json")
HISTORY_FILE = os.path.join(STATE_DIR, "download_history.json")
QUEUE_STATE_FILE = os.path.join(STATE_DIR, "queue_state.json")
COLLECTIONS_STATE_FILE = os.path.join(STATE_DIR, "collections.json")
CONNECTIONS_STATE_FILE = os.path.join(STATE_DIR, "connections.json")
APP_COOKIES_FILE = os.path.join(STATE_DIR, "yt-dlp-cookies.txt")
APP_VERSION = os.environ.get("APP_VERSION", "26.0906")
API_TOKEN = os.environ.get("YDLNAS_API_TOKEN", "").strip()
YTDLP_COOKIES_FILE = os.environ.get("YTDLP_COOKIES_FILE", "").strip()
YTDLP_EXTRA_ARGS = os.environ.get("YTDLP_EXTRA_ARGS", "").strip()
COOKIES_FILE_MAX_BYTES = 1024 * 1024
YDLNAS_ALLOW_PRIVATE_SOURCES = os.environ.get("YDLNAS_ALLOW_PRIVATE_SOURCES", "").strip().lower() in {
    "1", "true", "yes", "on",
}


def nonnegative_float_env(name, default):
    try:
        return max(0.0, float(os.environ.get(name, default)))
    except (TypeError, ValueError):
        return float(default)


STORAGE_WARNING_GB = nonnegative_float_env("YDLNAS_STORAGE_WARNING_GB", "10")
STORAGE_CRITICAL_GB = nonnegative_float_env("YDLNAS_STORAGE_CRITICAL_GB", "2")
VALID_RESOLUTIONS = {"best", "compatible-mp4", "audio", "audio-m4a", "audio-mp3", "audio-opus"}
RESOLUTION_PATTERN = re.compile(r"^\d{3,4}p$")
SUBTITLE_PATTERN = re.compile(r"^(vtt|srt)\|([A-Za-z0-9_-]+(?:-[A-Za-z0-9_-]+)*)$")
VIDEO_EXTENSIONS = {".mp4", ".m4v", ".mkv", ".mov", ".webm", ".avi"}
AUDIO_EXTENSIONS = {".mp3", ".m4a", ".aac", ".flac", ".opus", ".ogg", ".wav"}
SUBTITLE_EXTENSIONS = {".srt", ".vtt", ".ass", ".ssa"}
SKIPPED_DOWNFOLDER_NAMES = {".incomplete", ".DS_Store"}
SHARED_URL_PATTERN = re.compile(r"https?://[^\s<>\"]+", re.IGNORECASE)
SUBTITLE_QA_MAX_FILE_BYTES = max(1024, int(os.environ.get("SUBTITLE_QA_MAX_FILE_BYTES", str(5 * 1024 * 1024))))
SUBTITLE_QA_MAX_REFERENCE_CHARS = max(1000, int(os.environ.get("SUBTITLE_QA_MAX_REFERENCE_CHARS", "100000")))
SUBTITLE_QA_MAX_KEYWORDS = 20
YTDLP_OUTPUT_TEMPLATE = "%(title)s__%(extractor_key)s_%(id)s.%(ext)s"
COMPATIBLE_MP4_FORMAT_SELECTOR = (
    "bestvideo[ext=mp4][vcodec^=avc1]+bestaudio[ext=m4a][acodec^=mp4a]/"
    "best[ext=mp4][vcodec^=avc1][acodec^=mp4a]/"
    "bestvideo[vcodec^=avc1]+bestaudio[acodec^=mp4a]/"
    "best[vcodec^=avc1][acodec^=mp4a]"
)
YTDLP_ITEM_PREFIX = "__YDLNAS_ITEM__:"
YTDLP_ITEM_TEMPLATE = (
    '{"filepath":%(filepath|"")j,"title":%(title|"")j,'
    '"uploader":%(uploader|"")j,"channel":%(channel|"")j,'
    '"thumbnail":%(thumbnail|"")j,"duration":%(duration|0)j,'
    '"id":%(id|"")j,"extractor_key":%(extractor_key|"")j,'
    '"webpage_url":%(webpage_url|"")j,"original_url":%(original_url|"")j,'
    '"upload_date":%(upload_date|"")j}'
)
GENERIC_INSTAGRAM_TITLE_PATTERN = re.compile(r"^Video by .+$", re.IGNORECASE)
QUEUE_STATE_VERSION = 5
PREFLIGHT_GRACE_SECONDS = 3.0
PREFLIGHT_RECEIPT_TTL_SECONDS = 60.0
QUEUE_JOB_STATES = {"queued", "checking", "ready", "downloading"}
PLAYLIST_MODES = {"single", "first10", "all"}
SECTION_MODES = {"full", "from_timestamp"}
SHARE_PROFILE_COOKIE = "ydlnas_share_profile"
SHARE_REVIEW_COOKIE = "share_review"
SHARE_PROFILES = {"best", "compatible-mp4", "1080p", "720p", "audio-mp3", "audio-m4a", "audio-opus", "ask"}
SHARE_PROFILE_ALIASES = {
    "best": "best",
    "compatible": "compatible-mp4",
    "compatible-mp4": "compatible-mp4",
    "mp4": "compatible-mp4",
    "1080": "1080p",
    "1080p": "1080p",
    "720": "720p",
    "720p": "720p",
    "mp3": "audio-mp3",
    "audio": "audio-m4a",
    "m4a": "audio-m4a",
    "opus": "audio-opus",
    "audio-mp3": "audio-mp3",
    "audio-m4a": "audio-m4a",
    "audio-opus": "audio-opus",
    "ask": "ask",
}
THUMBNAIL_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")
TRACKING_QUERY_KEYS = {
    "fbclid",
    "feature",
    "gclid",
    "igsh",
    "si",
    "start",
    "t",
    "time_continue",
    "utm_campaign",
    "utm_content",
    "utm_medium",
    "utm_source",
    "utm_term",
}
ANSI_ESCAPE_PATTERN = re.compile(r"\x1b\[[0-9;]*m")
DIAGNOSTIC_URL_PATTERN = re.compile(r"https?://[^\s]+", re.IGNORECASE)
FAILURE_PATTERNS = (
    ("storage_full", ("no space left on device", "disk quota exceeded", "errno 28")),
    ("storage_permission", ("permission denied", "read-only file system", "operation not permitted")),
    ("auth_required", (
        "sign in to confirm", "login required", "authentication required", "cookies are required",
        "use --cookies", "members-only", "private video", "age-restricted",
    )),
    ("rate_limited", ("http error 429", "too many requests", "rate limit")),
    ("format_unavailable", ("requested format is not available", "no video formats found")),
    ("unsupported_url", ("unsupported url", "no suitable extractor")),
    ("network", (
        "timed out", "timeout", "unable to download webpage", "connection refused",
        "connection reset", "temporary failure in name resolution", "name or service not known",
    )),
    ("postprocessing", ("postprocessing", "post-processing", "ffmpeg", "merger error")),
    ("extractor", (
        "unable to extract", "signature extraction failed", "nsig extraction failed",
        "please report this issue", "update to a nightly version",
    )),
)

ERROR_CODE_BY_MESSAGE = {
    "Unauthorized": "unauthorized",
    "Invalid password, account, or API token.": "invalid_credentials",
    "URL is required": "url_required",
    "Only HTTP and HTTPS source URLs are allowed": "source_url_scheme",
    "Private or local source URLs are blocked": "private_source_url",
    "Source host could not be resolved": "source_url_unresolvable",
    "Source URL exceeded the redirect limit": "source_redirect_limit",
    "Resolution is required": "resolution_required",
    "Subtitle downloads require a language code, for example vtt|en or srt|ko": "subtitle_language_required",
    "Unsupported resolution": "unsupported_resolution",
    "Unsupported playlist mode": "unsupported_playlist_mode",
    "Playlist scope is required": "playlist_scope_required",
    "Unsupported timestamp mode": "unsupported_timestamp_mode",
    "Timestamp was not found in the shared URL": "timestamp_not_found",
    "Unsupported mobile share profile": "unsupported_share_profile",
    "Cookies file is required": "cookies_file_required",
    "Cookies file is too large": "cookies_file_too_large",
    "Cookies file is not a valid Netscape cookies file": "cookies_file_invalid",
    "Mounted cookies cannot be changed from the dashboard": "cookies_file_mounted",
    "Cookies file could not be saved": "cookies_file_save_failed",
    "Cookies file could not be deleted": "cookies_file_delete_failed",
    "Queued download not found or already active": "queue_not_found",
    "No active download to cancel": "active_download_not_found",
    "Download storage is critically low": "storage_critical",
    "History item not found": "history_not_found",
    "Valid file path not found": "valid_path_not_found",
    "Physical file not found": "physical_file_not_found",
    "Failed to delete physical file": "physical_file_delete_failed",
    "Reference transcript is required": "reference_required",
    "Subtitle history item not found": "subtitle_history_not_found",
    "Subtitle QA supports SRT, VTT, ASS, and SSA files": "subtitle_format_unsupported",
    "Subtitle file not found": "subtitle_file_not_found",
    "Subtitle file is too large to analyze": "subtitle_file_too_large",
    "Subtitle file could not be read": "subtitle_file_read_failed",
    "No subtitle text was found in this file": "subtitle_text_empty",
    "Subtitle QA is unavailable because nlptutti is not installed": "subtitle_qa_unavailable",
    "Subtitle QA could not analyze this transcript": "subtitle_qa_failed",
}
REFERENCE_TOO_LARGE_PATTERN = re.compile(r"^Reference transcript exceeds (\d+) characters$")

os.makedirs(STATE_DIR, exist_ok=True)
auth_state_lock = RLock()


def configure_request_context():
    if getattr(LocalRequest, "_ydlnas_contextvars", False):
        return

    def context_property(name):
        missing = object()
        context = ContextVar(name, default=missing)

        def get_value(_instance):
            value = context.get()
            if value is missing:
                raise RuntimeError("Request context not initialized.")
            return value

        return property(get_value, lambda _instance, value: context.set(value), lambda _instance: context.set(missing))

    # The vendored gevent adapter does not monkey-patch threading.local. Isolate
    # HTTP greenlets without replacing the worker's native queues and locks.
    LocalRequest.environ = context_property("ydlnas_request")
    for name in ("_status_line", "_status_code", "_cookies", "_headers", "body"):
        setattr(LocalResponse, name, context_property("ydlnas_response_" + name))
    LocalRequest._ydlnas_contextvars = True
    request.bind({})
    response.bind()


configure_request_context()


def get_error_details(msg):
    code = ERROR_CODE_BY_MESSAGE.get(msg)
    if code:
        return code, {}

    match = REFERENCE_TOO_LARGE_PATTERN.match(msg)
    if match:
        return "reference_too_large", {"limit": int(match.group(1))}

    return None, {}

def json_error(msg, status=400, params=None):
    response.status = status
    payload = {"success": False, "msg": msg}
    code, error_params = get_error_details(msg)
    if code:
        payload["code"] = code
    combined_params = dict(error_params)
    if isinstance(params, dict):
        combined_params.update(params)
    if combined_params:
        payload["params"] = combined_params
    return payload


def get_storage_status():
    """Return bounded, path-free capacity information for the download volume."""
    critical_bytes = int(STORAGE_CRITICAL_GB * (1024 ** 3))
    warning_bytes = max(critical_bytes, int(STORAGE_WARNING_GB * (1024 ** 3)))
    try:
        usage = shutil.disk_usage(DOWNFOLDER_DIR)
    except OSError:
        return {
            "available": False,
            "state": "unavailable",
            "blocking": False,
            "free_bytes": None,
            "total_bytes": None,
            "used_bytes": None,
            "free_percent": None,
            "warning_bytes": warning_bytes,
            "critical_bytes": critical_bytes,
        }

    state = "ok"
    if critical_bytes and usage.free <= critical_bytes:
        state = "critical"
    elif warning_bytes and usage.free <= warning_bytes:
        state = "warning"
    free_percent = round((usage.free / usage.total) * 100, 1) if usage.total else 0
    return {
        "available": True,
        "state": state,
        "blocking": state == "critical",
        "free_bytes": usage.free,
        "total_bytes": usage.total,
        "used_bytes": usage.used,
        "free_percent": free_percent,
        "warning_bytes": warning_bytes,
        "critical_bytes": critical_bytes,
    }


def sanitize_diagnostic_text(value):
    """Keep process diagnostics useful without logging URLs or mounted paths."""
    if isinstance(value, subprocess.TimeoutExpired):
        return "process timed out"
    text = ANSI_ESCAPE_PATTERN.sub("", str(value or "")).strip()
    text = DIAGNOSTIC_URL_PATTERN.sub("[url]", text)
    text = re.sub(r"(?i)\bbearer\s+\S+", "Bearer [redacted]", text)
    text = re.sub(r"\bydlnas_[A-Za-z0-9_-]+", "[redacted]", text)
    if API_TOKEN:
        text = text.replace(API_TOKEN, "[redacted]")
    known_paths = {
        AUTH_FILE,
        DOWNFOLDER_DIR,
        STATE_DIR,
        YTDLP_COOKIES_FILE,
        APP_COOKIES_FILE,
        os.path.abspath(AUTH_FILE),
        os.path.abspath(DOWNFOLDER_DIR),
        os.path.abspath(STATE_DIR),
    }
    for known_path in sorted((path for path in known_paths if path), key=len, reverse=True):
        text = text.replace(known_path, "[path]")
    text = re.sub(
        r"(?i)\b(authorization|password|token|cookie)(\s*[:=]\s*)\S+",
        r"\1\2[redacted]",
        text,
    )
    return text[:1000]


def classify_download_failure(lines=None, exception=None):
    diagnostics = [sanitize_diagnostic_text(line).casefold() for line in (lines or [])]
    if exception is not None:
        diagnostics.append(sanitize_diagnostic_text(exception).casefold())
    combined = "\n".join(diagnostics)
    for code, patterns in FAILURE_PATTERNS:
        if any(pattern in combined for pattern in patterns):
            return code
    return "unknown"


def terminate_process_group(process):
    if not process or process.poll() is not None:
        return
    try:
        if os.name == "posix":
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        else:
            process.terminate()
    except (OSError, ProcessLookupError):
        return

    def force_kill_after_grace_period():
        time.sleep(5)
        if process.poll() is not None:
            return
        try:
            if os.name == "posix":
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            else:
                process.kill()
        except (OSError, ProcessLookupError):
            pass

    Thread(target=force_kill_after_grace_period, name="download-cancel-watchdog", daemon=True).start()

def get_request_json():
    return request.json if isinstance(request.json, dict) else {}

def load_json_file(path, default=None):
    try:
        with open(path, encoding="utf-8") as data_file:
            return json.load(data_file)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {} if default is None else default


def atomic_write_json(path, payload, ensure_ascii=False):
    try:
        atomic_json_write(path, payload, ensure_ascii=ensure_ascii)
    except OSError as error:
        raise StateError("Persistent state could not be saved") from error

@nonblocking_auth_io
def save_app_state(updates):
    with auth_state_lock:
        state = load_json_file(APP_STATE_FILE, {})
        state.update(updates)
        atomic_write_json(APP_STATE_FILE, state, ensure_ascii=True)
        return state

@nonblocking_auth_io
def load_auth_data():
    with auth_state_lock:
        return _load_auth_data()


def _load_auth_data():
    data = load_json_file(AUTH_FILE, {})
    for key, value in list(data.items()):
        if isinstance(value, str) and re.fullmatch(r"\{\{[^{}]+\}\}", value.strip()):
            data[key] = ""

    for key in ("MY_ID", "MY_PW", "APP_PORT", "PROXY", "TERMS_ACCEPTED", "SECRET_KEY"):
        env_value = os.environ.get(key)
        if env_value is not None and env_value != "":
            data[key] = env_value

    state = load_json_file(APP_STATE_FILE, {})
    for key in ("TERMS_ACCEPTED", "SECRET_KEY"):
        if state.get(key):
            data[key] = state[key]

    if not data.get("SECRET_KEY"):
        data["SECRET_KEY"] = secrets.token_urlsafe(32)
        save_app_state({"SECRET_KEY": data["SECRET_KEY"]})

    data.setdefault("MY_ID", "")
    data.setdefault("MY_PW", "")
    data.setdefault("APP_PORT", "")
    data.setdefault("PROXY", "")
    data.setdefault("TERMS_ACCEPTED", "N")
    return data

def is_cookie_authenticated(data=None):
    data = data or load_auth_data()
    user_name = request.get_cookie("account", secret=data.get("SECRET_KEY"))
    return bool(data.get("MY_ID") and user_name == data.get("MY_ID"))

def is_api_authenticated(payload, data=None):
    data = data or load_auth_data()
    authorization = request.headers.get("Authorization", "")
    if API_TOKEN and authorization.startswith("Bearer "):
        supplied_token = authorization[7:].strip()
        if hmac.compare_digest(supplied_token, API_TOKEN):
            return True

    request_id = payload.get("id")
    request_password = payload.get("pw")
    if not data.get("MY_ID") or not data.get("MY_PW") or request_id is None or request_password is None:
        return False
    return hmac.compare_digest(str(request_id or ""), str(data.get("MY_ID") or "")) and hmac.compare_digest(
        str(request_password or ""), str(data.get("MY_PW") or "")
    )

def safe_next_path(value, fallback="/youtube-dl"):
    value = (value or "").strip()
    if not value.startswith("/") or value.startswith("//") or any(ord(char) < 32 for char in value):
        return fallback
    return value

def extract_shared_url(*values):
    for value in values:
        if not isinstance(value, str):
            continue
        match = SHARED_URL_PATTERN.search(value)
        if match:
            return match.group(0).rstrip(".,);]")
    return ""


def normalize_api_share_profile(value, default="best", allow_ask=False):
    profile = SHARE_PROFILE_ALIASES.get(str(value or "").strip().lower())
    if profile == "ask" and not allow_ask:
        return None
    return profile or default


def parse_timestamp_seconds(value):
    value = str(value or "").strip().lower()
    if not value:
        return 0
    if value.isdigit():
        return max(0, int(value))

    if re.fullmatch(r"\d{1,3}(?::\d{1,2}){1,2}", value):
        parts = [int(part) for part in value.split(":")]
        if len(parts) == 2:
            return parts[0] * 60 + parts[1]
        return parts[0] * 3600 + parts[1] * 60 + parts[2]

    matches = re.findall(r"(\d+)(h|m|s)", value)
    if matches and "".join(f"{amount}{unit}" for amount, unit in matches) == value:
        multipliers = {"h": 3600, "m": 60, "s": 1}
        return sum(int(amount) * multipliers[unit] for amount, unit in matches)
    return 0


def extract_shared_timestamp(value):
    try:
        parsed = urlsplit(str(value or "").strip())
    except ValueError:
        return 0

    host = parsed.netloc.casefold()
    is_youtube = host == "youtube.com" or host.endswith(".youtube.com")
    is_short_url = host == "youtu.be" or host.endswith(".youtu.be")
    if not is_youtube and not is_short_url:
        return 0

    values = {key.casefold(): item for key, item in parse_qsl(parsed.query, keep_blank_values=True)}
    if parsed.fragment:
        fragment_values = {
            key.casefold(): item
            for key, item in parse_qsl(parsed.fragment, keep_blank_values=True)
        }
        values.update(fragment_values)
    for key in ("t", "start", "time_continue"):
        seconds = parse_timestamp_seconds(values.get(key))
        if seconds > 0:
            return seconds
    return 0


def format_timestamp(seconds):
    seconds = max(0, int(seconds or 0))
    hours, remainder = divmod(seconds, 3600)
    minutes, remaining_seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{remaining_seconds:02d}"
    return f"{minutes}:{remaining_seconds:02d}"


def build_share_context(*values, profile="best"):
    shared_url = extract_shared_url(*values)
    playlist_kind = classify_playlist_url(shared_url) if shared_url else "single"
    timestamp_seconds = extract_shared_timestamp(shared_url)
    normalized_profile = normalize_api_share_profile(profile, allow_ask=True)
    return {
        "url": shared_url,
        "profile": normalized_profile,
        "profile_required": normalized_profile == "ask",
        "playlist_kind": playlist_kind if playlist_kind in ("playlist", "channel") else "",
        "timestamp_seconds": timestamp_seconds or None,
        "timestamp_label": format_timestamp(timestamp_seconds) if timestamp_seconds else "",
    }


def normalize_media_url(value):
    value = str(value or "").strip()
    if not value:
        return ""

    try:
        parsed = urlsplit(value)
    except ValueError:
        return value

    if parsed.scheme.lower() not in ("http", "https") or not parsed.netloc:
        return value

    query = []
    for key, item_value in parse_qsl(parsed.query, keep_blank_values=True):
        lowered_key = key.lower()
        if lowered_key in TRACKING_QUERY_KEYS or lowered_key.startswith("utm_"):
            continue
        query.append((key, item_value))

    path = parsed.path.rstrip("/") or "/"
    return urlunsplit((
        parsed.scheme.lower(),
        parsed.netloc.lower(),
        path,
        urlencode(sorted(query)),
        "",
    ))

def cookie_secure_enabled():
    return os.environ.get("COOKIE_SECURE", "false").lower() == "true"


def get_request_locale():
    return select_locale(
        request.get_cookie(LOCALE_COOKIE),
        request.headers.get("Accept-Language", ""),
    )


def render_localized_template(template_path, **context):
    locale = get_request_locale()
    localized_context = {
        "locale": locale,
        "locale_json": json.dumps(locale),
        "locale_options": locale_options(),
        "translations_json": catalog_json(locale),
        "t": get_translator(locale),
    }
    localized_context.update(context)
    return template(template_path, **localized_context)

def set_pending_share_cookie(shared_url, data):
    response.set_cookie(
        "pending_share",
        shared_url,
        secret=data.get("SECRET_KEY"),
        path="/",
        httponly=True,
        samesite="lax",
        secure=cookie_secure_enabled(),
        max_age=600,
    )


def normalize_share_profile(value, default="best"):
    profile = str(value or "").strip().lower()
    return profile if profile in SHARE_PROFILES else default


def get_share_profile(data=None):
    data = data or load_auth_data()
    profile = request.get_cookie(SHARE_PROFILE_COOKIE, secret=data.get("SECRET_KEY"))
    return normalize_share_profile(profile)


def set_share_profile_cookie(profile, data):
    response.set_cookie(
        SHARE_PROFILE_COOKIE,
        normalize_share_profile(profile),
        secret=data.get("SECRET_KEY"),
        path="/",
        httponly=True,
        samesite="lax",
        secure=cookie_secure_enabled(),
        max_age=365 * 24 * 60 * 60,
    )


def set_share_review_cookie(shared_url, data):
    response.set_cookie(
        SHARE_REVIEW_COOKIE,
        shared_url,
        secret=data.get("SECRET_KEY"),
        path="/",
        httponly=True,
        samesite="lax",
        secure=cookie_secure_enabled(),
        max_age=600,
    )


def consume_share_review(data):
    shared_url = request.get_cookie(SHARE_REVIEW_COOKIE, secret=data.get("SECRET_KEY"))
    response.delete_cookie(SHARE_REVIEW_COOKIE, path="/")
    return shared_url or ""


def queue_shared_url(shared_url, profile=None):
    data = load_auth_data()
    profile = normalize_share_profile(profile or get_share_profile(data))
    if profile == "ask" or classify_playlist_url(shared_url) in ("playlist", "channel"):
        set_share_review_cookie(shared_url, data)
        redirect("/youtube-dl?shared=review")

    validation_error = validate_download_request(shared_url, profile)
    if validation_error:
        redirect("/youtube-dl?shared=invalid")

    result = enqueue_download(shared_url, profile, "web", ws_addr.wsClassVal)
    if result.get("duplicate"):
        redirect("/youtube-dl?shared=duplicate")
    if result.get("blocked"):
        redirect("/youtube-dl?shared=storage")

    download_manager.send_message("Shared URL received. Added to the NAS queue.")
    redirect("/youtube-dl?shared=queued")

def require_cookie_auth():
    data = load_auth_data()
    if not is_cookie_authenticated(data):
        return None, json_error("Unauthorized", 403)

    return data, None


def cookies_file_status():
    mounted = bool(YTDLP_COOKIES_FILE)
    cookie_path = YTDLP_COOKIES_FILE if mounted else APP_COOKIES_FILE
    exists = os.path.isfile(cookie_path) and (mounted or not os.path.islink(cookie_path))
    readable = exists and os.access(cookie_path, os.R_OK)
    return {
        "configured": mounted or exists,
        "readable": readable,
        "managed": not mounted and exists,
        "mode": "mounted" if mounted else ("managed" if exists else "none"),
        "max_bytes": COOKIES_FILE_MAX_BYTES,
    }


def active_cookies_file():
    status = cookies_file_status()
    if not status["configured"]:
        return ""
    if not status["readable"]:
        raise ValueError("Configured cookies file is unavailable")
    return YTDLP_COOKIES_FILE if status["mode"] == "mounted" else APP_COOKIES_FILE


def valid_netscape_cookies(contents):
    try:
        text = contents.decode("utf-8-sig")
    except (AttributeError, UnicodeDecodeError):
        return False
    if "\x00" in text:
        return False

    lines = text.splitlines()
    header_found = any(
        line.lstrip().startswith("#") and "netscape http cookie file" in line.casefold()
        for line in lines[:10]
    )
    if not header_found:
        return False

    record_count = 0
    for line in lines:
        stripped = line.strip()
        if not stripped or (stripped.startswith("#") and not stripped.startswith("#HttpOnly_")):
            continue
        fields = line.split("\t", 6)
        if len(fields) != 7:
            return False
        domain, include_subdomains, path, secure, expires, name, _ = fields
        if domain.startswith("#HttpOnly_"):
            domain = domain[len("#HttpOnly_"):]
        if (
            not domain
            or include_subdomains.upper() not in {"TRUE", "FALSE"}
            or not path.startswith("/")
            or secure.upper() not in {"TRUE", "FALSE"}
            or not name
        ):
            return False
        try:
            int(expires)
        except ValueError:
            return False
        record_count += 1
    return record_count > 0


def save_managed_cookies(contents):
    os.makedirs(os.path.dirname(APP_COOKIES_FILE), exist_ok=True)
    temp_path = f"{APP_COOKIES_FILE}.tmp-{uuid.uuid4().hex}"
    file_descriptor = None
    try:
        file_descriptor = os.open(temp_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(file_descriptor, "wb") as cookie_file:
            file_descriptor = None
            cookie_file.write(contents)
            cookie_file.flush()
            os.fsync(cookie_file.fileno())
        os.replace(temp_path, APP_COOKIES_FILE)
        os.chmod(APP_COOKIES_FILE, 0o600)
    except OSError:
        if file_descriptor is not None:
            os.close(file_descriptor)
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise


@get('/youtube-dl/cookies')
def get_cookies_status():
    _, error_response = require_cookie_auth()
    if error_response:
        return error_response
    return {"success": True, "status": cookies_file_status()}


@post('/youtube-dl/cookies')
def upload_cookies_file():
    _, error_response = require_cookie_auth()
    if error_response:
        return error_response
    if YTDLP_COOKIES_FILE:
        return json_error("Mounted cookies cannot be changed from the dashboard", 409)
    if request.content_length and request.content_length > COOKIES_FILE_MAX_BYTES + (64 * 1024):
        return json_error("Cookies file is too large", 413)

    upload = request.files.get("cookies_file")
    if not upload:
        return json_error("Cookies file is required", 400)
    try:
        contents = upload.file.read(COOKIES_FILE_MAX_BYTES + 1)
    except OSError:
        return json_error("Cookies file is not a valid Netscape cookies file", 400)
    if len(contents) > COOKIES_FILE_MAX_BYTES:
        return json_error("Cookies file is too large", 413)
    if not valid_netscape_cookies(contents):
        return json_error("Cookies file is not a valid Netscape cookies file", 400)
    try:
        save_managed_cookies(contents)
    except OSError:
        return json_error("Cookies file could not be saved", 500)
    return {"success": True, "status": cookies_file_status()}


@route('/youtube-dl/cookies', method='DELETE')
def delete_cookies_file():
    _, error_response = require_cookie_auth()
    if error_response:
        return error_response
    if YTDLP_COOKIES_FILE:
        return json_error("Mounted cookies cannot be changed from the dashboard", 409)
    try:
        if os.path.lexists(APP_COOKIES_FILE):
            os.unlink(APP_COOKIES_FILE)
    except OSError:
        return json_error("Cookies file could not be deleted", 500)
    return {"success": True, "status": cookies_file_status()}


class NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def source_address_is_allowed(address):
    try:
        parsed = ipaddress.ip_address(str(address).split("%", 1)[0])
    except ValueError:
        return False
    return parsed.is_global


@nonblocking_io
def resolve_source_addresses(hostname, port):
    try:
        records = socket.getaddrinfo(
            hostname,
            port,
            family=socket.AF_UNSPEC,
            type=socket.SOCK_STREAM,
            proto=socket.IPPROTO_TCP,
        )
    except (socket.gaierror, OSError):
        return []

    addresses = []
    for record in records:
        address = record[4][0]
        if address not in addresses:
            addresses.append(address)
    return addresses


def validate_source_url(url, resolve=True):
    if not isinstance(url, str) or not url.strip():
        return "URL is required"

    source_url = url.strip()
    if any(character.isspace() or ord(character) < 32 for character in source_url):
        return "Only HTTP and HTTPS source URLs are allowed"

    try:
        parsed = urlsplit(source_url)
        port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
    except (TypeError, ValueError):
        return "Only HTTP and HTTPS source URLs are allowed"

    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        return "Only HTTP and HTTPS source URLs are allowed"

    hostname = parsed.hostname.rstrip(".").lower()
    if hostname == "localhost" or hostname.endswith(".localhost"):
        return None if YDLNAS_ALLOW_PRIVATE_SOURCES else "Private or local source URLs are blocked"

    try:
        literal_address = ipaddress.ip_address(hostname.split("%", 1)[0])
    except ValueError:
        literal_address = None

    if literal_address is not None:
        if not YDLNAS_ALLOW_PRIVATE_SOURCES and not source_address_is_allowed(literal_address):
            return "Private or local source URLs are blocked"
        return None

    if not resolve:
        return None

    addresses = resolve_source_addresses(hostname, port)
    if not addresses:
        return "Source host could not be resolved"
    if not YDLNAS_ALLOW_PRIVATE_SOURCES and any(not source_address_is_allowed(address) for address in addresses):
        return "Private or local source URLs are blocked"
    return None


def source_redirect_opener():
    handlers = [NoRedirectHandler()]
    proxy = load_auth_data().get("PROXY")
    if proxy:
        handlers.insert(0, ProxyHandler({"http": proxy, "https": proxy}))
    return build_opener(*handlers)


def validate_source_redirects(url, opener=None, max_redirects=5, timeout=4):
    current_url = str(url or "").strip()
    redirect_opener = opener or source_redirect_opener()

    for redirect_count in range(max_redirects + 1):
        validation_error = validate_source_url(current_url, resolve=True)
        if validation_error:
            return validation_error

        request_object = Request(
            current_url,
            method="HEAD",
            headers={"User-Agent": "youtube-dl-nas source guard", "Accept": "*/*"},
        )
        try:
            with redirect_opener.open(request_object, timeout=timeout):
                return None
        except URLHTTPError as http_error:
            location = http_error.headers.get("Location") if http_error.headers else None
            if http_error.code not in {301, 302, 303, 307, 308} or not location:
                return None
            if redirect_count >= max_redirects:
                return "Source URL exceeded the redirect limit"
            current_url = urljoin(current_url, location)
        except (URLError, TimeoutError, OSError):
            # yt-dlp may use cookies, impersonation, or a configured proxy that this
            # lightweight probe cannot reproduce. DNS and literal-address checks
            # above remain authoritative when the probe itself is unavailable.
            return None

    return "Source URL exceeded the redirect limit"


def validate_download_request(url, resolution, resolve_source=True):
    if not isinstance(url, str) or not url.strip():
        return "URL is required"

    source_error = validate_source_url(url, resolve=resolve_source)
    if source_error:
        return source_error

    if not isinstance(resolution, str) or not resolution.strip():
        return "Resolution is required"

    resolution = resolution.strip()
    if resolution in VALID_RESOLUTIONS or RESOLUTION_PATTERN.match(resolution):
        return None

    if resolution in ("vtt", "srt") or re.match(r"^(vtt|srt)", resolution):
        if not SUBTITLE_PATTERN.match(resolution):
            return "Subtitle downloads require a language code, for example vtt|en or srt|ko"
        return None

    return "Unsupported resolution"

def output_relative_path(filepath):
    if not isinstance(filepath, str) or not filepath or filepath == "unknown" or "\\" in filepath:
        return ""
    root = os.path.abspath(DOWNFOLDER_DIR)
    candidate = os.path.abspath(filepath)
    try:
        if os.path.commonpath([root, candidate]) == root:
            relative = os.path.relpath(candidate, root).replace(os.sep, "/")
            return relative if safe_downfolder_path(relative) else ""
    except ValueError:
        return ""
    if not os.path.isabs(filepath) and safe_downfolder_path(filepath):
        return filepath
    return ""


def get_relative_path(item):
    if not isinstance(item, dict):
        return ""
    if "relative_path" in item:
        return relative_media_path(item["relative_path"]) or ""
    filename = item.get("filename")
    if filename and filename != "unknown":
        return relative_media_path(filename) or ""
    return output_relative_path(item.get("filepath"))


def get_actual_filename(item):
    relative = get_relative_path(item)
    return relative.rsplit("/", 1)[-1] if relative else ""


def get_media_identity(metadata):
    metadata = metadata if isinstance(metadata, dict) else {}
    media_id = str(metadata.get("id") or "").strip()
    extractor = str(metadata.get("extractor_key") or metadata.get("extractor") or "").strip()
    return media_id, extractor


def get_media_display_title(metadata, fallback):
    metadata = metadata if isinstance(metadata, dict) else {}
    title = str(metadata.get("title") or metadata.get("playlist_title") or fallback or "").strip()
    media_id, extractor = get_media_identity(metadata)
    if (
        media_id
        and extractor.lower().startswith("instagram")
        and GENERIC_INSTAGRAM_TITLE_PATTERN.fullmatch(title)
        and media_id not in title
    ):
        return f"{title} [{media_id}]"
    return title


def safe_downfolder_path(filename):
    return safe_media_path(DOWNFOLDER_DIR, filename)

def get_nlptutti_version():
    try:
        return package_version("nlptutti")
    except PackageNotFoundError:
        return "unavailable"

def clean_subtitle_text_line(value):
    value = re.sub(r"\{\\[^}]+\}", "", value or "")
    value = re.sub(r"<[^>]+>", "", value)
    value = html.unescape(value.replace("\\N", " ").replace("\\n", " "))
    return re.sub(r"\s+", " ", value).strip()

def extract_subtitle_text(content, extension):
    """Extract spoken text from SRT, VTT, ASS, or SSA subtitle content."""
    extension = (extension or "").lower()
    normalized = (content or "").replace("\ufeff", "").replace("\r\n", "\n").replace("\r", "\n")

    if extension in {".ass", ".ssa"}:
        dialogue_lines = []
        for line in normalized.splitlines():
            if not line.lstrip().lower().startswith("dialogue:"):
                continue
            fields = line.split(",", 9)
            if len(fields) == 10:
                text = clean_subtitle_text_line(fields[9])
                if text:
                    dialogue_lines.append(text)
        return " ".join(dialogue_lines)

    cue_lines = []
    blocks = re.split(r"\n\s*\n", normalized)
    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines or lines[0].upper() == "WEBVTT":
            continue
        if lines[0].upper().startswith(("NOTE", "STYLE", "REGION")):
            continue

        timestamp_index = next((index for index, line in enumerate(lines) if "-->" in line), None)
        if timestamp_index is not None:
            text_lines = lines[timestamp_index + 1:]
        else:
            text_lines = [line for line in lines if not line.isdigit() and "-->" not in line]

        for line in text_lines:
            text = clean_subtitle_text_line(line)
            if text:
                cue_lines.append(text)
    return " ".join(cue_lines)

def normalize_qa_keywords(value):
    if isinstance(value, str):
        candidates = re.split(r"[,\n]", value)
    elif isinstance(value, list):
        candidates = value
    else:
        candidates = []

    keywords = []
    for candidate in candidates:
        keyword = re.sub(r"\s+", " ", str(candidate or "")).strip()
        if keyword and keyword not in keywords:
            keywords.append(keyword)
        if len(keywords) >= SUBTITLE_QA_MAX_KEYWORDS:
            break
    return keywords

def analyze_subtitle_text(reference, transcription, keywords=None):
    try:
        import nlptutti
    except ImportError as error:
        raise RuntimeError("nlptutti is not installed") from error

    reference = re.sub(r"\s+", " ", reference or "").strip()
    transcription = re.sub(r"\s+", " ", transcription or "").strip()
    cer = nlptutti.get_cer(reference, transcription)
    wer = nlptutti.get_wer(reference, transcription)
    crr = nlptutti.get_crr(reference, transcription)

    keyword_results = []
    for keyword in keywords or []:
        pattern = nlptutti.make_keyword_pattern(keyword, nlptutti.COMPLEX_JOSA, nlptutti.COMPLEX_EOMI)
        reference_count = len(pattern.findall(reference))
        subtitle_count = len(pattern.findall(transcription))
        preserved_count = min(reference_count, subtitle_count)
        preservation_rate = round(preserved_count / reference_count, 4) if reference_count else None
        keyword_results.append({
            "keyword": keyword,
            "reference_count": reference_count,
            "subtitle_count": subtitle_count,
            "preserved_count": preserved_count,
            "preservation_rate": preservation_rate,
        })

    return {
        "cer": cer,
        "wer": wer,
        "crr": crr,
        "reference_characters": len(reference.replace(" ", "")),
        "subtitle_characters": len(transcription.replace(" ", "")),
        "reference_words": len(reference.split()),
        "subtitle_words": len(transcription.split()),
        "keywords": keyword_results,
        "nlptutti_version": get_nlptutti_version(),
    }

def get_download_type(resolution):
    resolution = resolution or ""
    if resolution.startswith("audio"):
        return "audio"
    if re.match(r"^(vtt|srt)", resolution):
        return "subtitle"
    return "video"

def infer_download_type(resolution, filename=""):
    if resolution and resolution != "mounted":
        return get_download_type(resolution)

    extension = os.path.splitext(filename or "")[1].lower()
    if extension in AUDIO_EXTENSIONS:
        return "audio"
    if extension in SUBTITLE_EXTENSIONS:
        return "subtitle"
    if extension in VIDEO_EXTENSIONS:
        return "video"
    return "file"

def get_mounted_file_uuid(filename):
    return "file-" + str(uuid.uuid5(uuid.NAMESPACE_URL, f"youtube-dl-nas:{filename}"))

def build_mounted_file_item(filename):
    file_path = safe_downfolder_path(filename)
    if not file_path or not os.path.isfile(file_path):
        return None

    try:
        stat_result = os.stat(file_path)
    except OSError:
        return None
    return normalize_history_item({
        "uuid": get_mounted_file_uuid(filename),
        "timestamp": datetime.fromtimestamp(stat_result.st_mtime).isoformat(),
        "url": "",
        "resolution": "mounted",
        "title": os.path.splitext(os.path.basename(filename))[0] or filename,
        "channel": "Mounted folder",
        "status": "file_only",
        "filepath": filename,
        "relative_path": filename,
        "filename": os.path.basename(filename),
        "progress": 100,
        "source": "mounted_folder",
        "metadata_status": "missing",
        "thumbnail_file": find_thumbnail_sidecar(filename),
    })

def list_mounted_file_items():
    if not os.path.isdir(DOWNFOLDER_DIR) or os.path.islink(DOWNFOLDER_DIR):
        return []

    items = []
    try:
        for directory, directories, filenames in os.walk(DOWNFOLDER_DIR, followlinks=False):
            directories[:] = [
                name for name in directories if not name.startswith(".")
                and safe_downfolder_path(os.path.relpath(os.path.join(directory, name), DOWNFOLDER_DIR))
            ]
            media_stems = {
                os.path.splitext(filename)[0].casefold()
                for filename in filenames
                if os.path.splitext(filename)[1].casefold() in VIDEO_EXTENSIONS | AUDIO_EXTENSIONS
            }
            for filename in filenames:
                if filename in SKIPPED_DOWNFOLDER_NAMES or filename.startswith("."):
                    continue
                stem, extension = os.path.splitext(filename)
                if extension.casefold() in THUMBNAIL_EXTENSIONS and stem.casefold() in media_stems:
                    continue
                relative = os.path.relpath(os.path.join(directory, filename), DOWNFOLDER_DIR).replace(os.sep, "/")
                item = build_mounted_file_item(relative)
                if item:
                    items.append(item)
    except OSError as e:
        print(f"Failed to scan mounted folder files: {sanitize_diagnostic_text(e)}")
        return []

    return sorted(items, key=lambda item: item.get("timestamp", ""), reverse=True)

def get_mounted_file_item(item_uuid):
    for item in list_mounted_file_items():
        if item.get("uuid") == item_uuid:
            return item
    return None

def normalize_history_item(item):
    item = dict(item or {})
    if not item.get('uuid'):
        item['uuid'] = str(uuid.uuid4())
    if not item.get('timestamp'):
        item['timestamp'] = ""

    relative_path = get_relative_path(item)
    filename = get_actual_filename(item)
    file_path = safe_downfolder_path(relative_path)
    file_exists = bool(file_path and os.path.isfile(file_path))
    try:
        file_size_bytes = os.path.getsize(file_path) if file_exists else 0
    except OSError:
        file_exists, file_size_bytes = False, 0

    item.setdefault('url', '')
    item.setdefault('resolution', '')
    item.setdefault('title', '')
    item.setdefault('channel', '')
    item.setdefault('thumbnail', '')
    thumbnail = item.get("thumbnail_relative_path") or item.get("thumbnail_file")
    if thumbnail:
        thumbnail = relative_media_path(thumbnail) or ""
        if "/" not in thumbnail and "/" in relative_path:
            thumbnail = relative_path.rsplit("/", 1)[0] + "/" + thumbnail
        if (
            os.path.splitext(thumbnail)[0] != os.path.splitext(relative_path)[0]
            or os.path.splitext(thumbnail)[1].casefold() not in THUMBNAIL_EXTENSIONS
            or not safe_downfolder_path(thumbnail)
        ):
            thumbnail = ""
    else:
        thumbnail = find_thumbnail_sidecar(relative_path)
    item["thumbnail_file"] = thumbnail
    item["thumbnail_relative_path"] = thumbnail
    item.setdefault('duration_seconds', 0)
    item.setdefault('media_id', '')
    item.setdefault('extractor', '')
    item.setdefault('section_mode', 'full')
    item.setdefault('section_start', 0)
    item.setdefault('status', 'unknown')
    item.setdefault('failure_code', '')
    item["relative_path"] = relative_path
    item["filepath"] = relative_path
    item.setdefault('source', 'history')
    item.setdefault('metadata_status', 'saved' if item.get('source') != 'mounted_folder' else 'missing')
    item['filename'] = filename
    item['file_exists'] = file_exists
    item['file_size_bytes'] = file_size_bytes
    if relative_path and item["status"] in {"completed", "file_only", "missing"}:
        item["status"] = ("file_only" if item.get("source") == "mounted_folder" else "completed") if file_exists else "missing"
    thumbnail_path = safe_downfolder_path(item.get('thumbnail_file'))
    item['thumbnail_file_exists'] = bool(thumbnail_path and os.path.isfile(thumbnail_path))
    try:
        item['thumbnail_file_size_bytes'] = os.path.getsize(thumbnail_path) if item['thumbnail_file_exists'] else 0
    except OSError:
        item["thumbnail_file_exists"] = False
        item["thumbnail_file_size_bytes"] = 0
    item['thumbnail_local_url'] = f"/static/thumbnail/{item['uuid']}" if item['thumbnail_file_exists'] else ""
    item['download_type'] = infer_download_type(item.get('resolution', ''), filename)
    item.setdefault('progress', 0)
    return item


def parse_boolean(value):
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


def classify_playlist_url(value):
    """Classify URLs that can unexpectedly expand into multi-item downloads."""
    try:
        parsed = urlsplit(str(value or "").strip())
    except ValueError:
        return "single"

    host = parsed.netloc.casefold()
    path = parsed.path.casefold().rstrip("/")
    query = {key.casefold(): item for key, item in parse_qsl(parsed.query, keep_blank_values=True)}

    if "youtube.com" in host or "youtu.be" in host:
        has_video = bool(query.get("v")) or "youtu.be" in host or path.startswith("/shorts/")
        if query.get("list"):
            return "video_playlist" if has_video else "playlist"
        if path == "/playlist":
            return "playlist"
        if path.startswith(("/channel/", "/c/", "/user/", "/@")):
            return "channel"

    if any(query.get(key) for key in ("playlist", "album", "set")):
        return "playlist"
    if any(token in path.split("/") for token in ("playlist", "playlists", "channel", "channels")):
        return "playlist"
    return "single"


def normalize_playlist_mode(value, url=""):
    mode = str(value or "").strip().lower()
    if mode in PLAYLIST_MODES:
        return mode
    if not mode:
        return "single"
    return None


def validate_playlist_request(url, playlist_mode, explicit=False):
    mode = normalize_playlist_mode(playlist_mode, url)
    if not mode:
        return "Unsupported playlist mode"
    if explicit and classify_playlist_url(url) in ("playlist", "channel"):
        if not str(playlist_mode or "").strip() or mode == "single":
            return "Playlist scope is required"
    return None


def normalize_section_mode(value):
    mode = str(value or "").strip().lower()
    if not mode:
        return "full"
    return mode if mode in SECTION_MODES else None


def validate_section_request(url, section_mode):
    mode = normalize_section_mode(section_mode)
    if not mode:
        return "Unsupported timestamp mode"
    if mode == "from_timestamp" and not extract_shared_timestamp(url):
        return "Timestamp was not found in the shared URL"
    return None


def find_thumbnail_sidecar(filename):
    file_path = safe_downfolder_path(filename)
    if not file_path:
        return ""
    stem, extension = os.path.splitext(file_path)
    if extension.casefold() in THUMBNAIL_EXTENSIONS:
        return ""
    for thumbnail_extension in THUMBNAIL_EXTENSIONS:
        relative = os.path.splitext(filename)[0] + thumbnail_extension
        candidate = safe_downfolder_path(relative)
        if candidate and os.path.isfile(candidate):
            return relative
    return ""


def normalize_queue_job(item, restored=False):
    if isinstance(item, dict):
        job = dict(item)
    elif isinstance(item, (list, tuple)):
        job = {
            "url": item[0] if len(item) > 0 else "",
            "resolution": item[2] if len(item) > 2 else "",
            "source": item[3] if len(item) > 3 else "web",
        }
    else:
        return None

    if any(key in job for key in ("filepath", "relative_path", "physical_path", "target_path", "target_directory")):
        return None
    url = str(job.get("url") or "").strip()
    resolution = str(job.get("resolution") or "").strip()
    if validate_download_request(url, resolution, resolve_source=False):
        return None

    source = str(job.get("source") or "web").strip() or "web"
    created_at = str(job.get("created_at") or datetime.now().isoformat())
    job_id = str(job.get("id") or uuid.uuid4())
    try:
        attempts = max(0, int(job.get("attempts") or 0))
    except (TypeError, ValueError):
        attempts = 0
    playlist_mode = normalize_playlist_mode(job.get("playlist_mode"), url)
    if not playlist_mode:
        return None
    section_mode = normalize_section_mode(job.get("section_mode"))
    if not section_mode:
        return None
    section_start = extract_shared_timestamp(url) if section_mode == "from_timestamp" else 0
    if section_mode == "from_timestamp" and not section_start:
        return None

    state = str(job.get("state") or "queued").strip().lower()
    if state not in QUEUE_JOB_STATES:
        state = "queued"

    def queue_timestamp(name):
        try:
            return max(0.0, float(job.get(name) or 0))
        except (TypeError, ValueError):
            return 0.0

    try:
        duration_seconds = max(0, int(float(job.get("duration_seconds") or 0)))
    except (TypeError, ValueError):
        duration_seconds = 0

    collection_id = job.get("collection_id") or ""
    batch_id = job.get("batch_id") or ""
    target_directory = job.get("target_relative_directory") or ""
    try:
        date_policy = normalize_date_policy(job.get("date_policy"))
    except APIError:
        return None
    if collection_id or batch_id or target_directory or date_policy is not None:
        if (
            not valid_collection_target(collection_id, target_directory)
            or not isinstance(batch_id, str) or not batch_id
            or date_policy is None
        ):
            return None

    return {
        "id": job_id,
        "url": url,
        "normalized_url": normalize_media_url(job.get("normalized_url") or url),
        "resolution": resolution,
        "source": source,
        "created_at": created_at,
        "restored": bool(restored or job.get("restored")),
        "force": parse_boolean(job.get("force")),
        "attempts": attempts,
        "playlist_mode": playlist_mode,
        "write_thumbnail": parse_boolean(job.get("write_thumbnail")),
        "section_mode": section_mode,
        "section_start": section_start,
        "state": state,
        "preflight_started_at": queue_timestamp("preflight_started_at"),
        "preflight_ready_at": queue_timestamp("preflight_ready_at"),
        "title": str(job.get("title") or "").strip(),
        "channel": str(job.get("channel") or "").strip(),
        "thumbnail": str(job.get("thumbnail") or "").strip(),
        "duration_seconds": duration_seconds,
        "media_id": str(job.get("media_id") or "").strip(),
        "extractor": str(job.get("extractor") or "").strip(),
        "preflight_warning": str(job.get("preflight_warning") or "").strip(),
        "upload_date": metadata_upload_date(job),
        "collection_id": collection_id,
        "batch_id": batch_id,
        "target_relative_directory": target_directory,
        "date_policy": date_policy,
    }


def create_queue_job(
    url,
    resolution,
    source,
    force=False,
    playlist_mode="single",
    write_thumbnail=False,
    section_mode="full",
):
    return normalize_queue_job({
        "id": str(uuid.uuid4()),
        "url": url,
        "resolution": resolution,
        "source": source,
        "created_at": datetime.now().isoformat(),
        "force": force,
        "playlist_mode": playlist_mode,
        "write_thumbnail": write_thumbnail,
        "section_mode": section_mode,
    })


def public_queue_job(job, position=None):
    job = normalize_queue_job(job)
    if not job:
        return None

    public_job = {
        "id": job["id"],
        "url": job["url"],
        "resolution": job["resolution"],
        "source": job["source"],
        "created_at": job["created_at"],
        "restored": job["restored"],
        "playlist_mode": job["playlist_mode"],
        "write_thumbnail": job["write_thumbnail"],
        "section_mode": job["section_mode"],
        "section_start": job["section_start"],
        "state": job["state"],
        "preflight_started_at": job["preflight_started_at"],
        "preflight_ready_at": job["preflight_ready_at"],
        "preflight_remaining_seconds": max(
            0,
            int(math.ceil(job["preflight_ready_at"] - time.time())),
        ) if job["preflight_ready_at"] else 0,
        "title": job["title"],
        "channel": job["channel"],
        "thumbnail": job["thumbnail"],
        "duration_seconds": job["duration_seconds"],
        "media_id": job["media_id"],
        "extractor": job["extractor"],
        "preflight_warning": job["preflight_warning"],
        "upload_date": job["upload_date"],
        "collection_id": job["collection_id"] or None,
        "batch_id": job["batch_id"] or None,
        "target_relative_directory": job["target_relative_directory"],
        "date_policy": job["date_policy"],
    }
    if position is not None:
        public_job["position"] = position
    return public_job


def pending_queue_jobs():
    with dl_q.mutex:
        return [
            job
            for item in list(dl_q.queue)
            if (job := normalize_queue_job(item)) is not None
        ]


def persist_queue_state():
    with queue_state_lock:
        active = normalize_queue_job(active_queue_job) if active_queue_job else None
        write_queue_snapshot(active, pending_queue_jobs())


def write_queue_snapshot(active, pending):
    require_usable_queue()
    atomic_write_json(QUEUE_STATE_FILE, {
        "version": QUEUE_STATE_VERSION,
        "updated_at": datetime.now().isoformat(),
        "active": active,
        "pending": pending,
    })


def apply_collection_queue_journal(jobs, terminal_job_ids=()):
    with queue_operation_lock, queue_state_lock:
        active = normalize_queue_job(active_queue_job) if active_queue_job else None
        pending = pending_queue_jobs()
        kept = [job for job in pending if job["id"] not in terminal_job_ids]
        present = {job["id"] for job in kept}
        if active:
            present.add(active["id"])
        additions = []
        for item in jobs:
            job = normalize_queue_job(item)
            if not job:
                raise StateError("Invalid reserved queue job")
            if job["id"] not in present:
                present.add(job["id"])
                additions.append(job)
        write_queue_snapshot(active, kept + additions)
        with dl_q.mutex:
            sentinels = [item for item in dl_q.queue if item is None]
            dl_q.queue.clear()
            dl_q.queue.extend(kept + additions + sentinels)
            dl_q.unfinished_tasks = max(0, dl_q.unfinished_tasks - (len(pending) - len(kept))) + len(additions)
            dl_q.not_empty.notify_all()
            if dl_q.unfinished_tasks == 0:
                dl_q.all_tasks_done.notify_all()
            dl_q.not_full.notify_all()


def load_persisted_queue():
    global queue_restore_count, queue_state_loaded

    with queue_state_lock:
        if queue_state_loaded:
            return queue_restore_count

    payload = read_state(QUEUE_STATE_FILE, {})
    if not isinstance(payload, dict) or payload.get("version", 1) not in range(1, QUEUE_STATE_VERSION + 1):
        raise StateError("Invalid queue state version")
    if "pending" in payload and not isinstance(payload["pending"], list):
        raise StateError("Invalid pending queue state")
    candidates = []
    if isinstance(payload, dict):
        if payload.get("active") is not None:
            candidates.append(payload["active"])
        if isinstance(payload.get("pending"), list):
            candidates.extend(payload["pending"])

    restored_jobs = []
    seen_job_ids = set()
    for item in candidates:
        job = normalize_queue_job(item, restored=True)
        if not job:
            raise StateError("Invalid persisted queue job")
        if job["id"] in seen_job_ids:
            continue
        seen_job_ids.add(job["id"])
        job["attempts"] += 1
        restored_jobs.append(job)

    apply_collection_queue_journal(restored_jobs)
    queue_restore_count = len(restored_jobs)
    queue_state_loaded = True
    if restored_jobs:
        print(f"Restored {len(restored_jobs)} queued download(s)")
    return queue_restore_count


def set_active_queue_job(job):
    global active_queue_job
    with queue_state_lock:
        candidate = normalize_queue_job(job)
        write_worker_queue_snapshot(candidate)
        active_queue_job = candidate


def write_worker_queue_snapshot(active):
    try:
        write_queue_snapshot(active, pending_queue_jobs())
    except StateError:
        # Latch the failure before releasing the state lock to other queue writers.
        mark_worker_failed()
        raise


def begin_preflight(job):
    job = normalize_queue_job(job)
    if not job:
        return None

    now = time.time()
    if not job["preflight_started_at"]:
        job["preflight_started_at"] = now
    if not job["preflight_ready_at"]:
        job["preflight_ready_at"] = now + PREFLIGHT_GRACE_SECONDS
    job["state"] = "checking"
    return normalize_queue_job(job)


def update_active_queue_job(job, **updates):
    global active_queue_job

    candidate = dict(job or {})
    candidate.update(updates)
    candidate = normalize_queue_job(candidate)
    if not candidate:
        return None

    with queue_state_lock:
        active = normalize_queue_job(active_queue_job) if active_queue_job else None
        if active and active["id"] == candidate["id"]:
            write_worker_queue_snapshot(candidate)
            active_queue_job = candidate
    return candidate


def wait_for_preflight_window(job):
    ready_at = float((job or {}).get("preflight_ready_at") or 0)
    while ready_at > time.time():
        if shutdown_event.is_set():
            return "shutdown"
        if download_manager.cancellation_requested(job["id"]):
            download_manager.consume_cancellation(job["id"])
            return "canceled"
        time.sleep(min(0.1, max(0.0, ready_at - time.time())))
    return "ready"


def clear_active_queue_job():
    global active_queue_job
    with queue_state_lock:
        write_worker_queue_snapshot(None)
        active_queue_job = None


def same_queue_request(first, second):
    first = normalize_queue_job(first)
    second = normalize_queue_job(second)
    if not first or not second:
        return False
    known_media = bool(first["media_id"] and first["extractor"] and second["media_id"] and second["extractor"])
    same_media = (
        first["media_id"] == second["media_id"]
        and first["extractor"].casefold() == second["extractor"].casefold()
    ) if known_media else False
    return (
        (same_media if known_media else first["normalized_url"] == second["normalized_url"])
        and first["resolution"] == second["resolution"]
        and first["playlist_mode"] == second["playlist_mode"]
        and first["write_thumbnail"] == second["write_thumbnail"]
        and first["section_mode"] == second["section_mode"]
        and first["section_start"] == second["section_start"]
    )


def find_queued_duplicate(job):
    with queue_state_lock:
        active = normalize_queue_job(active_queue_job) if active_queue_job else None
    if active and same_queue_request(active, job):
        return public_queue_job(active)

    for position, queued_job in enumerate(pending_queue_jobs(), start=1):
        if same_queue_request(queued_job, job):
            return public_queue_job(queued_job, position=position)
    return None


def media_identity_matches_filename(filename, media_id, extractor):
    filename = os.path.basename(str(filename or ""))
    media_id = str(media_id or "").strip()
    extractor = str(extractor or "").strip()
    if not filename or not media_id or not extractor:
        return False

    stem = os.path.splitext(filename)[0]
    expected_suffix = f"__{extractor}_{media_id}"
    return stem.casefold().endswith(expected_suffix.casefold())


def existing_download_summary(item):
    item = normalize_history_item(item)
    return {
        "uuid": item.get("uuid"),
        "title": item.get("title") or item.get("filename") or "Existing download",
        "filename": item.get("filename"),
        "relative_path": item.get("relative_path"),
        "resolution": item.get("resolution"),
        "timestamp": item.get("timestamp"),
        "status": item.get("status"),
        "source": item.get("source"),
        "section_mode": item.get("section_mode"),
        "section_start": item.get("section_start"),
        "channel": item.get("channel"),
        "thumbnail": item.get("thumbnail"),
        "thumbnail_local_url": item.get("thumbnail_local_url"),
        "duration_seconds": item.get("duration_seconds"),
        "file_exists": item.get("file_exists"),
        "file_size_bytes": item.get("file_size_bytes"),
        "download_type": item.get("download_type"),
        "metadata_status": item.get("metadata_status"),
        "media_id": item.get("media_id"),
        "extractor": item.get("extractor"),
        "upload_date": item.get("upload_date"),
        "thumbnail_file": item.get("thumbnail_file"),
    }


def set_recent_preflight_receipt(existing, job):
    global recent_preflight_receipt

    existing = existing_download_summary(existing)
    public_job = public_queue_job(job)
    now = time.time()
    receipt = {
        "id": f"{(public_job or {}).get('id', '')}:{existing.get('uuid') or ''}",
        "type": "duplicate_history",
        "created_at": datetime.now().isoformat(),
        "expires_at": now + PREFLIGHT_RECEIPT_TTL_SECONDS,
        "existing": existing,
        "job": public_job,
    }
    with preflight_receipt_lock:
        recent_preflight_receipt = receipt
    return receipt


@nonblocking_io
def get_recent_preflight_receipt():
    global recent_preflight_receipt

    with preflight_receipt_lock:
        receipt = recent_preflight_receipt
        if receipt and float(receipt.get("expires_at") or 0) <= time.time():
            recent_preflight_receipt = None
            receipt = None
        return dict(receipt) if receipt else None


def find_existing_download(
    url,
    resolution,
    media_id="",
    extractor="",
    require_thumbnail=False,
    section_mode="full",
    items=None,
):
    normalized_url = normalize_media_url(url)
    requested_type = get_download_type(resolution)
    requested_section_mode = normalize_section_mode(section_mode) or "full"
    requested_section_start = extract_shared_timestamp(url) if requested_section_mode == "from_timestamp" else 0
    normalized_items = items is not None
    items = items if normalized_items else download_manager.combined_history()

    for item in items:
        item = item if normalized_items else normalize_history_item(item)
        if not item.get("file_exists"):
            continue
        if require_thumbnail and not item.get("thumbnail_file_exists"):
            continue
        if item.get("section_mode") != requested_section_mode:
            continue
        if int(item.get("section_start") or 0) != requested_section_start:
            continue

        item_resolution = str(item.get("resolution") or "")
        item_type = item.get("download_type") or infer_download_type(item_resolution, item.get("filename"))
        profile_matches = item_resolution == resolution
        mounted_type_matches = item_resolution == "mounted" and item_type == requested_type
        if not profile_matches and not mounted_type_matches:
            continue
        if media_id and extractor and item.get("media_id") and item.get("extractor") and (
            str(item["media_id"]) != str(media_id) or str(item["extractor"]).casefold() != str(extractor).casefold()
        ):
            continue

        item_url = normalize_media_url(item.get("url"))
        if normalized_url and item_url and normalized_url == item_url:
            existing = existing_download_summary(item)
            if existing["file_exists"]:
                return existing

        if media_id and extractor:
            identity_matches = (
                str(item.get("media_id") or "") == str(media_id)
                and str(item.get("extractor") or "").casefold() == str(extractor).casefold()
            )
            filename_matches = media_identity_matches_filename(
                item.get("filename"), media_id, extractor
            )
            if identity_matches or filename_matches:
                existing = existing_download_summary(item)
                if existing["file_exists"]:
                    return existing
    return None


@nonblocking_io
def remove_queued_job(job_id):
    removed = None
    with queue_operation_lock:
        candidate = next((job for job in pending_queue_jobs() if job["id"] == job_id), None)
        if candidate:
            collections_service.record_job_end(candidate, "canceled", "queue_removed")
            with queue_state_lock:
                write_queue_snapshot(
                    normalize_queue_job(active_queue_job) if active_queue_job else None,
                    [job for job in pending_queue_jobs() if job["id"] != job_id],
                )
        with dl_q.mutex:
            kept = []
            for item in list(dl_q.queue):
                job = normalize_queue_job(item)
                if job and job["id"] == job_id and removed is None:
                    removed = job
                    continue
                kept.append(item)

            if removed:
                dl_q.queue.clear()
                dl_q.queue.extend(kept)
                dl_q.unfinished_tasks = max(0, dl_q.unfinished_tasks - 1)
                if dl_q.unfinished_tasks == 0:
                    dl_q.all_tasks_done.notify_all()
                dl_q.not_full.notify_all()

    if removed:
        download_manager.broadcast_to_all_clients(
            f"[QUEUE_UPDATED], {json.dumps({'removed_job_id': job_id})}"
        )
        return public_queue_job(removed)
    return None


def require_usable_queue():
    if worker_failed_event.is_set():
        raise StateError("Download worker failed; process restart is required")


def mark_worker_failed():
    already_failed = worker_failed_event.is_set()
    worker_failed_event.set()
    shutdown_event.set()
    if not already_failed:
        print("Download worker failed; stopping the web process for durable queue recovery", flush=True)


def download_worker_thread():
    try:
        dl_worker()
    except Exception:
        # dl_worker has latched the failure; the web server must exit, not this thread alone.
        mark_worker_failed()
        return
    if not shutdown_event.is_set():
        mark_worker_failed()


def start_download_thread_if_needed():
    global download_thread
    with download_thread_lock:
        require_usable_queue()
        if shutdown_event.is_set():
            raise StateError("Download service is stopping")
        if download_thread is not None and not download_thread.is_alive():
            mark_worker_failed()
            require_usable_queue()
        if download_thread is None:
            download_thread = Thread(target=download_worker_thread, name="download-worker", daemon=True)
            try:
                download_thread.start()
            except RuntimeError as error:
                mark_worker_failed()
                raise StateError("Download worker could not start") from error


@nonblocking_io
def enqueue_download(
    url,
    resolution,
    source,
    ws=None,
    force=False,
    playlist_mode="single",
    write_thumbnail=False,
    section_mode="full",
    _collection_context=None,
):
    job = create_queue_job(
        url,
        resolution,
        source,
        force=force,
        playlist_mode=playlist_mode,
        write_thumbnail=write_thumbnail,
        section_mode=section_mode,
    )
    if not job:
        raise ValueError("Invalid download request")

    with queue_operation_lock:
        require_usable_queue()
        if shutdown_event.is_set():
            raise StateError("Download service is stopping")
        if _collection_context:
            job = normalize_queue_job({
                **job,
                **{key: _collection_context[key] for key in ("collection_id", "batch_id", "target_relative_directory", "date_policy")},
                **{key: value for key, value in (_collection_context.get("request") or {}).items() if key in {"media_id", "extractor"}},
            })
            if not job:
                raise APIError("unsafe_path")
        if not force:
            duplicate_job = find_queued_duplicate(job)
            if duplicate_job:
                if _collection_context:
                    collections_service.bind_retry_to_job(_collection_context, duplicate_job["id"])
                return {
                    "queued": False,
                    "duplicate": True,
                    "duplicate_type": "queue",
                    "job": duplicate_job,
                }

            existing = None
            if job["playlist_mode"] == "single" and not _collection_context:
                existing = find_existing_download(
                    job["url"],
                    job["resolution"],
                    require_thumbnail=job["write_thumbnail"],
                    section_mode=job["section_mode"],
                )
            if existing:
                set_recent_preflight_receipt(existing, job)
                return {
                    "queued": False,
                    "duplicate": True,
                    "duplicate_type": "history",
                    "existing": existing,
                }

        storage = get_storage_status()
        if storage["blocking"]:
            return {
                "queued": False,
                "duplicate": False,
                "blocked": True,
                "code": "storage_critical",
                "storage": storage,
                "queue_count": dl_q.qsize(),
            }

        queue_position = dl_q.qsize() + 1
        if _collection_context:
            collections_service.reserve_retry(job, _collection_context)
        with queue_state_lock:
            write_queue_snapshot(
                normalize_queue_job(active_queue_job) if active_queue_job else None,
                pending_queue_jobs() + [job],
            )
        dl_q.put(job)

    start_download_thread_if_needed()
    download_manager.broadcast_to_all_clients(
        f"[QUEUE_UPDATED], {json.dumps({'queued_job_id': job['id']})}"
    )
    return {
        "queued": True,
        "duplicate": False,
        "job": public_queue_job(job, position=queue_position),
        "queue_count": queue_position,
    }

@nonblocking_io
def get_queued_downloads():
    queued_items = []
    for position, job in enumerate(pending_queue_jobs(), start=1):
        queued_items.append(public_queue_job(job, position=position))
    return queued_items


def build_queue_receipt(result, profile, client=""):
    result = result if isinstance(result, dict) else {}
    job = result.get("job") if isinstance(result.get("job"), dict) else None
    queue_position = job.get("position") if job else None
    queue_count = result.get("queue_count")
    if queue_count is None:
        queue_count = dl_q.qsize()

    if result.get("blocked"):
        storage = result.get("storage") if isinstance(result.get("storage"), dict) else {}
        return {
            "success": False,
            "queued": False,
            "duplicate": False,
            "blocked": True,
            "code": "storage_critical",
            "profile": profile,
            "queue_position": None,
            "queue_count": queue_count,
            "storage": storage,
            "params": {
                "free_bytes": storage.get("free_bytes"),
                "critical_bytes": storage.get("critical_bytes"),
            },
            "client": client or None,
            "msg": "Download storage is critically low",
        }

    if result.get("duplicate"):
        duplicate_type = result.get("duplicate_type")
        if duplicate_type == "queue":
            code = "duplicate_queue"
            msg = "Already in the NAS queue."
            if queue_position:
                msg = f"Already in the NAS queue at position {queue_position}."
        else:
            code = "duplicate_history"
            msg = "Already downloaded on this NAS."
        return {
            "success": True,
            "queued": False,
            "duplicate": True,
            "duplicate_type": duplicate_type,
            "code": code,
            "profile": profile,
            "queue_position": queue_position,
            "queue_count": queue_count,
            "existing": result.get("existing"),
            "job": job,
            "client": client or None,
            "msg": msg,
        }

    msg = f"Added {profile} to the NAS queue."
    if queue_position:
        msg = f"Added {profile} to the NAS queue at position {queue_position}."
    return {
        "success": True,
        "queued": True,
        "duplicate": False,
        "code": "queued",
        "profile": profile,
        "queue_position": queue_position,
        "queue_count": queue_count,
        "job": job,
        "client": client or None,
        "msg": msg,
    }

# single use global download manager
class GlobalDownloadManager:
    def __init__(self):
        self.history_lock = RLock()
        self.current_download = None  # presently active download information
        self.download_history = []  # history of download info
        self.connected_clients = set() #every websocket clients
        self.client_hubs = {}
        self.is_downloading = False
        self.process_lock = Lock()
        self.active_process = None
        self.active_process_job_id = None
        self.cancel_requested_job_id = None
        self.history_file = HISTORY_FILE
        self.load_history()
    
    @nonblocking_io
    def load_history(self):
        with self.history_lock:
            history = read_state(self.history_file, [])
            if not isinstance(history, list) or any(not isinstance(item, dict) for item in history):
                raise StateError("Invalid download history")
            upgraded = False
            for item in history:
                if "relative_path" not in item:
                    item["relative_path"] = get_relative_path(item)
                    upgraded = True
                if item.get("filepath") and item["filepath"] != item["relative_path"]:
                    item["filepath"] = item["relative_path"]
                    upgraded = True
            if upgraded:
                atomic_write_json(self.history_file, history)
            self.download_history = history
    
    @nonblocking_io
    def save_history(self):
        """Save history to file"""
        with self.history_lock:
            atomic_write_json(self.history_file, self.download_history)
    
    @nonblocking_io
    def clear_all_history(self):
        """Clear all history"""
        with queue_operation_lock:
            if self is download_manager:
                collections_service.observe_history(self.normalized_history())
            with self.history_lock:
                previous = self.download_history
                self.download_history = []
                try:
                    self.save_history()
                except (OSError, StateError):
                    self.download_history = previous
                    raise
        self.broadcast_to_all_clients("[HISTORY_CLEARED], all")
        return True
    
    @nonblocking_io
    def delete_history_item(self, uuid):
        """Delete a history item with a specific UUID"""
        with queue_operation_lock:
            if self is download_manager:
                collections_service.observe_history(self.normalized_history())
            with self.history_lock:
                previous = self.download_history
                self.download_history = [item for item in previous if item.get('uuid') != uuid]
                if len(self.download_history) == len(previous):
                    return False
                try:
                    self.save_history()
                except (OSError, StateError):
                    self.download_history = previous
                    raise
        self.broadcast_to_all_clients(f"[HISTORY_DELETED], {uuid}")
        return True

    def get_history_item(self, uuid):
        for item in self.download_history:
            if item.get('uuid') == uuid:
                return item
        return None

    @nonblocking_io
    def normalized_history(self):
        with self.history_lock:
            return [normalize_history_item(item) for item in self.download_history]

    @nonblocking_io
    def combined_history(self):
        normalized_history = self.normalized_history()
        known_ids = {item["uuid"] for item in normalized_history}
        known_paths = {item["relative_path"] for item in normalized_history if item["relative_path"]}
        service = globals().get("collections_service")
        if service and self is download_manager:
            for snapshot in service.media_snapshots():
                item = normalize_history_item(snapshot)
                if item["uuid"] in known_ids or (item["relative_path"] and item["relative_path"] in known_paths):
                    continue
                normalized_history.append(item)
                known_ids.add(item["uuid"])
                if item["relative_path"]:
                    known_paths.add(item["relative_path"])
        history_filenames = {
            item.get('relative_path')
            for item in normalized_history
            if item.get('relative_path')
        }
        mounted_files = [
            item
            for item in list_mounted_file_items()
            if item.get('relative_path') not in history_filenames
        ]
        return normalized_history + mounted_files

    @nonblocking_io
    def get_combined_history_item(self, item_uuid):
        for item in self.normalized_history():
            if item.get('uuid') == item_uuid:
                return item
        service = globals().get("collections_service")
        if service and self is download_manager:
            for item in service.media_snapshots():
                if item.get("uuid") == item_uuid:
                    return normalize_history_item(item)
        return get_mounted_file_item(item_uuid)
    
    def set_current_download(self, download_info):
        """Set the current download information"""
        with self.process_lock:
            self.active_process = None
            self.active_process_job_id = None
            self.cancel_requested_job_id = None
            self.current_download = download_info
            self.is_downloading = True
        self.broadcast_to_all_clients(f"[RESTORE_ACTIVE], {json.dumps(download_info)}")

    def attach_process(self, job_id, process):
        with self.process_lock:
            self.active_process = process
            self.active_process_job_id = job_id
            should_cancel = self.cancel_requested_job_id == job_id
        if should_cancel:
            terminate_process_group(process)

    def detach_process(self, job_id, process):
        with self.process_lock:
            if self.active_process is process and self.active_process_job_id == job_id:
                self.active_process = None
                self.active_process_job_id = None

    def request_active_cancel(self):
        with self.process_lock:
            current = self.current_download if isinstance(self.current_download, dict) else None
            job_id = str((current or {}).get("job_id") or (current or {}).get("uuid") or "")
            if not self.is_downloading or not job_id:
                return None
            already_requested = self.cancel_requested_job_id == job_id
            self.cancel_requested_job_id = job_id
            process = self.active_process if self.active_process_job_id == job_id else None
            previous_status = str(current.get("status") or "")
            phase = str(current.get("cancel_phase") or "")
            if phase not in {"preflight", "download"}:
                phase = "preflight" if previous_status in {"checking", "ready", "extracting_info"} else "download"
                current["cancel_phase"] = phase
            current["status"] = "canceling"
        if process and not already_requested:
            terminate_process_group(process)
        return {
            "job_id": job_id,
            "already_requested": already_requested,
            "phase": phase,
        }

    def cancellation_requested(self, job_id):
        with self.process_lock:
            return self.cancel_requested_job_id == job_id

    def consume_cancellation(self, job_id):
        with self.process_lock:
            if self.cancel_requested_job_id != job_id:
                return False
            self.cancel_requested_job_id = None
            return True

    def reset_active_runtime(self):
        with self.process_lock:
            self.active_process = None
            self.active_process_job_id = None
            self.cancel_requested_job_id = None
            self.current_download = None
            self.is_downloading = False
    
    def update_progress(self, progress):
        """Update progress and broadcast to all clients"""
        if self.current_download:
            self.current_download['progress'] = progress
            self.broadcast_to_all_clients(f"[PROGRESS], {progress}")
    
    def update_status(self, status):
        """Update status"""
        if self.current_download:
            self.current_download['status'] = status
            self.broadcast_to_all_clients(
                f"[ACTIVE_UPDATED], {json.dumps(self.current_download, ensure_ascii=False)}"
            )

    def update_current_download(self, **updates):
        if not self.current_download:
            return
        self.current_download.update(updates)
        self.broadcast_to_all_clients(
            f"[ACTIVE_UPDATED], {json.dumps(self.current_download, ensure_ascii=False)}"
        )

    def update_transfer_stats(self, speed, eta):
        """Update live transfer statistics and broadcast them to dashboard clients."""
        if not self.current_download:
            return
        self.current_download['speed'] = speed or ''
        self.current_download['eta'] = eta or ''
        stats = {"speed": speed or "", "eta": eta or ""}
        self.broadcast_to_all_clients(f"[TRANSFER], {json.dumps(stats)}")
    
    def send_message(self, message):
        """Send a message to all clients"""
        self.broadcast_to_all_clients(f"[MSG], {message}")
    
    def send_title(self, title):
        """Send title information"""
        if self.current_download:
            self.current_download['title'] = title
        self.broadcast_to_all_clients(f"[TITLE], {title}")
    
    def send_channel(self, channel):
        """Send channel information"""
        if self.current_download:
            self.current_download['channel'] = channel
        self.broadcast_to_all_clients(f"[CHANNEL], {channel}")
    
    def send_thumbnail(self, thumbnail):
        """Send thumbnail information"""
        if self.current_download:
            self.current_download['thumbnail'] = thumbnail
        self.broadcast_to_all_clients(f"[THUMBNAIL], {thumbnail}")
    
    def _matching_history_index(self, candidate):
        candidate = normalize_history_item(candidate)
        if not candidate.get("file_exists"):
            return None

        candidate_filename = str(candidate.get("relative_path") or "")
        for index, existing in enumerate(self.download_history):
            existing = normalize_history_item(existing)
            if not existing.get("file_exists"):
                continue

            same_file = bool(
                candidate_filename
                and candidate_filename == str(existing.get("relative_path") or "")
            )
            if same_file:
                return index
        return None

    def complete_downloads(self, completion_items):
        with queue_operation_lock:
            with self.history_lock:
                previous = list(self.download_history)
                try:
                    completed = self._complete_downloads(completion_items)
                except (OSError, StateError):
                    self.download_history = previous
                    raise
            if self is download_manager:
                collections_service.observe_history(completed)
            return completed

    def _complete_downloads(self, completion_items):
        """Persist one queue job's outputs while de-duplicating physical files."""
        completed = []
        for completion_info in completion_items:
            history_item = dict(completion_info or {})
            history_item.setdefault('uuid', str(uuid.uuid4()))
            history_item.setdefault('timestamp', datetime.now().isoformat())
            history_item = normalize_history_item(history_item)

            existing_index = self._matching_history_index(history_item)
            if existing_index is not None:
                existing = normalize_history_item(self.download_history[existing_index])
                history_item['uuid'] = existing['uuid']
                history_item['timestamp'] = existing.get('timestamp') or history_item['timestamp']
                self.download_history[existing_index] = history_item
            else:
                self.download_history.append(history_item)
            completed.append(history_item)

        self.save_history()
        self.reset_active_runtime()
        for history_item in completed:
            complete_data = normalize_history_item(history_item)
            event = "[COMPLETE]" if complete_data.get("status") == "completed" else "[HISTORY_UPDATED]"
            message = f"{event}, {json.dumps(complete_data, ensure_ascii=False)}"
            self.broadcast_to_all_clients(message)

        return completed

    def complete_download(self, completion_info):
        """Handle a single download completion."""
        completed = self.complete_downloads([completion_info])
        return completed[0] if completed else None

    def skip_duplicate(self, existing, job):
        """Finish an active queue item without downloading an existing NAS file again."""
        if self is download_manager:
            collections_service.record_job_end(
                job, "completed", existing={**existing, "upload_date": job.get("upload_date") or existing.get("upload_date")},
            )
        payload = set_recent_preflight_receipt(existing, job)
        if self.current_download:
            self.current_download["status"] = "duplicate"
        self.reset_active_runtime()
        self.broadcast_to_all_clients(f"[DUPLICATE], {json.dumps(payload, ensure_ascii=False)}")

    def cancel_preflight(self, job):
        """Undo a queued request before file transfer without adding a history row."""
        if self is download_manager:
            collections_service.record_job_end(job, "canceled", "preflight_canceled")
        payload = {"job": public_queue_job(job)}
        self.reset_active_runtime()
        self.broadcast_to_all_clients(
            f"[PREFLIGHT_CANCELED], {json.dumps(payload, ensure_ascii=False)}"
        )

    def defer_current_download(self):
        """Release transient UI state while queue persistence retains the job for restart."""
        self.reset_active_runtime()
    
    def add_client(self, ws):
        """Add a new client connection"""
        from gevent import Greenlet, get_hub, getcurrent
        from gevent.lock import Semaphore

        if isinstance(getcurrent(), Greenlet):
            self.client_hubs[ws] = (get_hub(), get_ident(), Semaphore())
        self.connected_clients.add(ws)
        print(f"Client connected. Total clients: {len(self.connected_clients)}")

        # Restore current download if it exists
        if self.current_download:
            safe_websocket_send(ws, f"[RESTORE_ACTIVE], {json.dumps(self.current_download)}")
        
        # Send all history (reload from file to ensure the latest state)
        self.load_history()  # Reload latest history
        combined_history = self.combined_history()
        print(f"Sending {len(combined_history)} history items to new client")

        # Send all history items individually
        for idx, history_item in enumerate(combined_history):
            try:
                safe_websocket_send(ws, f"[RESTORE_HISTORY], {json.dumps(history_item)}")
                print(f"Sent history item {idx}")
            except Exception as e:
                print(f"Error sending history item {idx}: {sanitize_diagnostic_text(e)}")

        # Send history restore complete signal
        safe_websocket_send(ws, "[HISTORY_RESTORE_COMPLETE], done")

    def remove_client(self, ws):
        """Remove client connection"""
        self.connected_clients.discard(ws)
        self.client_hubs.pop(ws, None)
        print(f"Client disconnected. Total clients: {len(self.connected_clients)}")
    
    def broadcast_to_all_clients(self, message):
        """Broadcast message to all connected clients"""
        disconnected_clients = set()
        
        for client in list(self.connected_clients):
            if not safe_websocket_send(client, message):
                disconnected_clients.add(client)

        # Remove disconnected clients
        for client in disconnected_clients:
            self.connected_clients.discard(client)
            self.client_hubs.pop(client, None)
    
    def get_current_state(self):
        """Return current state"""
        return {
            'current_download': self.current_download,
            'is_downloading': self.is_downloading,
            'recent_history': self.download_history[-10:],
            'connected_clients': len(self.connected_clients),
            'queue_restore_count': queue_restore_count,
        }

# Initialize global download manager
download_manager = GlobalDownloadManager()

class WSAddr:
    def __init__(self):
        self.wsClassVal = None

# Create WSAddr instance
ws_addr = WSAddr()

# WebSocket safe send function
def safe_websocket_send(ws, message):
    """Send message only if WebSocket is connected"""
    if ws is None:
        return False
    owner = download_manager.client_hubs.get(ws)
    if owner and get_ident() != owner[1]:
        def deliver():
            if not safe_websocket_send(ws, message):
                download_manager.remove_client(ws)

        def schedule():
            from gevent import spawn
            spawn(deliver)

        try:
            owner[0].loop.run_callback_threadsafe(schedule)
            return True
        except RuntimeError:
            return False
    
    try:
        # Check WebSocket connection status
        if hasattr(ws, 'closed') and ws.closed:
            return False
        
        if owner:
            with owner[2]:
                ws.send(message)
        else:
            ws.send(message)
        return True
    except WebSocketError:
        return False
    except Exception:
        return False

app = Bottle()
port = 8080
proxy = ""


@post('/locale')
def set_locale():
    locale = normalize_locale(request.forms.get("locale"))
    next_path = safe_next_path(request.forms.get("next"), "/")
    if locale:
        response.set_cookie(
            LOCALE_COOKIE,
            locale,
            path="/",
            samesite="lax",
            secure=cookie_secure_enabled(),
            max_age=365 * 24 * 60 * 60,
        )
    redirect(next_path)


@get('/')
def dl_queue_list():        
    """Displays the login page or redirects to terms page if not accepted."""
    next_path = safe_next_path(request.query.get("next"), "/youtube-dl")
    try:
        data = load_auth_data()
        if data.get("TERMS_ACCEPTED") != "Y":
            redirect("/terms?next=" + quote(next_path, safe=""))
    except Exception as e:
        print(f"Error checking terms acceptance: {sanitize_diagnostic_text(e)}")
        redirect("/terms?next=" + quote(next_path, safe=""))
        
    locale_next = "/?next=" + quote(next_path, safe="")
    return render_localized_template(
        "./static/template/login.tpl",
        msg_key="",
        app_version=APP_VERSION,
        next_path=next_path,
        locale_next=locale_next,
    )

@get('/login', method='POST')
def dl_queue_login():
    data = load_auth_data()
    req_id = request.forms.get("id")
    req_pw = request.forms.get("myPw")
    next_path = safe_next_path(request.forms.get("next"), "/youtube-dl")

    credentials_configured = bool(data.get("MY_ID") and data.get("MY_PW"))
    if credentials_configured and req_id and req_pw and hmac.compare_digest(str(req_id), str(data["MY_ID"])) and hmac.compare_digest(
        str(req_pw), str(data["MY_PW"])
    ):
        response.set_cookie(
            "account",
            req_id,
            secret=data.get("SECRET_KEY"),
            path="/",
            httponly=True,
            samesite="lax",
            secure=cookie_secure_enabled(),
        )
        redirect(next_path)

    locale_next = "/?next=" + quote(next_path, safe="")
    return render_localized_template(
        "./static/template/login.tpl",
        msg_key="login.invalid",
        app_version=APP_VERSION,
        next_path=next_path,
        locale_next=locale_next,
    )

@get('/logout')
def dl_queue_logout():
    response.delete_cookie("account", path="/")
    redirect("/")

@route('/terms')
def terms_page():
    """Displays the terms of use page."""
    next_path = safe_next_path(request.query.get("next"), "/youtube-dl")
    locale_next = "/terms?next=" + quote(next_path, safe="")
    return render_localized_template(
        'static/template/terms.tpl',
        next_path_json=json.dumps(next_path),
        app_version=APP_VERSION,
        locale_next=locale_next,
    )

@post('/accept-terms')
def accept_terms():
    """Persist terms acceptance and the signed-cookie secret."""
    try:
        data = load_auth_data()
        save_app_state({"TERMS_ACCEPTED": "Y", "SECRET_KEY": data["SECRET_KEY"]})
        return {'success': True}
    except Exception as e:
        print(f"Error accepting terms: {sanitize_diagnostic_text(e)}")
        return {'success': False}
    

@get('/youtube-dl')
def dl_queue_main():
    next_path = request.path + ("?" + request.query_string if request.query_string else "")
    data = load_auth_data()
    if data.get("TERMS_ACCEPTED") != "Y":
        redirect("/terms?next=" + quote(next_path, safe=""))

    if is_cookie_authenticated(data):
        shared_url = ""
        if request.query.get("shared") == "review":
            shared_url = consume_share_review(data)
        return render_localized_template(
            "./static/template/index.tpl",
            userNm=data["MY_ID"],
            app_version=APP_VERSION,
            locale_next=next_path,
            shared_url_json=json.dumps(shared_url),
            page="downloads",
            collection_id="",
        )

    redirect("/?next=" + quote(next_path, safe=""))


def render_dashboard_page(page, collection_id=""):
    data = load_auth_data()
    next_path = safe_next_path(request.path)
    if data.get("TERMS_ACCEPTED") != "Y":
        redirect("/terms?next=" + quote(next_path, safe=""))
    if not is_cookie_authenticated(data):
        redirect("/?next=" + quote(next_path, safe=""))
    return render_localized_template(
        "./static/template/index.tpl",
        page=page,
        collection_id=collection_id,
        userNm=data["MY_ID"],
        app_version=APP_VERSION,
        locale_next=next_path,
        shared_url_json='""',
    )


@get("/youtube-dl/collections")
@get("/youtube-dl/collections/<collection_id>")
def collections_page(collection_id=""):
    return render_dashboard_page("collections", collection_id)


@get("/youtube-dl/ai-connect")
def ai_connect_page():
    return render_dashboard_page("ai-connect")


def bearer_authenticated():
    authorization = request.headers.get("Authorization", "")
    parts = authorization.split()
    if len(parts) != 2 or parts[0].casefold() != "bearer":
        return False
    supplied = parts[1]
    if API_TOKEN and hmac.compare_digest(supplied.encode("utf-8"), API_TOKEN.encode("utf-8")):
        return True
    return connections_store.validate(supplied)


def validate_browser_origin():
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return
    fetch_site = request.headers.get("Sec-Fetch-Site", "").casefold()
    if fetch_site == "cross-site":
        raise APIError("cross_origin_request", 403)
    origin = request.headers.get("Origin") or request.headers.get("Referer")
    if not origin:
        if fetch_site == "same-site":
            raise APIError("cross_origin_request", 403)
        return
    try:
        supplied = urlsplit(origin)
        expected = urlsplit(request.url)
        source = (supplied.scheme.lower(), supplied.hostname, supplied.port or (443 if supplied.scheme == "https" else 80))
        target = (expected.scheme.lower(), expected.hostname, expected.port or (443 if expected.scheme == "https" else 80))
        if supplied.username or supplied.password or source != target:
            raise APIError("cross_origin_request", 403)
    except ValueError as error:
        raise APIError("cross_origin_request", 403) from error


def api_v1(cookie_only=False, bearer_only=False):
    def decorate(handler):
        @wraps(handler)
        def guarded(*args, **kwargs):
            response.set_header("Cache-Control", "no-store")
            response.set_header("Pragma", "no-cache")
            try:
                cookie = False if bearer_only else is_cookie_authenticated()
                if cookie_only:
                    authenticated = cookie
                else:
                    authenticated = cookie or bearer_authenticated()
                if not authenticated:
                    raise APIError("unauthorized", 401)
                if cookie:
                    validate_browser_origin()
                return handler(*args, **kwargs)
            except APIError as error:
                response.status = error.status
                return {"success": False, "code": error.code, "msg": error.code}
            except (StateError, OSError):
                response.status = 503
                return {"success": False, "code": "state_unavailable", "msg": "state_unavailable"}
        return guarded
    return decorate


def v1_payload():
    if request.content_type != "application/json":
        raise APIError("json_body_required", 415)
    if not isinstance(request.json, dict):
        raise APIError("invalid_request")
    payload = request.json
    reject_client_paths(payload)
    return payload


@get("/youtube-dl/api/v1/capabilities")
@api_v1()
def v1_capabilities():
    return {
        "api_version": "1",
        "batch_limit": batch_limit(),
        "plan_ttl_seconds": PLAN_TTL_SECONDS,
        "preview_timeout_seconds": PREVIEW_TIMEOUT_SECONDS,
        "preview_work_timeout_seconds": PREVIEW_WORK_TIMEOUT_SECONDS,
        "commit_timeout_seconds": COMMIT_TIMEOUT_SECONDS,
        "features": ["collections", "preview_commit", "date_policy", "connection_tokens", "safe_relative_paths"],
        "direct_urls_only": True,
        "unknown_dates_require_approval": True,
    }


@get("/youtube-dl/api/v1/profiles")
@api_v1()
def v1_profiles():
    profiles = [
        "best", "compatible-mp4", "2160p", "1440p", "1080p", "720p", "480p", "360p",
        "audio-m4a", "audio-mp3", "audio-opus", "audio", "vtt|en", "srt|en", "vtt|ko", "srt|ko",
    ]
    return {"profiles": [{"id": profile, "download_type": get_download_type(profile)} for profile in profiles]}


@get("/youtube-dl/api/v1/library")
@api_v1()
def v1_library():
    download_manager.load_history()
    collections_service.reconcile()
    items = download_manager.combined_history()
    query = str(request.query.get("q") or "").strip().casefold()
    if query:
        items = [
            item for item in items
            if query in " ".join(str(item.get(key) or "") for key in ("title", "channel", "url", "relative_path")).casefold()
        ]
    try:
        limit = min(500, max(1, int(request.query.get("limit") or 200)))
    except ValueError:
        raise APIError("invalid_limit")
    return {"items": items[:limit], "total": len(items)}


@get("/youtube-dl/api/v1/downloads")
@api_v1()
def v1_downloads():
    return get_download_snapshot()


@nonblocking_io
def get_download_snapshot():
    with queue_state_lock:
        active = public_queue_job(active_queue_job) if active_queue_job else None
    return {
        "queue": get_queued_downloads(),
        "active": download_manager.current_download or active,
        "storage": get_storage_status(),
    }


@post("/youtube-dl/api/v1/downloads")
@api_v1()
def v1_enqueue():
    payload = v1_payload()
    if set(payload) - {"url", "resolution", "force", "playlist_mode", "write_thumbnail", "section_mode", "client", "client_version"}:
        raise APIError("invalid_download_options")
    url, resolution = payload.get("url"), payload.get("resolution", "best")
    for error in (
        validate_download_request(url, resolution),
        validate_playlist_request(url, payload.get("playlist_mode"), explicit=True),
        validate_section_request(url, payload.get("section_mode")),
    ):
        if error:
            raise APIError(get_error_details(error)[0] or "invalid_request")
    result = enqueue_download(
        url, resolution, "api",
        force=parse_boolean(payload.get("force")),
        playlist_mode=normalize_playlist_mode(payload.get("playlist_mode"), url),
        write_thumbnail=parse_boolean(payload.get("write_thumbnail")),
        section_mode=normalize_section_mode(payload.get("section_mode")),
    )
    receipt = build_queue_receipt(result, resolution, client="api-v1")
    if receipt.get("blocked"):
        response.status = 507
    return receipt


@get("/youtube-dl/api/v1/collections")
@api_v1()
def v1_collections():
    return {"collections": collections_service.list_collections()}


@get("/youtube-dl/api/v1/collections/<collection_id>")
@api_v1()
def v1_collection(collection_id):
    return collections_service.get_collection(collection_id)


@route("/youtube-dl/api/v1/collections/<collection_id>", method="PATCH")
@api_v1()
def v1_update_collection(collection_id):
    return {"collection": collections_service.update_collection(collection_id, v1_payload())}


@route("/youtube-dl/api/v1/collections/<collection_id>", method="DELETE")
@api_v1()
def v1_delete_collection(collection_id):
    collections_service.delete_collection(collection_id)
    return {"success": True}


@post("/youtube-dl/api/v1/plans")
@api_v1()
def v1_plan_preview():
    from gevent import Timeout

    payload = v1_payload()
    deadline = time.monotonic() + PREVIEW_WORK_TIMEOUT_SECONDS
    with Timeout(PREVIEW_WORK_TIMEOUT_SECONDS, APIError("preview_timeout", 504)):
        return {"plan": collections_service.preview(payload, deadline=deadline)}


@get("/youtube-dl/api/v1/plans/<plan_id>")
@api_v1()
def v1_plan(plan_id):
    return {"plan": collections_service.get_plan(plan_id)}


@post("/youtube-dl/api/v1/plans/<plan_id>/commit")
@api_v1()
def v1_commit_plan(plan_id):
    return collections_service.commit(plan_id, v1_payload())


@get("/youtube-dl/api/v1/batches/<batch_id>")
@api_v1()
def v1_batch(batch_id):
    return {"batch": collections_service.get_batch(batch_id)}


@get("/youtube-dl/api/v1/connections")
@api_v1(cookie_only=True)
def v1_connections():
    return {"connections": connections_store.list()}


@post("/youtube-dl/api/v1/connections")
@api_v1(cookie_only=True)
def v1_create_connection():
    payload = v1_payload()
    if set(payload) - {"name"}:
        raise APIError("invalid_connection")
    return connections_store.create(payload.get("name", ""))


@route("/youtube-dl/api/v1/connections/<connection_id>", method="DELETE")
@api_v1(cookie_only=True)
def v1_revoke_connection(connection_id):
    connections_store.revoke(connection_id)
    return {"success": True}


@get("/youtube-dl/api/v1/mcp/auth")
@api_v1(bearer_only=True)
def v1_mcp_auth():
    return {"authenticated": True}

@get('/health')
def health_check():
    response.content_type = "application/json"
    storage = get_storage_status()
    unavailable = shutdown_event.is_set() or worker_failed_event.is_set()
    response.status = 503 if unavailable else 200
    response.set_header("Cache-Control", "no-store")
    return {
        "status": "unavailable" if unavailable else "ok",
        "app": "youtube-dl-nas",
        "version": APP_VERSION,
        "queue_count": dl_q.qsize(),
        "queue": {
            "persistent": True,
            "restored_count": queue_restore_count,
            "state_file": os.path.basename(QUEUE_STATE_FILE),
            "worker_state": "failed" if worker_failed_event.is_set() else ("stopping" if unavailable else "ready"),
        },
        "storage": storage,
        "subtitle_qa": {
            "available": get_nlptutti_version() != "unavailable",
            "nlptutti_version": get_nlptutti_version(),
        },
    }

@get('/manifest.webmanifest')
def pwa_manifest():
    response.content_type = "application/manifest+json"
    return static_file("manifest.webmanifest", root="./static/pwa")

@get('/sw.js')
def pwa_service_worker():
    response.content_type = "application/javascript"
    response.set_header("Service-Worker-Allowed", "/")
    return static_file("sw.js", root="./static/pwa")

@post('/youtube-dl/share-target')
def share_target():
    shared_url = extract_shared_url(
        request.forms.get("url"),
        request.forms.get("text"),
        request.forms.get("title"),
    )
    if not shared_url:
        redirect("/youtube-dl?shared=missing")

    data = load_auth_data()
    if data.get("TERMS_ACCEPTED") != "Y" or not is_cookie_authenticated(data):
        set_pending_share_cookie(shared_url, data)
        redirect("/?next=" + quote("/youtube-dl/share-target/complete", safe=""))

    queue_shared_url(shared_url)

@get('/youtube-dl/share-target/complete')
def complete_pending_share():
    data = load_auth_data()
    if data.get("TERMS_ACCEPTED") != "Y" or not is_cookie_authenticated(data):
        redirect("/?next=" + quote(request.path, safe=""))

    shared_url = request.get_cookie("pending_share", secret=data.get("SECRET_KEY"))
    response.delete_cookie("pending_share", path="/")
    if not shared_url:
        redirect("/youtube-dl?shared=missing")

    queue_shared_url(shared_url)


@get('/youtube-dl/preferences')
def get_preferences():
    data, error_response = require_cookie_auth()
    if error_response:
        return error_response
    return {
        "success": True,
        "share_profile": get_share_profile(data),
    }


@post('/youtube-dl/preferences')
def update_preferences():
    data, error_response = require_cookie_auth()
    if error_response:
        return error_response

    payload = get_request_json()
    requested_profile = str(payload.get("share_profile") or "").strip().lower()
    if requested_profile not in SHARE_PROFILES:
        return json_error("Unsupported mobile share profile", 400)
    set_share_profile_cookie(requested_profile, data)
    return {
        "success": True,
        "share_profile": requested_profile,
    }

@get('/youtube-dl/static/<filename:path>')
def server_static(filename):
    return static_file(filename, root='./static')

@get('/youtube-dl/q', method='GET')
def q_size():
    _, error_response = require_cookie_auth()
    if error_response:
        return error_response
    queued_items = get_queued_downloads()
    return {
        "success": True,
        "size": json.dumps(queued_items),
        "items": queued_items,
        "count": len(queued_items),
    }

@get('/youtube-dl/status', method='GET')
def get_download_status():
    """Return dashboard status without changing the download queue API."""
    _, error_response = require_cookie_auth()
    if error_response:
        return error_response

    current_download = None
    if isinstance(download_manager.current_download, dict):
        current_download = dict(download_manager.current_download)
        start_time = current_download.get('start_time')
        if start_time:
            current_download['elapsed_seconds'] = max(0, int(time.time() - start_time))

    queued_items = get_queued_downloads()
    return {
        "success": True,
        "is_downloading": download_manager.is_downloading,
        "current_download": current_download,
        "queue_count": len(queued_items),
        "queue": queued_items,
        "connected_clients": len(download_manager.connected_clients),
        "storage": get_storage_status(),
        "preflight_receipt": get_recent_preflight_receipt(),
    }

@get('/youtube-dl/q', method='POST')
def q_put():
    _, error_response = require_cookie_auth()
    if error_response:
        return error_response

    payload = get_request_json()
    try:
        reject_client_paths(payload)
    except APIError as error:
        response.status = 400
        return {"success": False, "code": error.code, "msg": error.code}
    url = payload.get("url")
    resolution = payload.get("resolution")
    force = parse_boolean(payload.get("force"))
    playlist_mode = payload.get("playlist_mode")
    write_thumbnail = parse_boolean(payload.get("write_thumbnail"))
    section_mode = payload.get("section_mode")

    validation_error = validate_download_request(url, resolution)
    if validation_error:
        return json_error(validation_error, 400)
    playlist_error = validate_playlist_request(url, playlist_mode, explicit=True)
    if playlist_error:
        return json_error(playlist_error, 400, {
            "playlist_kind": classify_playlist_url(url),
            "options": ["first10", "all"],
        })
    section_error = validate_section_request(url, section_mode)
    if section_error:
        return json_error(section_error, 400)

    result = enqueue_download(
        url,
        resolution,
        "web",
        ws_addr.wsClassVal,
        force=force,
        playlist_mode=normalize_playlist_mode(playlist_mode, url),
        write_thumbnail=write_thumbnail,
        section_mode=normalize_section_mode(section_mode),
    )
    receipt = build_queue_receipt(result, resolution, client="web")
    if receipt.get("blocked"):
        response.status = 507
    if receipt["queued"]:
        download_manager.send_message('We received your download. Please wait.')
    return receipt


@post('/youtube-dl/share/context')
def share_context():
    payload = get_request_json()
    data = load_auth_data()
    if not is_api_authenticated(payload, data):
        return json_error("Invalid password, account, or API token.", 403)

    requested_profile = payload.get("profile") or payload.get("resolution") or "best"
    normalized_profile = normalize_api_share_profile(requested_profile, default=None, allow_ask=True)
    if not normalized_profile:
        return json_error("Unsupported mobile share profile", 400, {
            "profiles": sorted(SHARE_PROFILES),
        })

    context = build_share_context(
        payload.get("url"),
        payload.get("text"),
        payload.get("title"),
        profile=normalized_profile,
    )
    if not context["url"]:
        if parse_boolean(payload.get("soft_errors")):
            return {
                "success": False,
                "code": "url_required",
                "msg": "URL is required",
                **context,
            }
        return json_error("URL is required", 400)

    return {
        "success": True,
        "code": "share_context",
        **context,
        "profiles": ["best", "compatible-mp4", "1080p", "720p", "audio-mp3", "audio-m4a", "audio-opus"],
        "playlist_options": ["first10", "all"] if context["playlist_kind"] else [],
        "timestamp_options": ["full", "from_timestamp"] if context["timestamp_seconds"] else ["full"],
    }

@get('/youtube-dl/rest', method='POST')
def q_put_rest():
    payload = get_request_json()
    url = payload.get("url")
    requested_resolution = payload.get("resolution")
    force = parse_boolean(payload.get("force"))
    playlist_mode = payload.get("playlist_mode")
    write_thumbnail = parse_boolean(payload.get("write_thumbnail"))
    section_mode = payload.get("section_mode")
    client = re.sub(r"[^a-zA-Z0-9._-]", "", str(payload.get("client") or ""))[:64]
    client_version = re.sub(r"[^a-zA-Z0-9._-]", "", str(payload.get("client_version") or ""))[:32]

    data = load_auth_data()
    if not is_api_authenticated(payload, data):
        return json_error("Invalid password, account, or API token.", 403)
    try:
        reject_client_paths(payload)
    except APIError as error:
        response.status = 400
        return {"success": False, "code": error.code, "msg": error.code}

    if not isinstance(requested_resolution, str) or not requested_resolution.strip():
        return json_error("Resolution is required", 400)
    resolution = SHARE_PROFILE_ALIASES.get(
        requested_resolution.strip().lower(),
        requested_resolution.strip(),
    )
    if resolution == "ask":
        return json_error("Unsupported mobile share profile", 400, {
            "profiles": ["best", "compatible-mp4", "1080p", "720p", "audio-mp3", "audio-m4a", "audio-opus"],
        })

    validation_error = validate_download_request(url, resolution)
    if validation_error:
        return json_error(validation_error, 400)
    playlist_error = validate_playlist_request(url, playlist_mode, explicit=True)
    if playlist_error:
        return json_error(playlist_error, 400, {
            "playlist_kind": classify_playlist_url(url),
            "options": ["first10", "all"],
        })
    section_error = validate_section_request(url, section_mode)
    if section_error:
        return json_error(section_error, 400, {
            "timestamp_seconds": extract_shared_timestamp(url) or None,
            "options": ["full", "from_timestamp"],
        })

    result = enqueue_download(
        url,
        resolution,
        "api",
        "",
        force=force,
        playlist_mode=normalize_playlist_mode(playlist_mode, url),
        write_thumbnail=write_thumbnail,
        section_mode=normalize_section_mode(section_mode),
    )
    receipt = build_queue_receipt(result, resolution, client=client)
    if receipt.get("blocked"):
        response.status = 507
    receipt["client_version"] = client_version or None
    receipt["Remaining downloading count"] = json.dumps(receipt["queue_count"])
    return receipt


@post('/youtube-dl/q/active/cancel')
def cancel_active_download():
    _, error_response = require_cookie_auth()
    if error_response:
        return error_response

    cancellation = download_manager.request_active_cancel()
    if not cancellation:
        return json_error("No active download to cancel", 409)
    return {
        "success": True,
        "code": (
            "preflight_cancellation_requested"
            if cancellation["phase"] == "preflight"
            else "cancellation_requested"
        ),
        "job_id": cancellation["job_id"],
        "already_requested": cancellation["already_requested"],
        "phase": cancellation["phase"],
        "msg": (
            "Queued download undo requested"
            if cancellation["phase"] == "preflight"
            else "Active download cancellation requested"
        ),
    }

@post('/youtube-dl/q/<job_id>/remove')
def remove_queue_item(job_id):
    _, error_response = require_cookie_auth()
    if error_response:
        return error_response

    removed = remove_queued_job(job_id)
    if not removed:
        return json_error("Queued download not found or already active", 404)
    return {
        "success": True,
        "removed": removed,
        "msg": "Queued download removed",
    }

# History deletion API
@get('/youtube-dl/history/clear', method='POST')
def clear_history():
    """Clear all history"""    
    _, error_response = require_cookie_auth()
    if error_response:
        return error_response

    success = download_manager.clear_all_history()
    if success:
        return {"success": True, "msg": "History rows cleared. Downloaded files were kept."}
    else:
        return {"success": False, "msg": "Failed to clear history"}

@get('/youtube-dl/history/delete/<uuid>', method='POST')
def delete_history_item(uuid):
    """Delete a history item with a specific UUID"""
    _, error_response = require_cookie_auth()
    if error_response:
        return error_response

    success = download_manager.delete_history_item(uuid)
    if success:
        print(f"Removed from download manager: {success}")
        return {"success": True, "msg": "History item deleted successfully"}
    else:
        return json_error("History item not found", 404)

@get('/youtube-dl/history/delete-file/<uuid>', method='POST')
def delete_history_file(uuid):
    """Delete the physical file for a history item, then remove related history rows."""
    _, error_response = require_cookie_auth()
    if error_response:
        return error_response

    item = download_manager.get_history_item(uuid)
    is_mounted_file = False
    if not item:
        item = download_manager.get_combined_history_item(uuid)
        is_mounted_file = bool(item)

    if not item:
        return json_error("History item not found", 404)

    normalized = normalize_history_item(item)
    file_path = safe_downfolder_path(normalized.get('relative_path'))
    if not file_path:
        return json_error("Valid file path not found", 404)
    if not os.path.isfile(file_path):
        return json_error("Physical file not found", 404)

    try:
        delete_media_file(DOWNFOLDER_DIR, normalized["relative_path"])
    except Exception as e:
        print(f"Failed to delete file: {sanitize_diagnostic_text(e)}")
        return json_error("Failed to delete physical file", 500)

    deleted_sidecars = []
    thumbnail_filename = normalized.get("thumbnail_file")
    thumbnail_path = safe_downfolder_path(thumbnail_filename)
    if thumbnail_path and os.path.isfile(thumbnail_path):
        try:
            delete_media_file(DOWNFOLDER_DIR, thumbnail_filename)
            deleted_sidecars.append(thumbnail_filename)
        except OSError as error:
            print(f"Failed to delete thumbnail sidecar: {sanitize_diagnostic_text(error)}")

    if is_mounted_file:
        related_uuids = [uuid]
        download_manager.broadcast_to_all_clients(f"[HISTORY_DELETED], {uuid}")
    else:
        related_uuids = [
            history_item.get('uuid')
            for history_item in list(download_manager.download_history)
            if get_relative_path(history_item) == normalized.get('relative_path')
        ]
        for history_uuid in related_uuids:
            if history_uuid:
                download_manager.delete_history_item(history_uuid)

    return {
        "success": True,
        "msg": "File and related history items deleted",
        "deleted_uuids": related_uuids,
        "deleted_sidecars": deleted_sidecars,
    }

@get('/youtube-dl/history/retry/<uuid>', method='POST')
def retry_history_item(uuid):
    """Queue a previous history item again."""
    _, error_response = require_cookie_auth()
    if error_response:
        return error_response

    item = download_manager.get_history_item(uuid)
    if not item:
        item = download_manager.get_combined_history_item(uuid)
    if not item:
        return json_error("History item not found", 404)

    collection_context = collections_service.retry_context(item)
    retry_request = item
    if collection_context and validate_download_request(item.get("url"), item.get("resolution"), resolve_source=False):
        retry_request = collection_context.get("request") or item
    url = retry_request.get("url")
    resolution = retry_request.get("resolution")
    validation_error = validate_download_request(url, resolution)
    if validation_error:
        return json_error(validation_error, 400)

    extra_options = {"_collection_context": collection_context} if collection_context else {}
    result = enqueue_download(
        url,
        resolution,
        "web",
        ws_addr.wsClassVal,
        playlist_mode=normalize_playlist_mode(retry_request.get("playlist_mode"), url),
        write_thumbnail=parse_boolean(retry_request.get("write_thumbnail")),
        section_mode=normalize_section_mode(retry_request.get("section_mode")),
        **extra_options,
    )
    receipt = build_queue_receipt(result, resolution, client="web")
    if receipt.get("blocked"):
        response.status = 507
    elif receipt.get("queued"):
        download_manager.send_message('We received your retry request. Please wait.')
        receipt["msg"] = "Download queued again"
    receipt["Remaining downloading count"] = json.dumps(receipt["queue_count"])
    return receipt

@get('/youtube-dl/history', method='GET')
def get_history():
    """Retrieve history"""
    _, error_response = require_cookie_auth()
    if error_response:
        return error_response

    download_manager.load_history()
    combined_history = download_manager.combined_history()
    
    return {
        "success": True, 
        "history": combined_history,
        "total": len(combined_history)
    }

@post('/youtube-dl/subtitle-qa/<uuid>')
def subtitle_qa(uuid):
    """Compare a stored subtitle file with a user-supplied reference transcript."""
    _, error_response = require_cookie_auth()
    if error_response:
        return error_response

    payload = get_request_json()
    reference = payload.get("reference")
    if not isinstance(reference, str) or not reference.strip():
        return json_error("Reference transcript is required", 400)
    if len(reference) > SUBTITLE_QA_MAX_REFERENCE_CHARS:
        return json_error(f"Reference transcript exceeds {SUBTITLE_QA_MAX_REFERENCE_CHARS} characters", 413)

    download_manager.load_history()
    item = download_manager.get_combined_history_item(uuid)
    if not item:
        return json_error("Subtitle history item not found", 404)

    normalized = normalize_history_item(item)
    filename = normalized.get("filename", "")
    extension = os.path.splitext(filename)[1].lower()
    if normalized.get("download_type") != "subtitle" or extension not in SUBTITLE_EXTENSIONS:
        return json_error("Subtitle QA supports SRT, VTT, ASS, and SSA files", 400)

    file_path = safe_downfolder_path(normalized["relative_path"])
    if not file_path or not os.path.isfile(file_path):
        return json_error("Subtitle file not found", 404)
    if os.path.getsize(file_path) > SUBTITLE_QA_MAX_FILE_BYTES:
        return json_error("Subtitle file is too large to analyze", 413)

    try:
        with open_media_file(DOWNFOLDER_DIR, normalized["relative_path"]) as subtitle_file:
            contents = subtitle_file.read(SUBTITLE_QA_MAX_FILE_BYTES + 1)
            if len(contents) > SUBTITLE_QA_MAX_FILE_BYTES:
                return json_error("Subtitle file is too large to analyze", 413)
            transcription = extract_subtitle_text(contents.decode("utf-8-sig", errors="replace"), extension)
    except (OSError, APIError) as error:
        print(f"Failed to read subtitle file for QA: {sanitize_diagnostic_text(error)}")
        return json_error("Subtitle file could not be read", 500)

    if not transcription:
        return json_error("No subtitle text was found in this file", 422)

    try:
        result = analyze_subtitle_text(reference, transcription, normalize_qa_keywords(payload.get("keywords")))
    except RuntimeError:
        return json_error("Subtitle QA is unavailable because nlptutti is not installed", 503)
    except (TypeError, ValueError) as error:
        print(f"Subtitle QA input error: {sanitize_diagnostic_text(error)}")
        return json_error("Subtitle QA could not analyze this transcript", 422)

    return {
        "success": True,
        "file": {
            "uuid": normalized.get("uuid"),
            "title": normalized.get("title") or os.path.splitext(filename)[0],
            "filename": filename,
        },
        "result": result,
    }
    
def dl_worker():
    try:
        require_usable_queue()
        run_download_queue()
    except Exception:
        mark_worker_failed()
        raise


def run_download_queue():
    while not shutdown_event.is_set():
        job = None
        idle = False
        with queue_operation_lock:
            try:
                item = dl_q.get_nowait()
            except Empty:
                idle = True
                item = None
            if item is not None:
                job = normalize_queue_job(item)
                if job:
                    job = begin_preflight(job)
                    try:
                        set_active_queue_job(job)
                    except StateError:
                        shutdown_event.set()
                        dl_q.task_done()
                        raise
        if idle:
            shutdown_event.wait(0.1)
            continue
        try:
            if item is None:
                return
            if not job:
                print("Skipping invalid queued download")
                continue
            if collections_service.job_is_terminal(job["id"]):
                continue
            download(job)
        except StateError:
            shutdown_event.set()
            raise
        except Exception as e:
            print(f"Download worker error: {sanitize_diagnostic_text(e)}")
        finally:
            try:
                if job is not None and not shutdown_event.is_set():
                    clear_active_queue_job()
            finally:
                dl_q.task_done()

def build_ytdlp_common_args(data=None, include_extra_args=True):
    data = data or load_auth_data()
    args = ["yt-dlp", "--retry-sleep", "1", "--newline"]
    if data.get("PROXY"):
        args.extend(["--proxy", data["PROXY"]])
    cookies_file = active_cookies_file()
    if cookies_file:
        args.extend(["--cookies", cookies_file])
    if YTDLP_EXTRA_ARGS and include_extra_args:
        args.extend(shlex.split(YTDLP_EXTRA_ARGS))
    return args


def fetch_media_metadata(media_url, job_id=None, direct=False):
    command = build_ytdlp_common_args(include_extra_args=not direct) + [
        "--ignore-config", "--simulate", "--no-cache-dir",
        "--no-write-thumbnail", "--no-write-subs", "--no-write-auto-subs", "--no-write-info-json",
        "--no-write-playlist-metafiles",
        "--dump-single-json",
        "--playlist-items", "1",
        "--no-warnings",
    ]
    if direct:
        command.append("--no-playlist")
    command.append(media_url)
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=os.name == "posix",
    )
    if job_id:
        download_manager.attach_process(job_id, process)
    try:
        stdout, _ = process.communicate(timeout=30)
    except subprocess.TimeoutExpired:
        terminate_process_group(process)
        try:
            process.communicate(timeout=6)
        except subprocess.TimeoutExpired:
            pass
        raise
    finally:
        if job_id:
            download_manager.detach_process(job_id, process)

    if process.returncode != 0 or not stdout.strip():
        return {}
    metadata = json.loads(stdout)
    entries = metadata.get("entries") if isinstance(metadata, dict) else None
    if isinstance(entries, list):
        first_entry = next((entry for entry in entries if isinstance(entry, dict)), None)
        if first_entry:
            metadata = {**metadata, **first_entry}
    return metadata if isinstance(metadata, dict) else {}


def build_youtube_dl_cmd(item):
    job = normalize_queue_job(item)
    if not job:
        raise ValueError("Invalid download request")

    unsafe_chars_pattern = "[\\\\/:*?\"'<>|&+\\$%@!~=;,^#(){}\\[\\] ]"
    output_template = YTDLP_OUTPUT_TEMPLATE
    if job["section_mode"] == "from_timestamp":
        output_template = (
            f"%(title)s__from_{job['section_start']}s__%(extractor_key)s_%(id)s.%(ext)s"
        )
    target = job["target_relative_directory"]
    home = os.path.join(DOWNFOLDER_DIR, target) if target else DOWNFOLDER_DIR
    if safe_media_path(DOWNFOLDER_DIR, target, allow_empty=True) is None:
        raise APIError("unsafe_path")
    cmd = build_ytdlp_common_args() + [
        "--continue",
        "--windows-filenames",
        "--replace-in-metadata", "title", unsafe_chars_pattern, "_",
        "--paths", f"home:{home}",
        "--paths", f"temp:{os.path.join(home, '.incomplete')}",
        "-o", output_template,
    ]
    policy = job["date_policy"]
    if policy is not None:
        cmd.append("--no-match-filter")
        filters = []
        optional = "?" if policy["include_unknown_date"] else ""
        if policy["date_from"]:
            value = policy["date_from"].replace("-", "")
            cmd.extend(["--dateafter", value])
            filters.append(f"upload_date >={optional} {value}")
        if policy["date_to"]:
            value = policy["date_to"].replace("-", "")
            cmd.extend(["--datebefore", value])
            filters.append(f"upload_date <={optional} {value}")
        if not filters and not policy["include_unknown_date"]:
            filters.append("upload_date")
        if filters:
            cmd.extend(["--match-filter", " & ".join(filters)])
        cmd.extend(["--playlist-items", "1"])
    if job["force"]:
        cmd.append("--force-overwrites")
    if job["playlist_mode"] == "single":
        cmd.append("--no-playlist")
    elif job["playlist_mode"] == "first10":
        cmd.extend(["--yes-playlist", "--playlist-end", "10"])
    else:
        cmd.append("--yes-playlist")
    if job["section_mode"] == "from_timestamp":
        cmd.extend([
            "--download-sections",
            f"*{job['section_start']}-inf",
            "--force-keyframes-at-cuts",
        ])
    resolution = job["resolution"]
    if resolution == "best":
        cmd.extend([
            "-f",
            "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/bestvideo+bestaudio/best",
            "--merge-output-format", "mp4",
        ])
    elif resolution == "compatible-mp4":
        cmd.extend([
            "-f",
            COMPATIBLE_MP4_FORMAT_SELECTOR,
            "--merge-output-format", "mp4",
        ])
    elif resolution in ("audio-m4a", "audio"):
        cmd.extend(["-f", "bestaudio[ext=m4a]/bestaudio/best", "-x", "--audio-format", "m4a"])
    elif resolution == "audio-mp3":
        cmd.extend(["-f", "bestaudio[ext=m4a]/bestaudio/best", "-x", "--audio-format", "mp3"])
    elif resolution == "audio-opus":
        cmd.extend(["-f", "bestaudio[acodec^=opus]/bestaudio/best", "-x", "--audio-format", "opus"])
    elif re.match(r"(vtt|srt)", resolution):
        sub_format, sub_lang = resolution.split('|', 1)
        cmd.extend(["--write-auto-subs", "--sub-langs", sub_lang, "--sub-format", sub_format, "--skip-download"])
    else:
        height = resolution[:-1]
        format_selector = (
            f"bestvideo[height<={height}][ext=mp4]+bestaudio[ext=m4a]/"
            f"best[height<={height}][ext=mp4]/"
            f"bestvideo[height<={height}]+bestaudio/best[height<={height}]/best"
        )
        cmd.extend(["-f", format_selector, "--merge-output-format", "mp4"])

    if not re.match(r"(vtt|srt)", resolution):
        if job["write_thumbnail"]:
            cmd.extend(["--write-thumbnail", "--convert-thumbnails", "jpg"])
        cmd.extend(["--print", f"after_move:{YTDLP_ITEM_PREFIX}{YTDLP_ITEM_TEMPLATE}"])
    cmd.append(job["url"])
    return cmd


def file_download_timestamp(filepath):
    try:
        if filepath and os.path.isfile(filepath):
            return datetime.fromtimestamp(os.path.getmtime(filepath)).isoformat()
    except OSError:
        pass
    return datetime.now().isoformat()


def parse_completed_output_line(line):
    output_index = str(line or "").find(YTDLP_ITEM_PREFIX)
    if output_index < 0:
        return None
    try:
        output_info = json.loads(str(line)[output_index + len(YTDLP_ITEM_PREFIX):].strip())
    except json.JSONDecodeError:
        return None
    return output_info if isinstance(output_info, dict) else None


def build_completed_history_item(job, output_info, fallback, item_uuid=None):
    output_info = output_info if isinstance(output_info, dict) else {}
    fallback = fallback if isinstance(fallback, dict) else {}
    filepath = str(output_info.get("filepath") or output_info.get("_filename") or fallback.get("filepath") or "")
    relative_path = output_relative_path(filepath) if filepath else get_relative_path(fallback)
    if filepath and not relative_path:
        raise APIError("unsafe_path")
    target = job.get("target_relative_directory") or ""
    if target and relative_path and os.path.dirname(relative_path) != target:
        raise APIError("unsafe_path")
    filename = os.path.basename(relative_path) if relative_path else ""
    media_id, extractor = get_media_identity(output_info)
    if not media_id:
        media_id = fallback.get("media_id") or ""
    if not extractor:
        extractor = fallback.get("extractor") or ""
    title = get_media_display_title(output_info, fallback.get("title") or job["url"])
    channel = output_info.get("uploader") or output_info.get("channel") or fallback.get("channel") or ""
    source_url = output_info.get("webpage_url") or output_info.get("original_url") or job["url"]
    thumbnail_file = find_thumbnail_sidecar(relative_path)
    return {
        "uuid": item_uuid or str(uuid.uuid4()),
        "job_id": job["id"],
        "collection_id": job.get("collection_id") or None,
        "batch_id": job.get("batch_id") or None,
        "target_relative_directory": target,
        "date_policy": job.get("date_policy"),
        "upload_date": metadata_upload_date(output_info) if "upload_date" in output_info else fallback.get("upload_date"),
        "timestamp": file_download_timestamp(safe_downfolder_path(relative_path)),
        "url": source_url,
        "resolution": job["resolution"],
        "playlist_mode": job["playlist_mode"],
        "write_thumbnail": job["write_thumbnail"],
        "section_mode": job["section_mode"],
        "section_start": job["section_start"],
        "title": title,
        "channel": channel,
        "thumbnail": output_info.get("thumbnail") or fallback.get("thumbnail") or "",
        "thumbnail_file": thumbnail_file,
        "duration_seconds": output_info.get("duration") or fallback.get("duration_seconds") or 0,
        "media_id": media_id,
        "extractor": extractor,
        "status": "completed",
        "filepath": relative_path,
        "relative_path": relative_path,
        "filename": filename,
        "progress": 100,
        "source": job["source"],
        "restored": job["restored"],
    }


def download(item):
    job = normalize_queue_job(item)
    if not job:
        raise ValueError("Invalid download request")

    request_url = job["url"]
    resolution = job["resolution"]
    download_uuid = job["id"]
    video_title = request_url
    channel_name = ""
    thumbnail_url = ""
    duration_seconds = 0
    media_id = ""
    extractor = ""
    upload_date = None
    current_progress = 5
    final_filepath = None
    filename = None
    completed_outputs = []
    subtitle_paths = []
    process = None
    failure_diagnostics = deque(maxlen=80)

    def terminal_history_item(status, failure_code=""):
        return {
            'uuid': download_uuid,
            'job_id': job["id"],
            'collection_id': job["collection_id"] or None,
            'batch_id': job["batch_id"] or None,
            'target_relative_directory': job["target_relative_directory"],
            'date_policy': job["date_policy"],
            'upload_date': upload_date,
            'url': request_url,
            'resolution': resolution,
            'title': video_title,
            'channel': channel_name,
            'thumbnail': thumbnail_url,
            'duration_seconds': duration_seconds,
            'media_id': media_id,
            'extractor': extractor,
            'status': status,
            'failure_code': failure_code,
            'progress': current_progress,
            'source': job["source"],
            'restored': job["restored"],
            'playlist_mode': job["playlist_mode"],
            'write_thumbnail': job["write_thumbnail"],
            'section_mode': job["section_mode"],
            'section_start': job["section_start"],
        }

    def complete_cancellation():
        download_manager.complete_download(terminal_history_item("canceled"))

    try:
        # Download status setting
        download_info = {
            'uuid': download_uuid,
            'job_id': job["id"],
            'collection_id': job["collection_id"] or None,
            'batch_id': job["batch_id"] or None,
            'target_relative_directory': job["target_relative_directory"],
            'date_policy': job["date_policy"],
            'url': request_url,
            'resolution': resolution,
            'source': job["source"],
            'restored': job["restored"],
            'attempts': job["attempts"],
            'playlist_mode': job["playlist_mode"],
            'write_thumbnail': job["write_thumbnail"],
            'section_mode': job["section_mode"],
            'section_start': job["section_start"],
            'status': 'checking',
            'progress': 0,
            'title': video_title,
            'channel': channel_name,
            'thumbnail': thumbnail_url,
            'duration_seconds': duration_seconds,
            'media_id': media_id,
            'extractor': extractor,
            'preflight_started_at': job["preflight_started_at"],
            'preflight_ready_at': job["preflight_ready_at"],
            'preflight_warning': job["preflight_warning"],
            'speed': '',
            'eta': '',
            'start_time': time.time()
        }
        
        download_manager.set_current_download(download_info)

        source_error = validate_source_redirects(request_url)
        if source_error:
            download_manager.send_message("Source URL blocked by the private-network guard.")
            download_manager.complete_download(terminal_history_item("failed", "source_blocked"))
            return

        download_manager.send_message("Getting video information...")
        download_manager.update_progress(0)

        metadata = {}
        preflight_warning = ""
        try:
            metadata = (
                fetch_media_metadata(request_url, download_uuid, direct=True)
                if job["collection_id"] else fetch_media_metadata(request_url, download_uuid)
            )
            video_title = get_media_display_title(metadata, video_title)
            channel_name = metadata.get("uploader") or metadata.get("channel") or ""
            thumbnail_url = metadata.get("thumbnail") or ""
            duration_seconds = metadata.get("duration") or 0
            media_id, extractor = get_media_identity(metadata)
            upload_date = metadata_upload_date(metadata)
            if download_manager.current_download:
                download_manager.current_download['duration_seconds'] = duration_seconds
                download_manager.current_download['media_id'] = media_id
                download_manager.current_download['extractor'] = extractor
            download_manager.send_title(video_title)
            if channel_name:
                download_manager.send_channel(channel_name)
            if thumbnail_url:
                download_manager.send_thumbnail(thumbnail_url)
        except Exception as e:
            preflight_warning = "metadata_unavailable"
            failure_diagnostics.append(e)
            print(f"Info extraction error: {sanitize_diagnostic_text(e)}")

        if not metadata:
            preflight_warning = "metadata_unavailable"

        job = update_active_queue_job(
            job,
            state="ready",
            title=video_title,
            channel=channel_name,
            thumbnail=thumbnail_url,
            duration_seconds=duration_seconds,
            media_id=media_id,
            extractor=extractor,
            preflight_warning=preflight_warning,
            upload_date=upload_date,
        ) or job
        download_manager.update_current_download(
            status="ready",
            title=video_title,
            channel=channel_name,
            thumbnail=thumbnail_url,
            duration_seconds=duration_seconds,
            media_id=media_id,
            extractor=extractor,
            preflight_warning=preflight_warning,
        )

        if shutdown_event.is_set():
            download_manager.defer_current_download()
            return
        if download_manager.consume_cancellation(download_uuid):
            download_manager.cancel_preflight(job)
            return

        if job["date_policy"] is not None:
            rejection = (
                policy_rejection(metadata, job["date_policy"])
                if is_direct_metadata(metadata) else "metadata_unavailable"
            )
            if rejection:
                download_manager.complete_download(terminal_history_item("skipped", rejection))
                return

        if not job["force"] and job["playlist_mode"] == "single":
            existing = find_existing_download(
                request_url,
                resolution,
                media_id=media_id,
                extractor=extractor,
                require_thumbnail=job["write_thumbnail"],
                section_mode=job["section_mode"],
            )
            if existing:
                download_manager.skip_duplicate(existing, job)
                return

        preflight_outcome = wait_for_preflight_window(job)
        if preflight_outcome == "shutdown":
            download_manager.defer_current_download()
            return
        if preflight_outcome == "canceled":
            download_manager.cancel_preflight(job)
            return

        # Download start
        display_info = video_title
        if channel_name:
            display_info = f"{video_title} by {channel_name}"
            
        job = update_active_queue_job(job, state="downloading") or job
        download_manager.update_status('downloading')
        download_manager.send_message(f"[Started] downloading {display_info} resolution below {resolution}")
        download_manager.update_progress(5)
        
        cmd = build_youtube_dl_cmd(job)
        prepare_transfer_directory(job)
        print(
            f"Starting yt-dlp job {download_uuid} "
            f"profile={resolution} playlist={job['playlist_mode']}"
        )
        
        process = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1, start_new_session=os.name == "posix"
        )
        download_manager.attach_process(download_uuid, process)

        dn_type = download_info.get('resolution')
        
        # Read yt-dlp output
        while True:
            line = process.stdout.readline()
            if not line and process.poll() is not None:
                break
            if line:
                safe_line = sanitize_diagnostic_text(line)
                if safe_line:
                    failure_diagnostics.append(safe_line)
                    print(f"yt-dlp output: {safe_line}")

                plain_line = ANSI_ESCAPE_PATTERN.sub('', line)
                transfer_match = re.search(r'\bat\s+([^\s]+/s)\s+ETA\s+([0-9:]+)', plain_line)
                if transfer_match:
                    download_manager.update_transfer_stats(transfer_match.group(1), transfer_match.group(2))

                # Capture every final output so playlist jobs create one history row per file.
                if re.match(r"(vtt|srt)",dn_type):
                    exec_match = re.search(
                        r"\[(?:info|download)\] (?:Writing video subtitles to|Destination):\s+(.+?\.(?:srt|vtt))(?:\s|$)",
                        line,
                    )
                    if exec_match:
                        subtitle_path = exec_match.group(1)
                        if subtitle_path not in subtitle_paths:
                            subtitle_paths.append(subtitle_path)
                        filename = os.path.basename(subtitle_path)
                        final_filepath = subtitle_path
                        print("Captured subtitle output marker")
                else:
                    output_info = parse_completed_output_line(line)
                    if output_info:
                        completed_outputs.append(output_info)
                        final_filepath = output_info.get("filepath") or output_info.get("_filename") or final_filepath
                        filename = os.path.basename(final_filepath) if final_filepath else filename
                        print("Captured completed output marker")
                

                # Download start detection
                if "[download] Destination:" in line and ".incomplete/" in line:
                    download_manager.update_status('downloading_file')
                    download_manager.send_message("Downloading...")

                # Progress extraction
                progress_match = re.search(r'\[download\]\s+(\d+(?:\.\d+)?)%', line)
                if progress_match:
                    try:
                        raw_progress = float(progress_match.group(1))
                        adjusted_progress = 5 + (raw_progress * 0.90)
                        
                        if abs(adjusted_progress - current_progress) >= 1:
                            current_progress = adjusted_progress
                            download_manager.update_progress(adjusted_progress)
                    except Exception as e:
                        print(f"Progress parsing error: {sanitize_diagnostic_text(e)}")

                # Merge process detection
                if "[Merger] Merging formats" in line:
                    download_manager.update_status('merging')
                    download_manager.send_message("Merging files...")
                    download_manager.update_progress(95)
        
        return_code = process.poll()
        download_manager.detach_process(download_uuid, process)
        print(f"Process finished with return code: {return_code}")
        if shutdown_event.is_set():
            print(f"Download deferred for restart: job {download_uuid}")
            download_manager.defer_current_download()
            return
        was_canceled = download_manager.consume_cancellation(download_uuid)
        if was_canceled and return_code != 0:
            complete_cancellation()
            return

        # Completion handling
        if return_code == 0:
            if job["date_policy"] is not None and not completed_outputs and not subtitle_paths:
                download_manager.complete_download(terminal_history_item("skipped", "date_policy_filtered"))
                return
            download_manager.update_status('completed')
            download_manager.send_message(f"[Finished] downloading {display_info} completed")
            download_manager.update_progress(100)
            fallback = {
                "filepath": final_filepath,
                "filename": filename,
                "title": video_title,
                "channel": channel_name,
                "thumbnail": thumbnail_url,
                "duration_seconds": duration_seconds,
                "media_id": media_id,
                "extractor": extractor,
                "upload_date": upload_date,
            }
            if re.match(r"(vtt|srt)", resolution):
                completed_outputs = [{"filepath": path} for path in subtitle_paths]
            if not completed_outputs:
                completed_outputs = [{}]

            completion_items = [
                build_completed_history_item(
                    job,
                    output_info,
                    fallback,
                    item_uuid=download_uuid if index == 0 else None,
                )
                for index, output_info in enumerate(completed_outputs)
            ]
            download_manager.complete_downloads(completion_items)
        else:
            failure_code = classify_download_failure(failure_diagnostics)
            download_manager.send_message(f"[Finished] downloading failed {display_info}")
            download_manager.complete_download(terminal_history_item("failed", failure_code))
            
        print(f"Download job finished: {download_uuid}")
            
    except StateError:
        raise
    except Exception as e:
        if process is not None:
            download_manager.detach_process(download_uuid, process)
        print(f"Download error: {sanitize_diagnostic_text(e)}")
        if shutdown_event.is_set():
            download_manager.defer_current_download()
            return
        if download_manager.consume_cancellation(download_uuid):
            complete_cancellation()
            return
        failure_code = e.code if isinstance(e, APIError) else classify_download_failure(failure_diagnostics, e)
        download_manager.send_message("Download error occurred")
        download_manager.complete_download(terminal_history_item("error", failure_code))

import mimetypes
from email.utils import formatdate


def prepare_transfer_directory(job):
    target = job.get("target_relative_directory") or ""
    home = ensure_media_directory(DOWNFOLDER_DIR, target)
    incomplete = (target + "/" if target else "") + ".incomplete"
    ensure_media_directory(DOWNFOLDER_DIR, incomplete)
    for name in os.listdir(home):
        relative = (target + "/" if target else "") + name
        if safe_downfolder_path(relative) is None:
            raise APIError("unsafe_path")
    for directory, directories, filenames in os.walk(os.path.join(home, ".incomplete"), followlinks=False):
        for name in directories + filenames:
            relative = os.path.relpath(os.path.join(directory, name), DOWNFOLDER_DIR).replace(os.sep, "/")
            if safe_downfolder_path(relative) is None:
                raise APIError("unsafe_path")


def serve_media_file(relative_path, download_name=None):
    try:
        media = open_media_file(DOWNFOLDER_DIR, relative_path)
    except (OSError, APIError):
        abort(404, "File not found")
    metadata = os.fstat(media.fileno())
    size = metadata.st_size
    headers = {
        "Content-Type": mimetypes.guess_type(relative_path)[0] or "application/octet-stream",
        "Content-Length": str(size),
        "Accept-Ranges": "bytes",
        "Last-Modified": formatdate(metadata.st_mtime, usegmt=True),
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "private, no-store",
        "Content-Security-Policy": "sandbox",
        "Content-Disposition": "inline",
    }
    if download_name:
        headers["Content-Disposition"] = "attachment; filename*=UTF-8''" + quote(download_name, safe="")
    status = 200
    start, end = 0, size - 1
    range_header = request.headers.get("Range")
    if range_header:
        match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header.strip())
        if not match or not any(match.groups()) or size == 0:
            media.close()
            return HTTPResponse(status=416, headers={"Content-Range": f"bytes */{size}"})
        first, last = match.groups()
        if first:
            start = int(first)
            end = min(int(last), size - 1) if last else size - 1
        else:
            start = max(0, size - int(last))
        if start >= size or start > end:
            media.close()
            return HTTPResponse(status=416, headers={"Content-Range": f"bytes */{size}"})
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"
        headers["Content-Length"] = str(end - start + 1)
        status = 206
    if request.method == "HEAD":
        media.close()
        return HTTPResponse(status=status, headers=headers)
    if status == 200:
        return HTTPResponse(body=media, status=status, headers=headers)

    def stream_range():
        try:
            media.seek(start)
            remaining = end - start + 1
            while remaining:
                block = media.read(min(65536, remaining))
                if not block:
                    break
                remaining -= len(block)
                yield block
        finally:
            media.close()

    return HTTPResponse(body=stream_range(), status=status, headers=headers)

def resolve_history_file(uuid):
    download_manager.load_history()
    file_info = download_manager.get_combined_history_item(uuid)
    if not file_info:
        abort(404, "File not found")

    file_info = normalize_history_item(file_info)
    actual_filename = file_info.get('relative_path')
    file_path = safe_downfolder_path(actual_filename)
    if not actual_filename or not file_path:
        abort(404, "Valid filename not found")
    if not os.path.isfile(file_path):
        abort(404, "Physical file not found")
    return file_info, actual_filename

@get('/static/downfolder/<uuid>')
def serve_download(uuid):
    """File download using UUID"""
    data = load_auth_data()
    if not is_cookie_authenticated(data):
        abort(403, "Unauthorized")
    
    try:
        _, actual_filename = resolve_history_file(uuid)
        
        # Organize file names to allow safe downloads from your browser
        print(f"Serving history file {uuid}")
        safe_download_name = re.sub(r'[\\/:*?"<>|⧸]', '-', os.path.basename(actual_filename))
        safe_download_name = safe_download_name.replace("'\"'\"'", "'")  # 이스케이핑된 따옴표 처리
        # Check to preserve file extensions
        original_ext = os.path.splitext(actual_filename)[1]
        if original_ext and not safe_download_name.endswith(original_ext):
            safe_download_name += original_ext
        
        print(f"Serving history file {uuid} as an attachment")
        
        # Find the original file with actual_filename and use safe_download_name for the download name.
        return serve_media_file(actual_filename, download_name=safe_download_name)
    
        
    except HTTPError:
        raise
    except Exception as e:
        print(f"Error in serve_download: {sanitize_diagnostic_text(e)}")
        abort(500, "Internal server error")

@get('/static/preview/<uuid>')
def serve_preview(uuid):
    """Serve an authenticated media file inline for the dashboard preview player."""
    data = load_auth_data()
    if not is_cookie_authenticated(data):
        abort(403, "Unauthorized")

    try:
        _, actual_filename = resolve_history_file(uuid)
        response.set_header("Content-Disposition", "inline")
        response.set_header("X-Content-Type-Options", "nosniff")
        return serve_media_file(actual_filename)
    except HTTPError:
        raise
    except Exception as e:
        print(f"Error in serve_preview: {sanitize_diagnostic_text(e)}")
        abort(500, "Internal server error")


@get('/static/thumbnail/<uuid>')
def serve_thumbnail(uuid):
    """Serve a saved thumbnail sidecar to an authenticated dashboard."""
    data = load_auth_data()
    if not is_cookie_authenticated(data):
        abort(403, "Unauthorized")

    download_manager.load_history()
    file_info = download_manager.get_combined_history_item(uuid)
    if not file_info:
        abort(404, "Thumbnail not found")
    normalized = normalize_history_item(file_info)
    thumbnail_filename = normalized.get("thumbnail_file")
    thumbnail_path = safe_downfolder_path(thumbnail_filename)
    if not thumbnail_filename or not thumbnail_path or not os.path.isfile(thumbnail_path):
        abort(404, "Thumbnail not found")
    response.set_header("Content-Disposition", "inline")
    response.set_header("X-Content-Type-Options", "nosniff")
    return serve_media_file(thumbnail_filename)
    

# WebSocket handler
@get('/websocket')
@websocket
def websocket_handler(ws):
    if ws is None:
        abort(400, "WebSocket upgrade required")
    if not is_cookie_authenticated():
        ws.close()
        return

    try:
        # Add new client (including history auto-restoration)
        download_manager.add_client(ws)
        ws_addr.wsClassVal = ws
        print(f"WebSocket connected")
        
        while True:
            message = ws.receive()
            if message is None:
                break
                
            event_match = re.match(r"^\[[A-Z_]+\]", str(message or ""))
            event_name = event_match.group(0) if event_match else "[UNKNOWN]"
            print(f"Received WebSocket event: {event_name}")

            # Status request handling
            if message == '[REQUEST_STATE]':
                current_state = download_manager.get_current_state()
                safe_websocket_send(ws, f"[SESSION_STATE], {json.dumps(current_state)}")

            # History request handling
            elif message == '[REQUEST_HISTORY]':
                download_manager.load_history()  # Load latest history
                for history_item in download_manager.combined_history():
                    safe_websocket_send(ws, f"[RESTORE_HISTORY], {json.dumps(history_item)}")
                safe_websocket_send(ws, "[HISTORY_RESTORE_COMPLETE], done")
                
    except Exception as e:
        print(f"WebSocket error: {sanitize_diagnostic_text(e)}")
    finally:
        # Disconnect the client
        download_manager.remove_client(ws)
        if ws_addr.wsClassVal == ws:
            ws_addr.wsClassVal = None
        print(f"WebSocket disconnected")

# Global variable initialization
dl_q = Queue()
download_thread = None
download_thread_lock = Lock()
queue_state_lock = Lock()
queue_operation_lock = RLock()
shutdown_event = Event()
worker_failed_event = Event()
active_queue_job = None
queue_restore_count = 0
queue_state_loaded = False
preflight_receipt_lock = Lock()
recent_preflight_receipt = None
collections_service = CollectionService(globals(), COLLECTIONS_STATE_FILE)
connections_store = ConnectionStore(CONNECTIONS_STATE_FILE)

def run_server():
    global port, proxy
    require_usable_queue()
    shutdown_event.clear()
    data = load_auth_data()
    if os.environ.get("YDLNAS_WEB_PORT"):
        port = int(os.environ["YDLNAS_WEB_PORT"])
    elif data.get("APP_PORT"):
        port = data["APP_PORT"]
    if data.get("PROXY"):
        proxy = data["PROXY"]

    load_persisted_queue()
    collections_service.reconcile()
    start_download_thread_if_needed()
    try:
        run(
            host=os.environ.get("YDLNAS_WEB_HOST", "0.0.0.0"), port=port,
            server=GeventWebSocketServer, worker_failed_event=worker_failed_event,
        )
    finally:
        shutdown_event.set()
        dl_q.put(None)
        if download_thread and download_thread.is_alive():
            download_thread.join(timeout=5)

def main():
    try:
        run_server()
    except DownloadWorkerFailed:
        # Do not let unrelated executor threads delay the supervised process restart.
        os._exit(1)


if __name__ == "__main__":
    main()
