import json
import subprocess
import html
from queue import Queue
import re
import shutil
import signal
import time
import uuid
import hmac
import shlex
from importlib.metadata import PackageNotFoundError, version as package_version
from datetime import datetime, timedelta
from collections import defaultdict, deque
from bottle import run, Bottle, request, static_file, response, route, post, redirect, template, get, abort, HTTPError
from threading import Event, Lock, Thread
from bottle_websocket import GeventWebSocketServer
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
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

DOWNFOLDER_DIR = os.environ.get("DOWNLOAD_DIR", "./downfolder")
STATE_DIR = os.path.abspath(os.environ.get("STATE_DIR", "./metadata"))
AUTH_FILE = os.environ.get("AUTH_FILE", "Auth.json")
APP_STATE_FILE = os.path.join(STATE_DIR, "app_state.json")
HISTORY_FILE = os.path.join(STATE_DIR, "download_history.json")
QUEUE_STATE_FILE = os.path.join(STATE_DIR, "queue_state.json")
APP_VERSION = os.environ.get("APP_VERSION", "26.0806")
API_TOKEN = os.environ.get("YDLNAS_API_TOKEN", "").strip()
YTDLP_COOKIES_FILE = os.environ.get("YTDLP_COOKIES_FILE", "").strip()
YTDLP_EXTRA_ARGS = os.environ.get("YTDLP_EXTRA_ARGS", "").strip()


def nonnegative_float_env(name, default):
    try:
        return max(0.0, float(os.environ.get(name, default)))
    except (TypeError, ValueError):
        return float(default)


