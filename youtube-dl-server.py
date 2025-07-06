import json
import subprocess
from queue import Queue
import re
import time
import uuid
from datetime import datetime, timedelta
from collections import defaultdict
from bottle import run, Bottle, request, static_file, response, route, post, redirect, template, get, abort
from threading import Thread
from bottle_websocket import GeventWebSocketServer
from bottle_websocket import websocket
from socket import error
from geventwebsocket.exceptions import WebSocketError
import os
import secrets
import string

# single use global download manager
class GlobalDownloadManager:
    def __init__(self):
        self.current_download = None  # presently active download information
        self.download_history = []  # history of download info
        self.connected_clients = set() #every websocket clients
        self.is_downloading = False
        self.history_file = './metadata/download_history.json'
        self.load_history()
    
    def load_history(self):
        """Load saved history"""        
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    self.download_history = json.load(f)
                print(f"Loaded {len(self.download_history)} history items")
            except Exception as e:
                print(f"Failed to load history: {e}")
                self.download_history = []
    
    def save_history(self):        
        """Save history to file"""
        try:
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(self.download_history, f, indent=2, ensure_ascii=False)
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
            self.download_history = [item for item in self.download_history if item.get('uuid') != uuid]
            self.save_history()
            self.broadcast_to_all_clients(f"[HISTORY_DELETED], {uuid}")
            return True
        except Exception as e:
            print(f"Failed to delete history item: {e}")
            return False
    
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
        history_item = {
            'timestamp': datetime.now().isoformat(),
            **completion_info
        }
        self.download_history.append(history_item)

        # Limit history size (max 100 items)
        if len(self.download_history) > 100:
            self.download_history = self.download_history[-100:]

        # Save to file
        self.save_history()
                
        # Send completion message in JSON format
        complete_data = {
            'resolution': completion_info.get('resolution', ''),
            'channel': completion_info.get('channel', ''),
            'title': completion_info.get('title', ''),
            'filepath': completion_info.get('filepath', ''),
            'filename': completion_info.get('filename', ''),
            'uuid': completion_info.get('uuid', '')
        }
        
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
        print(f"Sending {len(self.download_history)} history items to new client")

        # Send all history items individually
        for idx, history_item in enumerate(self.download_history):
            try:
                # Add UUID to history item
                history_with_uuid = {
                    'uuid': history_item.get('uuid', str(uuid.uuid4())),
                    **history_item
                }
                safe_websocket_send(ws, f"[RESTORE_HISTORY], {json.dumps(history_with_uuid)}")
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
    #Check the terms agreement flag in the Auth.json file
    try:
        with open('Auth.json') as data_file:
            data = json.load(data_file)
            # Check the TERMS_ACCEPTED flag
            terms_accepted = data.get('TERMS_ACCEPTED', 'N')
            
            # If the flag is not 'Y', redirect to the terms agreement page.
            if terms_accepted != 'Y':
                redirect('/terms')
    except Exception as e:
        print(f"Error checking terms acceptance: {e}")
        # If an error occurs, redirect to the terms and conditions page for security reasons.
        redirect('/terms')
        
    return template("./static/template/login.tpl", msg="")

@get('/login', method='POST')
def dl_queue_login():
    with open('Auth.json') as data_file:
        data = json.load(data_file)
        
        req_id = request.forms.get("id")
        req_pw = request.forms.get("myPw")

        if (req_id == data["MY_ID"] and req_pw == data["MY_PW"]):
            secret_key = data.get("SECRET_KEY")
            response.set_cookie("account", req_id, secret=secret_key)
            redirect("/youtube-dl")
        else:
            return template("./static/template/login.tpl", msg="id or password is not correct")

@route('/terms')
def terms_page():
    """Displays the terms of use page."""
    return template('static/template/terms.tpl')

