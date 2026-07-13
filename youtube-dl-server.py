import json
import subprocess
from queue import Queue
import re
import time
import uuid
import hmac
import shlex
from datetime import datetime, timedelta
from collections import defaultdict
from bottle import run, Bottle, request, static_file, response, route, post, redirect, template, get, abort, HTTPError
from threading import Thread
from bottle_websocket import GeventWebSocketServer
from bottle_websocket import websocket
from socket import error
from geventwebsocket.exceptions import WebSocketError
import os
import secrets
from urllib.parse import quote

DOWNFOLDER_DIR = os.environ.get("DOWNLOAD_DIR", "./downfolder")
STATE_DIR = os.path.abspath(os.environ.get("STATE_DIR", "./metadata"))
AUTH_FILE = os.environ.get("AUTH_FILE", "Auth.json")
APP_STATE_FILE = os.path.join(STATE_DIR, "app_state.json")
HISTORY_FILE = os.path.join(STATE_DIR, "download_history.json")
APP_VERSION = os.environ.get("APP_VERSION", "26.0713")
API_TOKEN = os.environ.get("YDLNAS_API_TOKEN", "").strip()
YTDLP_COOKIES_FILE = os.environ.get("YTDLP_COOKIES_FILE", "").strip()
YTDLP_EXTRA_ARGS = os.environ.get("YTDLP_EXTRA_ARGS", "").strip()
VALID_RESOLUTIONS = {"best", "audio", "audio-m4a", "audio-mp3"}
RESOLUTION_PATTERN = re.compile(r"^\d{3,4}p$")
SUBTITLE_PATTERN = re.compile(r"^(vtt|srt)\|([A-Za-z0-9_-]+(?:-[A-Za-z0-9_-]+)*)$")
VIDEO_EXTENSIONS = {".mp4", ".m4v", ".mkv", ".mov", ".webm", ".avi"}
AUDIO_EXTENSIONS = {".mp3", ".m4a", ".aac", ".flac", ".opus", ".ogg", ".wav"}
SUBTITLE_EXTENSIONS = {".srt", ".vtt", ".ass", ".ssa"}
SKIPPED_DOWNFOLDER_NAMES = {".incomplete", ".DS_Store"}
SHARED_URL_PATTERN = re.compile(r"https?://[^\s<>\"]+", re.IGNORECASE)

os.makedirs(STATE_DIR, exist_ok=True)

def json_error(msg, status=400):
    response.status = status
    return {"success": False, "msg": msg}

def get_request_json():
    return request.json if isinstance(request.json, dict) else {}

def load_json_file(path, default=None):
    try:
        with open(path, encoding="utf-8") as data_file:
            return json.load(data_file)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {} if default is None else default

def save_app_state(updates):
    state = load_json_file(APP_STATE_FILE, {})
    state.update(updates)
    os.makedirs(STATE_DIR, exist_ok=True)
    temp_path = APP_STATE_FILE + ".tmp"
    with open(temp_path, "w", encoding="utf-8") as state_file:
        json.dump(state, state_file, indent=2, ensure_ascii=True)
    os.replace(temp_path, APP_STATE_FILE)
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

def cookie_secure_enabled():
    return os.environ.get("COOKIE_SECURE", "false").lower() == "true"

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

def queue_shared_url(shared_url):
    validation_error = validate_download_request(shared_url, "best")
    if validation_error:
        redirect("/youtube-dl?shared=invalid")

    download_manager.send_message("Shared URL received. Added to the NAS queue.")
    enqueue_download(shared_url, "best", "web", ws_addr.wsClassVal)
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
        "metadata_status": "missing"
    })

def list_mounted_file_items():
    if not os.path.isdir(DOWNFOLDER_DIR):
        return []

    items = []
    try:
        for filename in os.listdir(DOWNFOLDER_DIR):
            if filename in SKIPPED_DOWNFOLDER_NAMES or filename.startswith("."):
                continue
            file_path = safe_downfolder_path(filename)
            if not file_path or not os.path.isfile(file_path):
                continue
            item = build_mounted_file_item(filename)
            if item:
                items.append(item)
    except Exception as e:
        print(f"Failed to scan mounted folder files: {e}")
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
    item.setdefault('duration_seconds', 0)
    item.setdefault('status', 'unknown')
    item.setdefault('filepath', '')
    item.setdefault('source', 'history')
    item.setdefault('metadata_status', 'saved' if item.get('source') != 'mounted_folder' else 'missing')
    item['filename'] = filename
    item['file_exists'] = file_exists
    item['file_size_bytes'] = file_size_bytes
    item['download_type'] = infer_download_type(item.get('resolution', ''), filename)
    item.setdefault('progress', 0)
    return item