STORAGE_WARNING_GB = nonnegative_float_env("YDLNAS_STORAGE_WARNING_GB", "10")
STORAGE_CRITICAL_GB = nonnegative_float_env("YDLNAS_STORAGE_CRITICAL_GB", "2")
VALID_RESOLUTIONS = {"best", "audio", "audio-m4a", "audio-mp3"}
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
YTDLP_ITEM_PREFIX = "__YDLNAS_ITEM__:"
YTDLP_ITEM_TEMPLATE = (
    '{"filepath":%(filepath|"")j,"title":%(title|"")j,'
    '"uploader":%(uploader|"")j,"channel":%(channel|"")j,'
    '"thumbnail":%(thumbnail|"")j,"duration":%(duration|0)j,'
    '"id":%(id|"")j,"extractor_key":%(extractor_key|"")j,'
    '"webpage_url":%(webpage_url|"")j,"original_url":%(original_url|"")j}'
)
GENERIC_INSTAGRAM_TITLE_PATTERN = re.compile(r"^Video by .+$", re.IGNORECASE)
QUEUE_STATE_VERSION = 3
PLAYLIST_MODES = {"single", "first10", "all"}
SECTION_MODES = {"full", "from_timestamp"}
SHARE_PROFILE_COOKIE = "ydlnas_share_profile"
SHARE_REVIEW_COOKIE = "share_review"
SHARE_PROFILES = {"best", "1080p", "720p", "audio-mp3", "audio-m4a", "ask"}
SHARE_PROFILE_ALIASES = {
    "best": "best",
    "1080": "1080p",
    "1080p": "1080p",
    "720": "720p",
    "720p": "720p",
    "mp3": "audio-mp3",
    "audio": "audio-m4a",
    "m4a": "audio-m4a",
    "audio-mp3": "audio-mp3",
    "audio-m4a": "audio-m4a",
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
    "Resolution is required": "resolution_required",
    "Subtitle downloads require a language code, for example vtt|en or srt|ko": "subtitle_language_required",
    "Unsupported resolution": "unsupported_resolution",
    "Unsupported playlist mode": "unsupported_playlist_mode",
    "Playlist scope is required": "playlist_scope_required",
    "Unsupported timestamp mode": "unsupported_timestamp_mode",
    "Timestamp was not found in the shared URL": "timestamp_not_found",
    "Unsupported mobile share profile": "unsupported_share_profile",
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
    known_paths = {
        AUTH_FILE,
        DOWNFOLDER_DIR,
        STATE_DIR,
        YTDLP_COOKIES_FILE,
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
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    temp_path = path + ".tmp"
    with open(temp_path, "w", encoding="utf-8") as output_file:
        json.dump(payload, output_file, indent=2, ensure_ascii=ensure_ascii)
    os.replace(temp_path, path)

def save_app_state(updates):
    state = load_json_file(APP_STATE_FILE, {})
    state.update(updates)
    atomic_write_json(APP_STATE_FILE, state, ensure_ascii=True)
    return state

def load_auth_data():
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

def validate_download_request(url, resolution):
    if not isinstance(url, str) or not url.strip():
        return "URL is required"

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

def get_actual_filename(item):
    filename = item.get('filename') if isinstance(item, dict) else None
    filepath = item.get('filepath') if isinstance(item, dict) else None

    if filename and filename != "unknown":
        return os.path.basename(filename)
    if filepath and filepath != "unknown":
        return os.path.basename(filepath)
    return ""


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
    if not filename:
        return None

    root = os.path.abspath(DOWNFOLDER_DIR)
    candidate = os.path.abspath(os.path.join(root, os.path.basename(filename)))
    try:
        if os.path.commonpath([root, candidate]) != root:
            return None
    except ValueError:
        return None
    return candidate

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

    stat_result = os.stat(file_path)
    return normalize_history_item({
        "uuid": get_mounted_file_uuid(filename),
        "timestamp": datetime.fromtimestamp(stat_result.st_mtime).isoformat(),
        "url": "",
        "resolution": "mounted",
        "title": os.path.splitext(filename)[0] or filename,
        "channel": "Mounted folder",
        "status": "file_only",
        "filepath": os.path.join(DOWNFOLDER_DIR, filename),
        "filename": filename,
        "progress": 100,
        "source": "mounted_folder",
        "metadata_status": "missing",
        "thumbnail_file": find_thumbnail_sidecar(filename),
    })

def list_mounted_file_items():
    if not os.path.isdir(DOWNFOLDER_DIR):
        return []

    items = []
    try:
        filenames = os.listdir(DOWNFOLDER_DIR)
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
            file_path = safe_downfolder_path(filename)
            if not file_path or not os.path.isfile(file_path):
                continue
            item = build_mounted_file_item(filename)
            if item:
                items.append(item)
    except Exception as e:
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

    filename = get_actual_filename(item)
    file_path = safe_downfolder_path(filename)
    file_exists = bool(file_path and os.path.isfile(file_path))
    file_size_bytes = os.path.getsize(file_path) if file_exists else 0

    item.setdefault('url', '')
    item.setdefault('resolution', '')
    item.setdefault('title', '')
    item.setdefault('channel', '')
    item.setdefault('thumbnail', '')
    if not item.get('thumbnail_file'):
        item['thumbnail_file'] = find_thumbnail_sidecar(filename)
    item.setdefault('duration_seconds', 0)
    item.setdefault('media_id', '')
    item.setdefault('extractor', '')
    item.setdefault('section_mode', 'full')
    item.setdefault('section_start', 0)
    item.setdefault('status', 'unknown')
    item.setdefault('failure_code', '')
    item.setdefault('filepath', '')
    item.setdefault('source', 'history')
    item.setdefault('metadata_status', 'saved' if item.get('source') != 'mounted_folder' else 'missing')
    item['filename'] = filename
    item['file_exists'] = file_exists
    item['file_size_bytes'] = file_size_bytes
    thumbnail_path = safe_downfolder_path(item.get('thumbnail_file'))
    item['thumbnail_file_exists'] = bool(thumbnail_path and os.path.isfile(thumbnail_path))
    item['thumbnail_file_size_bytes'] = os.path.getsize(thumbnail_path) if item['thumbnail_file_exists'] else 0
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
        candidate = stem + thumbnail_extension
        if os.path.isfile(candidate):
            return os.path.basename(candidate)
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

    url = str(job.get("url") or "").strip()
    resolution = str(job.get("resolution") or "").strip()
    if validate_download_request(url, resolution):
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
    try:
        with queue_state_lock:
            active = normalize_queue_job(active_queue_job) if active_queue_job else None
            pending = pending_queue_jobs()
            atomic_write_json(QUEUE_STATE_FILE, {
                "version": QUEUE_STATE_VERSION,
                "updated_at": datetime.now().isoformat(),
                "active": active,
                "pending": pending,
            })
    except Exception as error:
        print(f"Failed to save queue state: {sanitize_diagnostic_text(error)}")


def load_persisted_queue():
    global queue_restore_count, queue_state_loaded

    with queue_state_lock:
        if queue_state_loaded:
            return queue_restore_count
        queue_state_loaded = True

    payload = load_json_file(QUEUE_STATE_FILE, {})
    candidates = []
    if isinstance(payload, dict):
        if payload.get("active"):
            candidates.append(payload["active"])
        if isinstance(payload.get("pending"), list):
            candidates.extend(payload["pending"])

    restored_jobs = []
    seen_job_ids = set()
    for item in candidates:
        job = normalize_queue_job(item, restored=True)
        if not job or job["id"] in seen_job_ids:
            continue
        seen_job_ids.add(job["id"])
        job["attempts"] += 1
        restored_jobs.append(job)

    for job in restored_jobs:
        dl_q.put(job)

    queue_restore_count = len(restored_jobs)
    persist_queue_state()
    if restored_jobs:
        print(f"Restored {len(restored_jobs)} queued download(s)")
    return queue_restore_count


def set_active_queue_job(job):
    global active_queue_job
    with queue_state_lock:
        active_queue_job = normalize_queue_job(job)
    persist_queue_state()


def clear_active_queue_job():
    global active_queue_job
    with queue_state_lock:
        active_queue_job = None
    persist_queue_state()


def same_queue_request(first, second):
    first = normalize_queue_job(first)
    second = normalize_queue_job(second)
    if not first or not second:
        return False
    return (
        first["normalized_url"] == second["normalized_url"]
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
        "resolution": item.get("resolution"),
        "timestamp": item.get("timestamp"),
        "status": item.get("status"),
        "source": item.get("source"),
        "section_mode": item.get("section_mode"),
        "section_start": item.get("section_start"),
    }


def find_existing_download(
    url,
    resolution,
    media_id="",
    extractor="",
    require_thumbnail=False,
    section_mode="full",
):
    normalized_url = normalize_media_url(url)
    requested_type = get_download_type(resolution)
    requested_section_mode = normalize_section_mode(section_mode) or "full"
    requested_section_start = extract_shared_timestamp(url) if requested_section_mode == "from_timestamp" else 0
    items = download_manager.normalized_history() + list_mounted_file_items()

    for item in items:
        item = normalize_history_item(item)
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

        item_url = normalize_media_url(item.get("url"))
        if normalized_url and item_url and normalized_url == item_url:
            return existing_download_summary(item)

        if media_id and extractor:
            identity_matches = (
                str(item.get("media_id") or "") == str(media_id)
                and str(item.get("extractor") or "").casefold() == str(extractor).casefold()
            )
            filename_matches = media_identity_matches_filename(
                item.get("filename"), media_id, extractor
            )
            if identity_matches or filename_matches:
                return existing_download_summary(item)
    return None


def remove_queued_job(job_id):
    removed = None
    with queue_operation_lock:
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
            persist_queue_state()

    if removed:
        download_manager.broadcast_to_all_clients(
            f"[QUEUE_UPDATED], {json.dumps({'removed_job_id': job_id})}"
        )
        return public_queue_job(removed)
    return None


def start_download_thread_if_needed():
    global download_thread
    if download_thread is None or not download_thread.is_alive():
        download_thread = Thread(target=dl_worker, name="download-worker", daemon=True)
        download_thread.start()


def enqueue_download(
    url,
    resolution,
    source,
    ws=None,
    force=False,
    playlist_mode="single",
    write_thumbnail=False,
    section_mode="full",
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
        if not force:
            duplicate_job = find_queued_duplicate(job)
            if duplicate_job:
                return {
                    "queued": False,
                    "duplicate": True,
                    "duplicate_type": "queue",
                    "job": duplicate_job,
                }

            existing = None
            if job["playlist_mode"] == "single":
                existing = find_existing_download(
                    job["url"],
                    job["resolution"],
                    require_thumbnail=job["write_thumbnail"],
                    section_mode=job["section_mode"],
                )
            if existing:
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
        dl_q.put(job)
        persist_queue_state()

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
        self.current_download = None  # presently active download information
        self.download_history = []  # history of download info
        self.connected_clients = set() #every websocket clients
        self.is_downloading = False
        self.process_lock = Lock()
        self.active_process = None
        self.active_process_job_id = None
        self.cancel_requested_job_id = None
        self.history_file = HISTORY_FILE
        self.load_history()
    
    def load_history(self):
        """Load saved history"""        
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    self.download_history = json.load(f)
                if not isinstance(self.download_history, list):
                    self.download_history = []
                print(f"Loaded {len(self.download_history)} history items")
            except Exception as e:
                print(f"Failed to load history: {sanitize_diagnostic_text(e)}")
                self.download_history = []
    
    def save_history(self):        
        """Save history to file"""
        try:
            atomic_write_json(self.history_file, self.download_history)
        except Exception as e:
            print(f"Failed to save history: {sanitize_diagnostic_text(e)}")
    
    def clear_all_history(self):
        """Clear all history"""
        self.download_history = []
        self.save_history()
        self.broadcast_to_all_clients("[HISTORY_CLEARED], all")
        return True
    
    def delete_history_item(self, uuid):
        """Delete a history item with a specific UUID"""
        try:
            original_len = len(self.download_history)
            self.download_history = [item for item in self.download_history if item.get('uuid') != uuid]
            if len(self.download_history) == original_len:
                return False
            self.save_history()
            self.broadcast_to_all_clients(f"[HISTORY_DELETED], {uuid}")
            return True
        except Exception as e:
            print(f"Failed to delete history item: {sanitize_diagnostic_text(e)}")
            return False

    def get_history_item(self, uuid):
        for item in self.download_history:
            if item.get('uuid') == uuid:
                return item
        return None

    def normalized_history(self):
        return [normalize_history_item(item) for item in self.download_history]

    def combined_history(self):
        normalized_history = self.normalized_history()
        history_filenames = {
            item.get('filename')
            for item in normalized_history
            if item.get('filename')
        }
        mounted_files = [
            item
            for item in list_mounted_file_items()
            if item.get('filename') not in history_filenames
        ]
        return normalized_history + mounted_files

    def get_combined_history_item(self, item_uuid):
        for item in self.normalized_history():
            if item.get('uuid') == item_uuid:
                return item
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
            current["status"] = "canceling"
        if process and not already_requested:
            terminate_process_group(process)
        return {"job_id": job_id, "already_requested": already_requested}

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

        candidate_filename = str(candidate.get("filename") or "").casefold()
        candidate_media_id = str(candidate.get("media_id") or "")
        candidate_extractor = str(candidate.get("extractor") or "").casefold()
        for index, existing in enumerate(self.download_history):
            existing = normalize_history_item(existing)
            if not existing.get("file_exists"):
                continue

            same_file = bool(
                candidate_filename
                and candidate_filename == str(existing.get("filename") or "").casefold()
            )
            same_media = bool(
                candidate_media_id
                and candidate_extractor
                and candidate_media_id == str(existing.get("media_id") or "")
                and candidate_extractor == str(existing.get("extractor") or "").casefold()
                and candidate.get("resolution") == existing.get("resolution")
                and candidate.get("section_mode") == existing.get("section_mode")
                and int(candidate.get("section_start") or 0) == int(existing.get("section_start") or 0)
            )
            if same_file or same_media:
                return index
        return None

    def complete_downloads(self, completion_items):
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
        payload = {
            "existing": existing,
            "job": public_queue_job(job),
        }
        if self.current_download:
            self.current_download["status"] = "duplicate"
        self.reset_active_runtime()
        self.broadcast_to_all_clients(f"[DUPLICATE], {json.dumps(payload, ensure_ascii=False)}")

    def defer_current_download(self):
        """Release transient UI state while queue persistence retains the job for restart."""
        self.reset_active_runtime()
    
    def add_client(self, ws):
        """Add a new client connection"""
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
        print(f"Client disconnected. Total clients: {len(self.connected_clients)}")
    
    def broadcast_to_all_clients(self, message):
        """Broadcast message to all connected clients"""
        disconnected_clients = set()
        
        for client in self.connected_clients:
            if not safe_websocket_send(client, message):
                disconnected_clients.add(client)

        # Remove disconnected clients
        for client in disconnected_clients:
            self.connected_clients.discard(client)
    
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
    
    try:
        # Check WebSocket connection status
        if hasattr(ws, 'closed') and ws.closed:
            return False
        
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
    try:
        data = load_auth_data()
        if data.get("TERMS_ACCEPTED") != "Y":
            redirect('/terms')
    except Exception as e:
        print(f"Error checking terms acceptance: {sanitize_diagnostic_text(e)}")
        redirect('/terms')

    if is_cookie_authenticated(data):
        shared_url = ""
        if request.query.get("shared") == "review":
            shared_url = consume_share_review(data)
        return render_localized_template(
            "./static/template/index.tpl",
            userNm=data["MY_ID"],
            app_version=APP_VERSION,
            locale_next="/youtube-dl",
            shared_url_json=json.dumps(shared_url),
        )

    redirect("/")

@get('/health')
def health_check():
    response.content_type = "application/json"
    storage = get_storage_status()
    return {
        "status": "ok",
        "app": "youtube-dl-nas",
        "version": APP_VERSION,
        "queue_count": dl_q.qsize(),
        "queue": {
            "persistent": True,
            "restored_count": queue_restore_count,
            "state_file": os.path.basename(QUEUE_STATE_FILE),
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
    }

@get('/youtube-dl/q', method='POST')
def q_put():
    _, error_response = require_cookie_auth()
    if error_response:
        return error_response

    payload = get_request_json()
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
        "profiles": ["best", "1080p", "720p", "audio-mp3", "audio-m4a"],
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

    if not isinstance(requested_resolution, str) or not requested_resolution.strip():
        return json_error("Resolution is required", 400)
    resolution = SHARE_PROFILE_ALIASES.get(
        requested_resolution.strip().lower(),
        requested_resolution.strip(),
    )
    if resolution == "ask":
        return json_error("Unsupported mobile share profile", 400, {
            "profiles": ["best", "1080p", "720p", "audio-mp3", "audio-m4a"],
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
        "code": "cancellation_requested",
        "job_id": cancellation["job_id"],
        "already_requested": cancellation["already_requested"],
        "msg": "Active download cancellation requested",
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
        item = get_mounted_file_item(uuid)
        is_mounted_file = bool(item)

    if not item:
        return json_error("History item not found", 404)

    normalized = normalize_history_item(item)
    file_path = safe_downfolder_path(normalized.get('filename'))
    if not file_path:
        return json_error("Valid file path not found", 404)
    if not os.path.isfile(file_path):
        return json_error("Physical file not found", 404)

    try:
        os.remove(file_path)
    except Exception as e:
        print(f"Failed to delete file: {sanitize_diagnostic_text(e)}")
        return json_error("Failed to delete physical file", 500)

    deleted_sidecars = []
    thumbnail_filename = normalized.get("thumbnail_file")
    thumbnail_path = safe_downfolder_path(thumbnail_filename)
    if thumbnail_path and os.path.isfile(thumbnail_path):
        try:
            os.remove(thumbnail_path)
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
            if get_actual_filename(history_item) == normalized.get('filename')
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
        return json_error("History item not found", 404)

    url = item.get("url")
    resolution = item.get("resolution")
    validation_error = validate_download_request(url, resolution)
    if validation_error:
        return json_error(validation_error, 400)

    result = enqueue_download(
        url,
        resolution,
        "web",
        ws_addr.wsClassVal,
        playlist_mode=normalize_playlist_mode(item.get("playlist_mode"), url),
        write_thumbnail=parse_boolean(item.get("write_thumbnail")),
        section_mode=normalize_section_mode(item.get("section_mode")),
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

    file_path = safe_downfolder_path(filename)
    if not file_path or not os.path.isfile(file_path):
        return json_error("Subtitle file not found", 404)
    if os.path.getsize(file_path) > SUBTITLE_QA_MAX_FILE_BYTES:
        return json_error("Subtitle file is too large to analyze", 413)

    try:
        with open(file_path, "r", encoding="utf-8-sig", errors="replace") as subtitle_file:
            transcription = extract_subtitle_text(subtitle_file.read(), extension)
    except OSError as error:
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
    while not shutdown_event.is_set():
        item = dl_q.get()
        job = None
        try:
            if item is None:
                return
            job = normalize_queue_job(item)
            if not job:
                print("Skipping invalid queued download")
                continue
            set_active_queue_job(job)
            download(job)
        except Exception as e:
            print(f"Download worker error: {sanitize_diagnostic_text(e)}")
        finally:
            if job is not None and not shutdown_event.is_set():
                clear_active_queue_job()
            dl_q.task_done()

def build_ytdlp_common_args(data=None):
    data = data or load_auth_data()
    args = ["yt-dlp", "--retry-sleep", "1", "--newline"]
    if data.get("PROXY"):
        args.extend(["--proxy", data["PROXY"]])
    if YTDLP_COOKIES_FILE:
        if not os.path.isfile(YTDLP_COOKIES_FILE):
            raise ValueError(f"YTDLP_COOKIES_FILE does not exist: {YTDLP_COOKIES_FILE}")
        args.extend(["--cookies", YTDLP_COOKIES_FILE])
    if YTDLP_EXTRA_ARGS:
        args.extend(shlex.split(YTDLP_EXTRA_ARGS))
    return args


def fetch_media_metadata(media_url, job_id=None):
    command = build_ytdlp_common_args() + [
        "--dump-single-json",
        "--playlist-items", "1",
        "--no-warnings",
        media_url,
    ]
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
    cmd = build_ytdlp_common_args() + [
        "--continue",
        "--replace-in-metadata", "title", unsafe_chars_pattern, "_",
        "--paths", f"home:{DOWNFOLDER_DIR}",
        "--paths", f"temp:{os.path.join(DOWNFOLDER_DIR, '.incomplete')}",
        "-o", output_template,
    ]
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
    elif resolution in ("audio-m4a", "audio"):
        cmd.extend(["-f", "bestaudio[ext=m4a]/bestaudio/best", "-x", "--audio-format", "m4a"])
    elif resolution == "audio-mp3":
        cmd.extend(["-f", "bestaudio[ext=m4a]/bestaudio/best", "-x", "--audio-format", "mp3"])
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
    filename = os.path.basename(filepath) if filepath else fallback.get("filename")
    media_id, extractor = get_media_identity(output_info)
    if not media_id:
        media_id = fallback.get("media_id") or ""
    if not extractor:
        extractor = fallback.get("extractor") or ""
    title = get_media_display_title(output_info, fallback.get("title") or job["url"])
    channel = output_info.get("uploader") or output_info.get("channel") or fallback.get("channel") or ""
    source_url = output_info.get("webpage_url") or output_info.get("original_url") or job["url"]
    thumbnail_file = find_thumbnail_sidecar(filename)
    return {
        "uuid": item_uuid or str(uuid.uuid4()),
        "timestamp": file_download_timestamp(filepath),
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
        "filepath": filepath or "unknown",
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
            'url': request_url,
            'resolution': resolution,
            'source': job["source"],
            'restored': job["restored"],
            'attempts': job["attempts"],
            'playlist_mode': job["playlist_mode"],
            'write_thumbnail': job["write_thumbnail"],
            'section_mode': job["section_mode"],
            'section_start': job["section_start"],
            'status': 'extracting_info',
            'progress': 0,
            'title': video_title,
            'channel': channel_name,
            'thumbnail': thumbnail_url,
            'duration_seconds': duration_seconds,
            'media_id': media_id,
            'extractor': extractor,
            'speed': '',
            'eta': '',
            'start_time': time.time()
        }
        
        download_manager.set_current_download(download_info)
        download_manager.send_message("Getting video information...")
        download_manager.update_progress(0)

        try:
            metadata = fetch_media_metadata(request_url, download_uuid)
            video_title = get_media_display_title(metadata, video_title)
            channel_name = metadata.get("uploader") or metadata.get("channel") or ""
            thumbnail_url = metadata.get("thumbnail") or ""
            duration_seconds = metadata.get("duration") or 0
            media_id, extractor = get_media_identity(metadata)
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
            failure_diagnostics.append(e)
            print(f"Info extraction error: {sanitize_diagnostic_text(e)}")

        if shutdown_event.is_set():
            download_manager.defer_current_download()
            return
        if download_manager.consume_cancellation(download_uuid):
            complete_cancellation()
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

        # Download start
        display_info = video_title
        if channel_name:
            display_info = f"{video_title} by {channel_name}"
            
        download_manager.update_status('downloading')
        download_manager.send_message(f"[Started] downloading {display_info} resolution below {resolution}")
        download_manager.update_progress(5)
        
        cmd = build_youtube_dl_cmd(job)
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
        failure_code = classify_download_failure(failure_diagnostics, e)
        download_manager.send_message("Download error occurred")
        download_manager.complete_download(terminal_history_item("error", failure_code))

import mimetypes

def resolve_history_file(uuid):
    download_manager.load_history()
    file_info = download_manager.get_combined_history_item(uuid)
    if not file_info:
        abort(404, "File not found")

    actual_filename = file_info.get('filename')
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
        safe_download_name = re.sub(r'[\\/:*?"<>|⧸]', '-', actual_filename)
        safe_download_name = safe_download_name.replace("'\"'\"'", "'")  # 이스케이핑된 따옴표 처리
        # Check to preserve file extensions
        original_ext = os.path.splitext(actual_filename)[1]
        if original_ext and not safe_download_name.endswith(original_ext):
            safe_download_name += original_ext
        
        print(f"Serving history file {uuid} as an attachment")
        
        # Find the original file with actual_filename and use safe_download_name for the download name.
        return static_file(actual_filename, root=DOWNFOLDER_DIR, download=safe_download_name)
    
        
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
        return static_file(actual_filename, root=DOWNFOLDER_DIR)
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
    return static_file(thumbnail_filename, root=DOWNFOLDER_DIR)
    

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
queue_state_lock = Lock()
queue_operation_lock = Lock()
shutdown_event = Event()
active_queue_job = None
queue_restore_count = 0
queue_state_loaded = False

def run_server():
    global port, proxy
    shutdown_event.clear()
    data = load_auth_data()
    if data.get("APP_PORT"):
        port = data["APP_PORT"]
    if data.get("PROXY"):
        proxy = data["PROXY"]

    load_persisted_queue()
    start_download_thread_if_needed()
    try:
        run(host="0.0.0.0", port=port, server=GeventWebSocketServer)
    finally:
        shutdown_event.set()
        dl_q.put(None)
        if download_thread and download_thread.is_alive():
            download_thread.join(timeout=5)

if __name__ == "__main__":
    run_server()