@post('/accept-terms')
def accept_terms():
    """Updates Auth.json with terms acceptance."""
    try:
        # Reading the Auth.json file
        with open('Auth.json', 'r') as data_file:
            data = json.load(data_file)
        
        # Set the TERMS_ACCEPTED flag to 'Y'
        data['TERMS_ACCEPTED'] = 'Y'
        
        # Generate a cryptographically secure random secret key (32 characters)
        alphabet = string.ascii_letters + string.digits + string.punctuation
        random_secret = ''.join(secrets.choice(alphabet) for _ in range(32))
        # Save the generated secret key
        data['SECRET_KEY'] = random_secret
        
        # Save updated content to a file
        with open('Auth.json', 'w') as data_file:
            json.dump(data, data_file, indent=2)
        
        return {'success': True}
    except Exception as e:
        print(f"Error accepting terms: {e}")
        return {'success': False, 'msg': str(e)}
    

@get('/youtube-dl')
def dl_queue_main():
    
    # Check the terms agreement flag in the Auth.json file
    try:
        with open('Auth.json') as data_file:
            data = json.load(data_file)
            # Check the TERMS_ACCEPTED flag
            terms_accepted = data.get('TERMS_ACCEPTED', 'N')
            
            # If the flag is not 'Y', redirect to the terms agreement page.
            if terms_accepted != 'Y':
                redirect('/terms')
    except Exception as e:
        print(f"Error checking terms acceptance: {e}")
        # If an error occurs, redirect to the terms and conditions page for security reasons.
        redirect('/terms')
        
    secret_key = data.get("SECRET_KEY")
    userNm = request.get_cookie("account", secret=secret_key)
    print("CHK : ", userNm)

    if (userNm == data["MY_ID"]):
        return template("./static/template/index.tpl", userNm=userNm)
    else:
        print("no cookie or fail login")
        redirect("/")

@get('/youtube-dl/static/:filename#.*#')
def server_static(filename):
    return static_file(filename, root='./static')

@get('/youtube-dl/q', method='GET')
def q_size():
    return {"success": True, "size": json.dumps(list(dl_q.queue))}

@get('/youtube-dl/q', method='POST')
def q_put():
    url = request.json.get("url")
    resolution = request.json.get("resolution")

    if "" != url:
        # Send global message
        download_manager.send_message('We received your download. Please wait.')
        
        box = (url, ws_addr.wsClassVal, resolution, "web")
        dl_q.put(box)

        if (Thr.dl_thread.is_alive() == False):
            thr = Thr()
            thr.restart()

        return {"success": True, "msg": 'We received your download. Please wait.'}
    else:
        return {"success": False, "msg": "download queue somethings wrong."}

@get('/youtube-dl/rest', method='POST')
def q_put_rest():
    url = request.json.get("url")
    resolution = request.json.get("resolution")

    with open('Auth.json') as data_file:
        data = json.load(data_file)
        req_id = request.json.get("id")
        req_pw = request.json.get("pw")

        if (req_id != data["MY_ID"] or req_pw != data["MY_PW"]):
            return {"success": False, "msg": "Invalid password or account."}
        else:
            box = (url, "", resolution, "api")
            dl_q.put(box)
            return {"success": True, "msg": 'download has started', "Remaining downloading count": json.dumps(dl_q.qsize()) }

# History deletion API
@get('/youtube-dl/history/clear', method='POST')
def clear_history():
    """Clear all history"""    
    with open('Auth.json') as data_file:
        data = json.load(data_file)
    secret_key = data.get("SECRET_KEY")
    userNm = request.get_cookie("account", secret=secret_key)

    if userNm != data["MY_ID"]:
        return {"success": False, "msg": "Unauthorized"}
    # Delete all files under .downfolder
    if os.path.exists("./downfolder"):
        try:
            for filename in os.listdir("./downfolder"):
                file_path = os.path.join("./downfolder", filename)
                # metadata 디렉토리는 건드리지 않음
                if filename == "metadata":
                    continue
                if os.path.isfile(file_path):
                    os.remove(file_path)
            print("All files in ./downfolder have been deleted.")
        except Exception as e:
            print(f"Failed to delete files: {e}")

    # Call download_manager.clear_all_history() to clear history
    success = download_manager.clear_all_history()
    if success:
        return {"success": True, "msg": "All history cleared"}
    else:
        return {"success": False, "msg": "Failed to clear history"}