def start_download_thread_if_needed():
    global download_thread
    if download_thread is None or not download_thread.is_alive():
        download_thread = Thread(target=dl_worker, name="download-worker", daemon=True)
        download_thread.start()

def enqueue_download(url, resolution, source, ws=None):
    dl_q.put((url.strip(), ws, resolution.strip(), source))
    start_download_thread_if_needed()

def get_queued_downloads():
    queued_items = []
    for position, item in enumerate(list(dl_q.queue), start=1):
        if not item:
            continue
        queued_items.append({
            "position": position,
            "url": item[0] if len(item) > 0 else "",
            "resolution": item[2] if len(item) > 2 else "",
            "source": item[3] if len(item) > 3 else "web",
        })
    return queued_items

# single use global download manager
class GlobalDownloadManager:
    def __init__(self):
        self.current_download = None  # presently active download information
        self.download_history = []  # history of download info
        self.connected_clients = set() #every websocket clients
        self.is_downloading = False
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
                print(f"Failed to load history: {e}")
                self.download_history = []
    
    def save_history(self):        
        """Save history to file"""
        try:
            temp_path = self.history_file + ".tmp"
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(self.download_history, f, indent=2, ensure_ascii=False)
            os.replace(temp_path, self.history_file)
        except Exception as e:
            print(f"Failed to save history: {e}")
    
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
            print(f"Failed to delete history item: {e}")
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
        self.current_download = download_info
        self.is_downloading = True
        self.broadcast_to_all_clients(f"[RESTORE_ACTIVE], {json.dumps(download_info)}")
    
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
    
    def complete_download(self, completion_info):
        """Handle download completion"""
        if 'uuid' not in completion_info or not completion_info['uuid']:
            completion_info['uuid'] = str(uuid.uuid4())
            
        # 히스토리에 추가
        history_item = dict(completion_info)
        if not history_item.get('timestamp'):
            history_item['timestamp'] = datetime.now().isoformat()
        history_item = normalize_history_item(history_item)
        self.download_history.append(history_item)

        # Limit history size (max 100 items)
        if len(self.download_history) > 100:
            self.download_history = self.download_history[-100:]

        # Save to file
        self.save_history()
                
        # Send completion message in JSON format
        complete_data = normalize_history_item(history_item)
        
        # Serialize to JSON and send
        message = f"[COMPLETE], {json.dumps(complete_data, ensure_ascii=False)}"
        self.broadcast_to_all_clients(message)

        # Reset current download information
        self.current_download = None
        self.is_downloading = False
    
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
                print(f"Sent history item {idx}: {history_item.get('title', 'Unknown')}")
            except Exception as e:
                print(f"Error sending history item {idx}: {e}")

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
            'connected_clients': len(self.connected_clients)
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

@get('/')
def dl_queue_list():        
    """Displays the login page or redirects to terms page if not accepted."""
    next_path = safe_next_path(request.query.get("next"), "/youtube-dl")
    try:
        data = load_auth_data()
        if data.get("TERMS_ACCEPTED") != "Y":
            redirect("/terms?next=" + quote(next_path, safe=""))
    except Exception as e:
        print(f"Error checking terms acceptance: {e}")
        redirect("/terms?next=" + quote(next_path, safe=""))
        
    return template("./static/template/login.tpl", msg="", app_version=APP_VERSION, next_path=next_path)

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

    return template(
        "./static/template/login.tpl",
        msg="id or password is not correct",
        app_version=APP_VERSION,
        next_path=next_path,
    )

@get('/logout')
def dl_queue_logout():
    response.delete_cookie("account", path="/")
    redirect("/")

@route('/terms')
def terms_page():
    """Displays the terms of use page."""
    next_path = safe_next_path(request.query.get("next"), "/youtube-dl")
    return template(
        'static/template/terms.tpl',
        next_path_json=json.dumps(next_path),
        app_version=APP_VERSION,
    )