# Function to delete all history items in download_history.json with a specific filename
def delete_history_item_by_filename(filename):
    """Delete all history items with a specific file name"""
    original_len = len(download_manager.download_history)
    download_manager.download_history = [
        item for item in download_manager.download_history
        if item.get('filename') != filename
    ]
    download_manager.save_history()
    return len(download_manager.download_history) < original_len


def get_uuid_by_filename(filename):
    """Return a list of UUIDs for history items with a specific file name"""
    uuids = []
    for item in download_manager.download_history:
        if item.get('filename') == filename:
            uuids.append(item.get('uuid'))
    return uuids

def get_filename_by_uuid(uuid):
    """Return the file name for a history item with a specific UUID"""
    for item in download_manager.download_history:
        if item.get('uuid') == uuid:
            return item.get('filename', '')
    return None


@get('/youtube-dl/history/delete/<uuid>', method='POST')
def delete_history_item(uuid):
    """Delete a history item with a specific UUID"""
    
    with open('Auth.json') as data_file:
        data = json.load(data_file)
    secret_key = data.get("SECRET_KEY")
    if not secret_key:
        return {"success": False, "msg": "Secret key not found in Auth.json"}
    userNm = request.get_cookie("account", secret=secret_key)

    if userNm != data["MY_ID"]:
        return {"success": False, "msg": "Unauthorized"}

    file_name = get_filename_by_uuid(uuid)
    
    if os.path.exists(f"./downfolder/{file_name}") and file_name != "":
        try:
            print("Allways?")
            os.remove(f"./downfolder/{file_name}")
        except Exception as e:
            print(f"Failed to delete file: {e}")

    uuids = get_uuid_by_filename(file_name)
   
    #success = False
    success = False    
    for uuid in uuids:
        
        success = download_manager.delete_history_item(uuid)

    if not success:
        return {"success": False, "msg": "Failed to delete history item"}

    if success:
        print(f"Removed from download manager: {success}")
        return {"success": True, "msg": "History item deleted successfully"}
    else:
        return {"success": False, "msg": "Failed to delete history item"}

@get('/youtube-dl/history', method='GET')
def get_history():
    """Retrieve history"""
    
    with open('Auth.json') as data_file:
        data = json.load(data_file)
    secret_key = data.get("SECRET_KEY")
    if not secret_key:
        return {"success": False, "msg": "Secret key not found in Auth.json"}
    
    userNm = request.get_cookie("account", secret=secret_key)

    if userNm != data["MY_ID"]:
        return {"success": False, "msg": "Unauthorized"}
    
    return {
        "success": True, 
        "history": download_manager.download_history,
        "total": len(download_manager.download_history)
    }
    
def save_download_history(info):
    history_path = "./metadata/download_history.json"
    history = []
    if os.path.exists(history_path):
        try:
            with open(history_path, "r", encoding="utf-8") as f:
                history = json.load(f)
        except (json.JSONDecodeError, ValueError):
            history = []
    history.append(info)
    with open(history_path, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

def dl_worker():
    while not done:
        item = dl_q.get()
        if(item[3]=="web"):
            download(item)
        else:
            download_rest(item)
        dl_q.task_done()

def build_youtube_dl_cmd(url):
    with open('Auth.json') as data_file:
        data = json.load(data_file)  # Auth info, when docker run making file
        unsafe_chars_pattern = "[\\\\/:*?\"'<>|&+\\$%@!~\`=;,^#(){}\[\] ]"
        safe_replacement = "_"
        if (url[2] == "best"):
            cmd = ["yt-dlp", "--retry-sleep", "1", "--proxy", data['PROXY'], "--replace-in-metadata", "title", unsafe_chars_pattern, safe_replacement, "-o", "./downfolder/.incomplete/%(title)s.%(ext)s", "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]", "--exec", "touch {} && mv {} ./downfolder/", "--merge-output-format", "mp4", url[0]]
        # url[2] == "audio" for download_rest()
        elif (url[2] == "audio-m4a" or url[2] == "audio"):
            cmd = ["yt-dlp", "--retry-sleep", "1", "--proxy", data['PROXY'], "--replace-in-metadata", "title", unsafe_chars_pattern, safe_replacement, "-o", "./downfolder/.incomplete/%(title)s.%(ext)s", "-f", "bestaudio[ext=m4a]", "--exec", "touch {} && mv {} ./downfolder/", url[0]]
        elif (url[2] == "audio-mp3"):
            cmd = ["yt-dlp", "--retry-sleep", "1", "--proxy", data['PROXY'], "--replace-in-metadata", "title", unsafe_chars_pattern, safe_replacement, "-o", "./downfolder/.incomplete/%(title)s.%(ext)s", "-f", "bestaudio[ext=m4a]", "-x", "--audio-format", "mp3", "--exec", "touch {} && mv {} ./downfolder/", url[0]]
        elif re.match(r"(vtt|srt)", url[2]):
            sub_format = url[2].split('|')[0]
            sub_lang = url[2].split('|')[1]            
            cmd = ["yt-dlp", "--retry-sleep", "1", "--proxy", data['PROXY'], "--replace-in-metadata", "title", unsafe_chars_pattern, safe_replacement, "-o", "./downfolder/%(title)s.%(ext)s",  "--write-auto-subs", "--sub-langs", sub_lang, "--sub-format", sub_format, "--skip-download", url[0]]
        else:
            resolution = url[2][:-1]
            cmd = ["yt-dlp", "--retry-sleep", "1", "--proxy", data['PROXY'], "--replace-in-metadata", "title", unsafe_chars_pattern, safe_replacement, "-o", "./downfolder/.incomplete/%(title)s.%(ext)s", "-f", "bestvideo[height<="+resolution+"][ext=mp4]+bestaudio[ext=m4a]", "--exec", "touch {} && mv {} ./downfolder/",  url[0]]
        print (" ".join(cmd))
        return cmd
    


def download(url):
    try:
        # Generate UUID at function start time
        download_uuid = str(uuid.uuid4())
        
        # Download information initialization
        video_title = url[0]
        channel_name = ""
        thumbnail_url = ""
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
            'start_time': time.time()
        }
        
        download_manager.set_current_download(download_info)
        download_manager.send_message("Getting video information...")
        download_manager.update_progress(0)

        try:
            # title extraction
            title_result = subprocess.run(["yt-dlp", "--get-title", "--no-warnings", url[0]],
                                        capture_output=True, text=True, timeout=10)
            if title_result.returncode == 0 and title_result.stdout.strip():
                video_title = title_result.stdout.strip()
                print(f"Title extracted: {video_title}")
                download_manager.send_title(video_title)

            # channel name extraction
            channel_result = subprocess.run(["yt-dlp", "--get-filename", "-o", "%(uploader)s", "--no-warnings", url[0]],
                                          capture_output=True, text=True, timeout=10)
            
            if channel_result.returncode == 0 and channel_result.stdout.strip():
                channel_name = channel_result.stdout.strip()                
                download_manager.send_channel(channel_name)

            # thumbnail URL extraction
            thumbnail_result = subprocess.run(["yt-dlp", "--get-thumbnail", "--no-warnings", url[0]],
                                            capture_output=True, text=True, timeout=10)
            if thumbnail_result.returncode == 0 and thumbnail_result.stdout.strip():
                thumbnail_url = thumbnail_result.stdout.strip()
                print(f"Thumbnail extracted: {thumbnail_url}")
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

                 # Extract filename from exec command (alternative method)
                if re.match(r"(vtt|srt)",dn_type):
                    
                    exec_match = re.search(
                    #r"\[download\] Destination: (\.\/downfolder\/.+?\.(srt|vtt))\$", 
                    r"\[(?:info|download)\] (?:Writing video subtitles to|Destination): (\.\/downfolder\/.*?\.(srt|vtt))", 
                    line
                    )
                    if exec_match and not final_filepath:                        
                        subtitle_path = exec_match.group(1)
                        filename = os.path.basename(subtitle_path)
                        final_filepath = subtitle_path
                        print(f"Extracted subtitle filename: {filename}")
                else:                    
                    exec_match = re.search(
                    r"touch\s+(?:'|\")?(.+?)(?:'|\")?\s+&&\s+mv\s+(?:'|\")?(.+?)(?:'|\")?\s+\./downfolder/", 
                    line
                    )
                    if exec_match and not final_filepath:                        
                        source_path = exec_match.group(2)                                        
                        filename = os.path.basename(source_path)
                        final_filepath = os.path.join("./downfolder", filename)                        
                        print(f"Extracted filename from exec: {filename}")     
                

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
            'status': 'error',
            'progress': 0
        })