@post('/accept-terms')
def accept_terms():
    """Persist terms acceptance and the signed-cookie secret."""
    try:
        data = load_auth_data()
        save_app_state({"TERMS_ACCEPTED": "Y", "SECRET_KEY": data["SECRET_KEY"]})
        return {'success': True}
    except Exception as e:
        print(f"Error accepting terms: {e}")
        return {'success': False, 'msg': str(e)}
    

@get('/youtube-dl')
def dl_queue_main():
    try:
        data = load_auth_data()
        if data.get("TERMS_ACCEPTED") != "Y":
            redirect('/terms')
    except Exception as e:
        print(f"Error checking terms acceptance: {e}")
        redirect('/terms')

    if is_cookie_authenticated(data):
        return template("./static/template/index.tpl", userNm=data["MY_ID"], app_version=APP_VERSION)

    redirect("/")

@get('/health')
def health_check():
    response.content_type = "application/json"
    return {
        "status": "ok",
        "app": "youtube-dl-nas",
        "version": APP_VERSION,
        "queue_count": dl_q.qsize(),
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
        "connected_clients": len(download_manager.connected_clients)
    }

@get('/youtube-dl/q', method='POST')
def q_put():
    _, error_response = require_cookie_auth()
    if error_response:
        return error_response

    payload = get_request_json()
    url = payload.get("url")
    resolution = payload.get("resolution")

    validation_error = validate_download_request(url, resolution)
    if validation_error:
        return json_error(validation_error, 400)

    download_manager.send_message('We received your download. Please wait.')
    enqueue_download(url, resolution, "web", ws_addr.wsClassVal)
    return {"success": True, "msg": 'We received your download. Please wait.'}

@get('/youtube-dl/rest', method='POST')
def q_put_rest():
    payload = get_request_json()
    url = payload.get("url")
    resolution = payload.get("resolution")

    data = load_auth_data()
    if not is_api_authenticated(payload, data):
        return json_error("Invalid password, account, or API token.", 403)

    validation_error = validate_download_request(url, resolution)
    if validation_error:
        return json_error(validation_error, 400)

    enqueue_download(url, resolution, "api", "")
    return {"success": True, "msg": 'download has started', "Remaining downloading count": json.dumps(dl_q.qsize()) }

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
        print(f"Failed to delete file: {e}")
        return json_error("Failed to delete physical file", 500)

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
        "deleted_uuids": related_uuids
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

    download_manager.send_message('We received your retry request. Please wait.')
    enqueue_download(url, resolution, "web", ws_addr.wsClassVal)
    return {"success": True, "msg": "Download queued again", "Remaining downloading count": json.dumps(dl_q.qsize())}

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
    
def dl_worker():
    while True:
        item = dl_q.get()
        try:
            if item is None:
                return
            download(item)
        except Exception as e:
            print(f"Download worker error: {e}")
        finally:
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


def fetch_media_metadata(media_url):
    command = build_ytdlp_common_args() + [
        "--dump-single-json",
        "--playlist-items", "1",
        "--no-warnings",
        media_url,
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
    if result.returncode != 0 or not result.stdout.strip():
        return {}
    metadata = json.loads(result.stdout)
    entries = metadata.get("entries") if isinstance(metadata, dict) else None
    if isinstance(entries, list):
        first_entry = next((entry for entry in entries if isinstance(entry, dict)), None)
        if first_entry:
            metadata = {**metadata, **first_entry}
    return metadata if isinstance(metadata, dict) else {}


def build_youtube_dl_cmd(url):
    validation_error = validate_download_request(url[0] if len(url) > 0 else None, url[2] if len(url) > 2 else None)
    if validation_error:
        raise ValueError(validation_error)

    unsafe_chars_pattern = "[\\\\/:*?\"'<>|&+\\$%@!~=;,^#(){}\\[\\] ]"
    cmd = build_ytdlp_common_args() + [
        "--replace-in-metadata", "title", unsafe_chars_pattern, "_",
        "--paths", f"home:{DOWNFOLDER_DIR}",
        "--paths", f"temp:{os.path.join(DOWNFOLDER_DIR, '.incomplete')}",
        "-o", "%(title)s.%(ext)s",
    ]
    if url[2] == "best":
        cmd.extend(["-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]", "--merge-output-format", "mp4"])
    elif url[2] in ("audio-m4a", "audio"):
        cmd.extend(["-f", "bestaudio[ext=m4a]"])
    elif url[2] == "audio-mp3":
        cmd.extend(["-f", "bestaudio[ext=m4a]", "-x", "--audio-format", "mp3"])
    elif re.match(r"(vtt|srt)", url[2]):
        sub_format, sub_lang = url[2].split('|', 1)
        cmd.extend(["--write-auto-subs", "--sub-langs", sub_lang, "--sub-format", sub_format, "--skip-download"])
    else:
        resolution = url[2][:-1]
        cmd.extend(["-f", "bestvideo[height<="+resolution+"][ext=mp4]+bestaudio[ext=m4a]"])

    if not re.match(r"(vtt|srt)", url[2]):
        cmd.extend(["--print", "after_move:__YDLNAS_FILE__:%(filepath)s"])
    cmd.append(url[0])
    print(" ".join(cmd))
    return cmd


def download(url):
    try:
        # Generate UUID at function start time
        download_uuid = str(uuid.uuid4())
        
        # Download information initialization
        video_title = url[0]
        channel_name = ""
        thumbnail_url = ""
        duration_seconds = 0
        current_progress = 5  # Initialize current_progress here
        final_filepath = None
        filename = None  # Initialize filename here

        # Download status setting
        download_info = {
            'url': url[0],
            'resolution': url[2],
            'status': 'extracting_info',
            'progress': 0,
            'title': video_title,
            'channel': channel_name,
            'thumbnail': thumbnail_url,
            'duration_seconds': duration_seconds,
            'speed': '',
            'eta': '',
            'start_time': time.time()
        }
        
        download_manager.set_current_download(download_info)
        download_manager.send_message("Getting video information...")
        download_manager.update_progress(0)

        try:
            metadata = fetch_media_metadata(url[0])
            video_title = metadata.get("title") or metadata.get("playlist_title") or video_title
            channel_name = metadata.get("uploader") or metadata.get("channel") or ""
            thumbnail_url = metadata.get("thumbnail") or ""
            duration_seconds = metadata.get("duration") or 0
            if download_manager.current_download:
                download_manager.current_download['duration_seconds'] = duration_seconds
            download_manager.send_title(video_title)
            if channel_name:
                download_manager.send_channel(channel_name)
            if thumbnail_url:
                download_manager.send_thumbnail(thumbnail_url)
        except Exception as e:
            print(f"Info extraction error: {e}")

        # Download start
        display_info = video_title
        if channel_name:
            display_info = f"{video_title} by {channel_name}"
            
        download_manager.update_status('downloading')
        download_manager.send_message(f"[Started] downloading {display_info} resolution below {url[2]}")
        download_manager.update_progress(5)
        
        cmd = build_youtube_dl_cmd(url)
        print(f"Executing command: {' '.join(cmd)}")
        
        process = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1
        )
        

        dn_type = download_info.get('resolution')
        
        # Read yt-dlp output
        while True:
            line = process.stdout.readline()
            if not line and process.poll() is not None:
                break
            if line:
                print(f"yt-dlp output: {line.strip()}")

                plain_line = re.sub(r'\x1b\[[0-9;]*m', '', line)
                transfer_match = re.search(r'\bat\s+([^\s]+/s)\s+ETA\s+([0-9:]+)', plain_line)
                if transfer_match:
                    download_manager.update_transfer_stats(transfer_match.group(1), transfer_match.group(2))

                # Capture the final path emitted after post-processing.
                if re.match(r"(vtt|srt)",dn_type):
                    
                    exec_match = re.search(
                        r"\[(?:info|download)\] (?:Writing video subtitles to|Destination):\s+(.+?\.(?:srt|vtt))(?:\s|$)",
                        line,
                    )
                    if exec_match and not final_filepath:                        
                        subtitle_path = exec_match.group(1)
                        filename = os.path.basename(subtitle_path)
                        final_filepath = subtitle_path
                        print(f"Extracted subtitle filename: {filename}")
                else:
                    final_path_match = re.search(r"__YDLNAS_FILE__:(.+)$", line.strip())
                    if final_path_match:
                        final_filepath = final_path_match.group(1).strip()
                        filename = os.path.basename(final_filepath)
                        print(f"Final file: {filename}")
                

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
                            print(f"Progress: {adjusted_progress}%")
                    except Exception as e:
                        print(f"Progress parsing error: {e}")

                # Merge process detection
                if "[Merger] Merging formats" in line:
                    download_manager.update_status('merging')
                    download_manager.send_message("Merging files...")
                    download_manager.update_progress(95)
        
        return_code = process.poll()
        print(f"Process finished with return code: {return_code}")
        print("-------------------------------------------------")
        # Completion handling
        if return_code == 0:
            download_manager.update_status('completed')
            download_manager.send_message(f"[Finished] downloading {display_info} completed")
            download_manager.update_progress(100)
            # Save download history
            download_info = {  
                'uuid': download_uuid,              
                'timestamp': datetime.now().isoformat(),
                'url': url[0],
                'resolution': url[2],
                'title': video_title,
                'channel': channel_name,
                'thumbnail': thumbnail_url,
                'duration_seconds': duration_seconds,
                'status': 'completed',
                'filepath': final_filepath if final_filepath else "unknown",
                'filename': filename,
                'progress': 100
                
            }


            # Save download history
            download_manager.complete_download(download_info)
        else:
            download_manager.send_message(f"[Finished] downloading failed {display_info}")
            download_manager.complete_download({
                'uuid': download_uuid,
                'url': url[0],
                'resolution': url[2],
                'title': video_title,
                'channel': channel_name,
                'thumbnail': thumbnail_url,
                'duration_seconds': duration_seconds,
                'status': 'failed',
                'progress': current_progress
            })
            
        print(f"Download completed: {video_title}")
            
    except Exception as e:
        print(f"Download error: {e}")
        download_manager.send_message("Download error occurred")
        download_manager.complete_download({
            'uuid': str(uuid.uuid4()), # Generate new UUID for error case
            'url': url[0] if url else 'unknown',
            'resolution': url[2] if len(url) > 2 else 'unknown',
            'title': video_title if 'video_title' in locals() else 'unknown',
            'channel': channel_name if 'channel_name' in locals() else '',
            'thumbnail': thumbnail_url if 'thumbnail_url' in locals() else '',
            'duration_seconds': duration_seconds if 'duration_seconds' in locals() else 0,
            'status': 'error',
            'progress': 0
        })

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
        print(f"Serving file: {actual_filename}")
        safe_download_name = re.sub(r'[\\/:*?"<>|⧸]', '-', actual_filename)
        safe_download_name = safe_download_name.replace("'\"'\"'", "'")  # 이스케이핑된 따옴표 처리
        # Check to preserve file extensions
        original_ext = os.path.splitext(actual_filename)[1]
        if original_ext and not safe_download_name.endswith(original_ext):
            safe_download_name += original_ext
        
        print(f"Serving file: {actual_filename} as {safe_download_name}")
        
        # Find the original file with actual_filename and use safe_download_name for the download name.
        return static_file(actual_filename, root=DOWNFOLDER_DIR, download=safe_download_name)
    
        
    except HTTPError:
        raise
    except Exception as e:
        print(f"Error in serve_download: {e}")
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
        print(f"Error in serve_preview: {e}")
        abort(500, "Internal server error")
    

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
                
            print(f"Received: {message}")

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
        print(f"WebSocket error: {e}")
    finally:
        # Disconnect the client
        download_manager.remove_client(ws)
        if ws_addr.wsClassVal == ws:
            ws_addr.wsClassVal = None
        print(f"WebSocket disconnected")

# Global variable initialization
dl_q = Queue()
download_thread = None

def run_server():
    global port, proxy
    data = load_auth_data()
    if data.get("APP_PORT"):
        port = data["APP_PORT"]
    if data.get("PROXY"):
        proxy = data["PROXY"]

    start_download_thread_if_needed()
    try:
        run(host="0.0.0.0", port=port, server=GeventWebSocketServer)
    finally:
        dl_q.put(None)
        if download_thread and download_thread.is_alive():
            download_thread.join(timeout=5)

if __name__ == "__main__":
    run_server()