def download_rest(url):
    result = subprocess.run(build_youtube_dl_cmd(url))

import mimetypes
@get('/static/downfolder/<uuid>')
def serve_download(uuid):
    """File download using UUID"""

    
    with open('Auth.json') as data_file:
        data = json.load(data_file)
    secret_key = data.get("SECRET_KEY")
    
    if not secret_key:
        abort(500, "Secret key not found in Auth.json")
        
    userNm = request.get_cookie("account", secret=secret_key)        
    
    if userNm != data["MY_ID"]:
        abort(403, "Unauthorized")
    
    # Find file information by UUID
    history_path = "./metadata/download_history.json"
    if not os.path.exists(history_path):
        abort(404, "History file not found")
    
    
    try:
        with open(history_path, "r", encoding="utf-8") as f:
            history = json.load(f)
        
        # Retrieving file information by UUID
        file_info = None
        for item in history:
            if item.get('uuid') == uuid:
                file_info = item
                break        
        if not file_info:
            abort(404, "File not found in history")
        
        # Check file path
        filename = file_info.get('filename')
        filepath = file_info.get('filepath')
        
        if not filename and not filepath:
            abort(404, "File path not found")
        
        # Determine the actual file path
        if filename and filename != "unknown":
            actual_filename = filename
        elif filepath and filepath != "unknown":
            actual_filename = os.path.basename(filepath)
        else:
            abort(404, "Valid filename not found")
        
        file_path = os.path.join("./downfolder", actual_filename)
        if not os.path.exists(file_path):
            abort(404, "Physical file not found")
        
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
        return static_file(actual_filename, root='./downfolder', download=safe_download_name)
    
        
    except Exception as e:
        print(f"Error in serve_download: {e}")
        abort(500, "Internal server error")
    

# WebSocket handler
@get('/websocket')
@websocket
def websocket_handler(ws):
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
                for history_item in download_manager.download_history:
                    history_with_uuid = {
                        'uuid': history_item.get('uuid', str(uuid.uuid4())),
                        **history_item
                    }
                    safe_websocket_send(ws, f"[RESTORE_HISTORY], {json.dumps(history_with_uuid)}")
                safe_websocket_send(ws, "[HISTORY_RESTORE_COMPLETE], done")
                
    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        # Disconnect the client
        download_manager.remove_client(ws)
        if ws_addr.wsClassVal == ws:
            ws_addr.wsClassVal = None
        print(f"WebSocket disconnected")

class Thr:
    def __init__(self):
        self.dl_thread = ''

    def restart(self):
        self.dl_thread = Thread(target=dl_worker)
        self.dl_thread.start()

# Global variable initialization
dl_q = Queue()
done = False
Thr.dl_thread = Thread(target=dl_worker)
Thr.dl_thread.start()

# Read configuration file
with open('Auth.json') as env_file:
    data = json.load(env_file)

if (data['APP_PORT'] !=''):
    port = data['APP_PORT']
if (data['PROXY'] !=''):
    proxy = data['PROXY']

# Start server
run(host='0.0.0.0', port=port, server=GeventWebSocketServer)

done = True
Thr.dl_thread.join()