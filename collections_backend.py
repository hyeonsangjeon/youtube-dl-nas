"""Durable collection plans, media membership, and scoped connection credentials."""

import copy
import hashlib
import hmac
import json
import os
import re
import secrets
import stat
import time
import unicodedata
import uuid
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from datetime import date, datetime, timezone
from functools import wraps
from threading import RLock
from urllib.parse import unquote


STATE_VERSION = 1
PLAN_TTL_SECONDS = 1800
PREVIEW_TIMEOUT_SECONDS = 900
PREVIEW_WORK_TIMEOUT_SECONDS = 840
COMMIT_TIMEOUT_SECONDS = 120
PROGRESS_STATES = ("queued", "running", "completed", "skipped", "failed", "missing")
TERMINAL_STATES = {"completed", "skipped", "failed", "missing"}
DIRECTORY_PATTERN = re.compile(r"^collections/[a-z0-9][a-z0-9-]{0,79}--[0-9a-f]{12}$")
REQUEST_IDENTITY_FIELDS = (
    "url", "resolution", "playlist_mode", "write_thumbnail", "section_mode", "section_start",
    "media_id", "extractor",
)


class StateError(RuntimeError):
    """An unreadable or unpersisted state must not be treated as an empty store."""


class APIError(ValueError):
    def __init__(self, code, status=400):
        super().__init__(code)
        self.code = code
        self.status = status


def _io_wrapper(function, authentication=False):
    @wraps(function)
    def wrapped(*args, **kwargs):
        from gevent import Greenlet, get_hub, getcurrent

        if isinstance(getcurrent(), Greenlet):
            hub = get_hub()
            pool = hub.threadpool
            if authentication:
                pool = getattr(hub, "_ydlnas_auth_pool", None)
                if pool is None:
                    from gevent.threadpool import ThreadPool
                    pool = hub._ydlnas_auth_pool = ThreadPool(2, hub=hub)

            def execute():
                try:
                    return True, function(*args, **kwargs)
                except Exception as error:
                    return False, error

            # gevent logs uncaught worker exceptions with their call arguments.
            # Transport errors as values so credentials never enter that log.
            succeeded, result = pool.apply(execute)
            if not succeeded:
                raise result
            return result
        return function(*args, **kwargs)
    return wrapped


def nonblocking_io(function):
    """Offload blocking service work, never Bottle request/response handling."""
    return _io_wrapper(function)


def nonblocking_auth_io(function):
    """Credential I/O must not queue behind stalled collection/state workers."""
    return _io_wrapper(function, authentication=True)


def utc_timestamp(timestamp=None):
    return datetime.fromtimestamp(time.time() if timestamp is None else timestamp, timezone.utc).isoformat()


def batch_limit():
    try:
        value = int(os.environ.get("YDLNAS_MCP_BATCH_LIMIT", "25"))
    except (TypeError, ValueError):
        value = 25
    return min(100, max(1, value))


def relative_media_path(value, allow_empty=False):
    if not isinstance(value, str) or (not value and not allow_empty):
        return None
    if not value:
        return ""
    for candidate in (value, unquote(value)):
        if (
            candidate.startswith("/")
            or "\\" in candidate
            or re.match(r"^[a-zA-Z]:", candidate)
            or any(ord(char) < 32 or ord(char) == 127 for char in candidate)
            or any(part in {"", ".", ".."} for part in candidate.split("/"))
        ):
            return None
    return value


def safe_media_path(root, relative, allow_empty=False):
    relative = relative_media_path(relative, allow_empty=allow_empty)
    if relative is None:
        return None
    root = os.path.abspath(root)
    if os.path.islink(root):
        return None
    candidate = root
    parts = relative.split("/") if relative else []
    for index, part in enumerate(parts):
        candidate = os.path.join(candidate, part)
        try:
            mode = os.lstat(candidate).st_mode
        except FileNotFoundError:
            continue
        except OSError:
            return None
        if stat.S_ISLNK(mode):
            return None
        if index < len(parts) - 1 and not stat.S_ISDIR(mode):
            return None
        if index == len(parts) - 1 and not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
            return None
    try:
        if os.path.commonpath((os.path.realpath(root), os.path.realpath(candidate))) != os.path.realpath(root):
            return None
    except ValueError:
        return None
    return candidate


@contextmanager
def media_parent(root, relative, create=False):
    relative = relative_media_path(relative)
    if relative is None or safe_media_path(root, relative) is None:
        raise APIError("unsafe_path")
    if create:
        os.makedirs(root, exist_ok=True)
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    descriptor = os.open(root, flags)
    try:
        parts = relative.split("/")
        for part in parts[:-1]:
            if create:
                try:
                    os.mkdir(part, dir_fd=descriptor)
                except FileExistsError:
                    pass
            child = os.open(part, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        yield descriptor, parts[-1]
    finally:
        os.close(descriptor)


def open_media_file(root, relative):
    with media_parent(root, relative) as (parent, name):
        descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
    if not stat.S_ISREG(os.fstat(descriptor).st_mode):
        os.close(descriptor)
        raise APIError("unsafe_path")
    return os.fdopen(descriptor, "rb")


def delete_media_file(root, relative):
    with media_parent(root, relative) as (parent, name):
        if not stat.S_ISREG(os.stat(name, dir_fd=parent, follow_symlinks=False).st_mode):
            raise APIError("unsafe_path")
        os.unlink(name, dir_fd=parent)


def ensure_media_directory(root, relative):
    marker = (relative + "/" if relative else "") + ".directory-check"
    with media_parent(root, marker, create=True):
        pass
    return safe_media_path(root, relative, allow_empty=True)


def atomic_json_write(path, payload, ensure_ascii=False):
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    staging = os.path.join(directory, "." + os.path.basename(path) + "." + secrets.token_hex(8) + ".pending")
    descriptor = None
    try:
        descriptor = os.open(staging, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            descriptor = None
            json.dump(payload, output, indent=2, ensure_ascii=ensure_ascii, allow_nan=False)
            output.flush()
            os.fsync(output.fileno())
        os.replace(staging, path)
        directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        try:
            os.unlink(staging)
        except FileNotFoundError:
            pass


def read_state(path, empty):
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            os.close(descriptor)
            raise StateError("Persistent state is not a regular file")
        with os.fdopen(descriptor, encoding="utf-8") as source:
            return json.load(source)
    except FileNotFoundError:
        return copy.deepcopy(empty)
    except (OSError, ValueError) as error:
        raise StateError("Persistent state could not be read") from error


def normalize_text(value, required=False, limit=2000):
    if not isinstance(value, str):
        raise APIError("invalid_collection_text")
    value = " ".join(unicodedata.normalize("NFKC", value).split())
    if (required and not value) or len(value) > limit or any(ord(char) < 32 for char in value):
        raise APIError("invalid_collection_text")
    return value


def match_text(value):
    return " ".join(unicodedata.normalize("NFKC", str(value or "")).casefold().split())


def normalize_criteria(value):
    if value is None:
        value = {}
    if not isinstance(value, dict) or set(value) - {"date_from", "date_to"}:
        raise APIError("invalid_date_range")
    result = {}
    for key in ("date_from", "date_to"):
        candidate = value.get(key)
        if candidate is not None:
            if not isinstance(candidate, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", candidate):
                raise APIError("invalid_date_range")
            try:
                date.fromisoformat(candidate)
            except ValueError as error:
                raise APIError("invalid_date_range") from error
        result[key] = candidate
    if result["date_from"] and result["date_to"] and result["date_from"] > result["date_to"]:
        raise APIError("invalid_date_range")
    return result


def metadata_upload_date(metadata):
    value = (metadata or {}).get("upload_date")
    if not isinstance(value, str):
        return None
    if re.fullmatch(r"\d{8}", value):
        value = value[:4] + "-" + value[4:6] + "-" + value[6:]
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return None
    try:
        date.fromisoformat(value)
    except ValueError:
        return None
    return value


def date_status(metadata, criteria):
    uploaded = metadata_upload_date(metadata)
    if not uploaded:
        return "date_unknown"
    if criteria.get("date_from") and uploaded < criteria["date_from"]:
        return "outside_date_range"
    if criteria.get("date_to") and uploaded > criteria["date_to"]:
        return "outside_date_range"
    return None


def normalize_date_policy(value):
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) - {"date_from", "date_to", "include_unknown_date"}:
        raise APIError("invalid_date_policy")
    result = normalize_criteria({key: value.get(key) for key in ("date_from", "date_to")})
    if not isinstance(value.get("include_unknown_date", False), bool):
        raise APIError("invalid_date_policy")
    result["include_unknown_date"] = value.get("include_unknown_date", False)
    return result


def policy_rejection(metadata, policy):
    if policy is None:
        return None
    status = date_status(metadata, policy)
    if status == "date_unknown" and policy.get("include_unknown_date"):
        return None
    return status


def is_direct_metadata(metadata):
    return bool(
        isinstance(metadata, dict)
        and metadata
        and metadata.get("_type", "video") not in {"playlist", "multi_video", "url", "url_transparent"}
        and "entries" not in metadata
    )


def valid_collection_target(collection_id, relative):
    try:
        suffix = uuid.UUID(str(collection_id)).hex[:12]
    except (ValueError, TypeError, AttributeError):
        return False
    return bool(
        isinstance(relative, str)
        and DIRECTORY_PATTERN.fullmatch(relative)
        and relative.endswith("--" + suffix)
    )


def reject_client_paths(payload):
    forbidden = {
        "path", "filepath", "filename", "relative_path", "physical_path", "physical_file",
        "target", "target_path", "target_dir", "target_directory", "target_relative_directory",
        "relative_directory", "directory", "download_dir", "output", "output_template",
        "args", "extra_args", "command", "date_policy",
    }
    if isinstance(payload, dict):
        for key, value in payload.items():
            if str(key).casefold() in forbidden:
                raise APIError("caller_path_forbidden")
            reject_client_paths(value)
    elif isinstance(payload, list):
        for value in payload:
            reject_client_paths(value)


class ConnectionStore:
    def __init__(self, path):
        self.path = path
        self.lock = RLock()
        self._load()

    def _load(self):
        state = read_state(self.path, {"version": STATE_VERSION, "connections": {}})
        if not isinstance(state, dict) or state.get("version") != STATE_VERSION or not isinstance(state.get("connections"), dict):
            raise StateError("Invalid connection state")
        for key, item in state["connections"].items():
            if (
                not isinstance(item, dict)
                or item.get("id") != key
                or not isinstance(item.get("token_hash"), str)
                or not re.fullmatch(r"[0-9a-f]{64}", item["token_hash"])
                or not all(field in item for field in ("name", "prefix", "created_at", "last_used_at", "revoked_at"))
            ):
                raise StateError("Invalid connection record")
        return state

    @staticmethod
    def public(item):
        return {key: item.get(key) for key in ("id", "name", "prefix", "created_at", "last_used_at", "revoked_at")}

    @nonblocking_auth_io
    def list(self):
        with self.lock:
            return [self.public(item) for item in self._load()["connections"].values()]

    @nonblocking_auth_io
    def create(self, name):
        name = normalize_text(name, required=True, limit=120)
        token = "ydlnas_" + secrets.token_urlsafe(32)
        item = {
            "id": str(uuid.uuid4()),
            "name": name,
            "prefix": token[:15],
            "token_hash": hashlib.sha256(token.encode("utf-8")).hexdigest(),
            "created_at": utc_timestamp(),
            "last_used_at": None,
            "revoked_at": None,
        }
        with self.lock:
            state = self._load()
            state["connections"][item["id"]] = item
            atomic_json_write(self.path, state)
        return {"connection": self.public(item), "token": token}

    @nonblocking_auth_io
    def revoke(self, connection_id):
        with self.lock:
            state = self._load()
            item = state["connections"].get(connection_id)
            if not item:
                raise APIError("connection_not_found", 404)
            if not item["revoked_at"]:
                item["revoked_at"] = utc_timestamp()
                atomic_json_write(self.path, state)

    @nonblocking_auth_io
    def validate(self, token):
        if not isinstance(token, str) or not token or len(token) > 512:
            return False
        supplied = hashlib.sha256(token.encode("utf-8")).hexdigest()
        with self.lock:
            state = self._load()
            matched = None
            for item in state["connections"].values():
                equal = hmac.compare_digest(supplied, item["token_hash"])
                if equal and not item["revoked_at"]:
                    matched = item
            if matched is None:
                return False
            matched["last_used_at"] = utc_timestamp()
            atomic_json_write(self.path, state)
            return True


class CollectionService:
    def __init__(self, server, path):
        self.server = server
        self.path = path
        self.lock = RLock()
        self.state = read_state(path, {
            "version": STATE_VERSION, "collections": {}, "memberships": {}, "plans": {}, "batches": {},
        })
        self._validate_state()
        self.signature = self._signature()

    def _signature(self):
        try:
            info = os.stat(self.path, follow_symlinks=False)
        except FileNotFoundError:
            return None
        except OSError as error:
            raise StateError("Collections state could not be inspected") from error
        if not stat.S_ISREG(info.st_mode):
            raise StateError("Collections state is not a regular file")
        return info.st_ino, info.st_size, info.st_mtime_ns

    def _require_current(self):
        if self._signature() != self.signature:
            raise StateError("Collections state changed on disk; reload is required")

    def _validate_state(self):
        state = self.state
        if not isinstance(state, dict) or state.get("version") != STATE_VERSION:
            raise StateError("Unsupported collections state version")
        for table in ("collections", "memberships", "plans", "batches"):
            if not isinstance(state.get(table), dict):
                raise StateError("Invalid collections state")
            if any(not isinstance(row, dict) or row.get("id") != key for key, row in state[table].items()):
                raise StateError("Invalid collections record")
        try:
            for collection in state["collections"].values():
                if not valid_collection_target(collection["id"], collection["relative_directory"]):
                    raise StateError("Invalid collection directory")
                normalize_criteria(collection["criteria"])
                normalize_text(collection["name"], required=True, limit=120)
                normalize_text(collection["description"])
            for membership in state["memberships"].values():
                if membership["collection_id"] not in state["collections"] or not isinstance(membership["media"], dict):
                    raise StateError("Invalid collection membership")
                normalize_date_policy(membership.get("date_policy"))
                policies = membership.get("date_policies", [membership.get("date_policy")])
                if not isinstance(policies, list) or not policies:
                    raise StateError("Invalid membership date policies")
                for policy in policies:
                    normalize_date_policy(policy)
                if membership.get("status") not in PROGRESS_STATES:
                    raise StateError("Invalid membership status")
                if "request" in membership and not self.server["normalize_queue_job"](membership["request"]):
                    raise StateError("Invalid membership request")
            for plan in state["plans"].values():
                if not isinstance(plan["items"], list) or not isinstance(plan["expires_at_epoch"], (int, float)):
                    raise StateError("Invalid preview plan")
                normalize_criteria(plan["criteria"])
                if plan.get("batch_id") and plan["batch_id"] not in state["batches"]:
                    raise StateError("Invalid plan commit journal")
            for batch in state["batches"].values():
                if not isinstance(batch["items"], list) or not isinstance(batch["jobs"], list):
                    raise StateError("Invalid batch journal")
                plan = state["plans"].get(batch.get("plan_id"))
                if not plan:
                    raise StateError("Batch approval plan is unavailable")
                if "criteria" in batch and normalize_criteria(batch["criteria"]) != plan["criteria"]:
                    raise StateError("Batch criteria do not match the approved plan")
                for entry in batch["jobs"]:
                    if not self.server["normalize_queue_job"](entry["job"]):
                        raise StateError("Invalid reserved queue job")
        except (KeyError, TypeError, ValueError) as error:
            raise StateError("Invalid collections state") from error

    def _save(self, state):
        self._require_current()
        try:
            atomic_json_write(self.path, state)
        except OSError as error:
            raise StateError("Collections state could not be saved") from error
        self.state = state
        self.signature = self._signature()

    def _normalize_media(self, media):
        return self.server["normalize_history_item"](media)

    def _request_snapshot(self, source):
        request = self.server["normalize_queue_job"]({
            key: source[key] for key in REQUEST_IDENTITY_FIELDS if key in source
        })
        return {key: request[key] for key in REQUEST_IDENTITY_FIELDS} if request else None

    def _member_request(self, state, member):
        if member.get("request"):
            return member["request"]
        # Older memberships only kept media snapshots, which completion may replace.
        # Recover their requested profile and stable identity from the approved plan.
        batch = state["batches"].get(member.get("batch_id"), {})
        plan = state["plans"].get(batch.get("plan_id"), {})
        entry = next((row for row in batch.get("items", []) if row["membership_id"] == member["id"]), {})
        candidate = next((row for row in plan.get("items", []) if row["id"] == entry.get("id")), {})
        reserved = next((
            row["job"] for row in batch.get("jobs", [])
            if row["job"]["id"] == member.get("job_id")
        ), {})
        media = member["media"]
        source = dict(reserved or ({} if plan else media))
        source.update(
            url=candidate.get("url") or entry.get("url") or media.get("url", ""),
            resolution=plan.get("resolution") or media.get("resolution", ""),
            media_id=candidate.get("media_id") or media.get("media_id", ""),
            extractor=candidate.get("extractor") or media.get("extractor", ""),
        )
        return self._request_snapshot(source)

    def _matches_member_request(self, state, member, request):
        previous = self._member_request(state, member)
        if not previous:
            return False
        return self.server["same_queue_request"](previous, request)

    @staticmethod
    def _references_retry(row, context):
        previous_job = context.get("retry_of")
        media_uuids = {
            value for value in (context.get("retry_uuid"), context.get("retry_current_uuid"), previous_job) if value
        }
        return bool(
            (previous_job and row.get("job_id") == previous_job)
            or media_uuids.intersection({row.get("uuid"), (row.get("media") or {}).get("uuid")})
        )

    def _pending_media(self, job, previous):
        return {
            **self._request_snapshot(job),
            "uuid": job["id"], "job_id": job["id"], "status": "queued",
            "title": job.get("title") or previous.get("title", ""),
            "channel": job.get("channel") or previous.get("channel", ""),
            "upload_date": job.get("upload_date") or previous.get("upload_date"),
        }

    def _bind_members_to_job(self, state, member_ids, job, action, retry_context=None):
        for member_id in member_ids:
            member = state["memberships"][member_id]
            member["request"] = self._member_request(state, member) or self._request_snapshot(job)
            member.update(
                job_id=job["id"], status="queued", failure_code="",
                media=self._pending_media(job, member["media"]), updated_at=utc_timestamp(),
            )
        for batch in state["batches"].values():
            for entry in batch["items"]:
                if entry["membership_id"] in member_ids or (retry_context and self._references_retry(entry, retry_context)):
                    entry.update(
                        job_id=job["id"], uuid=None, status="queued", action=action, failure_code="",
                        media=self._pending_media(job, entry.get("media") or {}),
                    )

    def _queue(self):
        jobs = self.server["pending_queue_jobs"]()
        with self.server["queue_state_lock"]:
            active = self.server["normalize_queue_job"](self.server.get("active_queue_job"))
        if active:
            jobs.append(active)
        return {job["id"]: job for job in jobs}

    def _media_view(self, membership, queue):
        media = self._normalize_media(membership.get("media") or {"uuid": membership["job_id"] or membership["id"]})
        status = membership["status"]
        queued = queue.get(membership.get("job_id"))
        if status in {"queued", "running"} and queued:
            status = "queued" if queued["state"] == "queued" else "running"
        if status == "completed" and not media["file_exists"]:
            status = "missing"
        if status == "missing" and media["file_exists"]:
            status = "completed"
        return {
            **media,
            "membership_id": membership["id"],
            "collection_id": membership["collection_id"],
            "batch_id": membership.get("batch_id"),
            "job_id": membership.get("job_id"),
            "status": status,
            "failure_code": membership.get("failure_code") or media.get("failure_code", ""),
        }

    @staticmethod
    def _progress(items):
        progress = {key: 0 for key in PROGRESS_STATES}
        for item in items:
            progress[item["status"] if item["status"] in progress else "failed"] += 1
        return progress

    def _summary(self, state, collection, queue=None):
        queue = self._queue() if queue is None else queue
        items = [
            self._media_view(member, queue)
            for member in state["memberships"].values()
            if member["collection_id"] == collection["id"]
        ]
        files = {item["relative_path"]: item["file_size_bytes"] for item in items if item["file_exists"]}
        return {
            **copy.deepcopy(collection),
            "item_count": len(items),
            "total_size_bytes": sum(files.values()),
            "progress": self._progress(items),
        }

    def _batch_view(self, state, batch, queue=None):
        queue = self._queue() if queue is None else queue
        items = []
        for entry in batch["items"]:
            media = self._normalize_media(
                entry.get("media") or {"uuid": entry.get("uuid") or entry.get("job_id") or entry["id"]}
            )
            status = entry["status"]
            if entry.get("job_id") in queue and status in {"queued", "running"}:
                status = "queued" if queue[entry["job_id"]]["state"] == "queued" else "running"
            if status in {"completed", "missing"}:
                status = "completed" if media["file_exists"] else "missing"
            if entry["action"] == "reused" and status == "completed":
                status = "skipped"
            items.append({
                "id": entry["id"],
                "membership_id": entry["membership_id"],
                "url": entry["url"],
                "title": media.get("title") or entry.get("title") or "",
                "job_id": entry.get("job_id"),
                "uuid": media.get("uuid") if media.get("file_exists") else entry.get("uuid"),
                "relative_path": media.get("relative_path") or "",
                "file_exists": media.get("file_exists", False),
                "file_size_bytes": media.get("file_size_bytes", 0),
                "status": status,
                "action": entry["action"],
                "failure_code": entry.get("failure_code") or media.get("failure_code", ""),
            })
        return {
            "id": batch["id"],
            "plan_id": batch["plan_id"],
            "collection_id": batch["collection_id"],
            "created_at": batch["created_at"],
            "criteria": copy.deepcopy(batch.get("criteria", state["plans"][batch["plan_id"]]["criteria"])),
            "progress": self._progress(items),
            "items": items,
        }

    @nonblocking_io
    def list_collections(self):
        self.reconcile()
        with self.lock:
            queue = self._queue()
            return [
                self._summary(self.state, row, queue)
                for row in sorted(self.state["collections"].values(), key=lambda row: row["created_at"], reverse=True)
            ]

    @nonblocking_io
    def get_collection(self, collection_id):
        self.reconcile()
        with self.lock:
            collection = self.state["collections"].get(collection_id)
            if not collection:
                raise APIError("collection_not_found", 404)
            queue = self._queue()
            return {
                "collection": self._summary(self.state, collection, queue),
                "items": [
                    self._media_view(member, queue)
                    for member in self.state["memberships"].values()
                    if member["collection_id"] == collection_id
                ],
                "batches": [
                    self._batch_view(self.state, batch, queue)
                    for batch in self.state["batches"].values()
                    if batch["collection_id"] == collection_id
                ],
            }

    @nonblocking_io
    def update_collection(self, collection_id, payload):
        reject_client_paths(payload)
        if not payload or set(payload) - {"name", "description"}:
            raise APIError("immutable_collection_fields")
        with self.lock:
            state = copy.deepcopy(self.state)
            collection = state["collections"].get(collection_id)
            if not collection:
                raise APIError("collection_not_found", 404)
            for key in payload:
                collection[key] = normalize_text(payload[key], required=key == "name", limit=120 if key == "name" else 2000)
            collection["updated_at"] = utc_timestamp()
            self._save(state)
            return self._summary(state, collection)

    @nonblocking_io
    def delete_collection(self, collection_id):
        with self.server["queue_operation_lock"], self.lock:
            state = copy.deepcopy(self.state)
            if collection_id not in state["collections"]:
                raise APIError("collection_not_found", 404)
            del state["collections"][collection_id]
            state["memberships"] = {
                key: member for key, member in state["memberships"].items()
                if member["collection_id"] != collection_id
            }
            self._save(state)

    def _candidate(self, candidate, resolution, criteria, item_id):
        url = candidate.get("url")
        item = {
            "id": item_id, "url": url.strip() if isinstance(url, str) else "",
            "title": "", "upload_date": None, "status": "invalid",
        }
        error = self.server["validate_download_request"](url, resolution)
        if error:
            item["reason"] = self.server["get_error_details"](error)[0] or "invalid_url"
            return item
        if self.server["classify_playlist_url"](url) != "single":
            item["reason"] = "direct_urls_only"
            return item
        try:
            if self.server["validate_source_redirects"](url):
                item["reason"] = "source_blocked"
                return item
            metadata = self.server["fetch_media_metadata"](url, direct=True)
        except (OSError, ValueError, TimeoutError, self.server["subprocess"].SubprocessError):
            item["reason"] = "metadata_unavailable"
            return item
        if not is_direct_metadata(metadata):
            item["reason"] = "direct_urls_only" if metadata else "metadata_unavailable"
            return item
        media_id, extractor = self.server["get_media_identity"](metadata)
        item.update({
            "title": self.server["get_media_display_title"](metadata, url),
            "channel": str(metadata.get("uploader") or metadata.get("channel") or ""),
            "upload_date": metadata_upload_date(metadata),
            "media_id": media_id,
            "extractor": extractor,
            "thumbnail": str(metadata.get("thumbnail") or ""),
        })
        status = date_status(metadata, criteria)
        if status:
            item["status"] = status
            return item
        job = self.server["create_queue_job"](url, resolution, "collection")
        job.update(media_id=media_id, extractor=extractor)
        queued = self.server["find_queued_duplicate"](job)
        existing = self.server["find_existing_download"](url, resolution, media_id=media_id, extractor=extractor)
        if existing:
            item.update(status="already_downloaded", uuid=existing["uuid"], relative_path=existing["relative_path"])
        elif queued:
            item.update(status="already_queued", job_id=queued["id"])
        else:
            item["status"] = "new"
        return item

    @nonblocking_io
    def preview(self, payload, deadline=None):
        deadline = time.monotonic() + PREVIEW_WORK_TIMEOUT_SECONDS if deadline is None else deadline
        if time.monotonic() >= deadline:
            raise APIError("preview_timeout", 504)
        reject_client_paths(payload)
        if set(payload) - {"name", "description", "criteria", "resolution", "candidates"}:
            raise APIError("invalid_plan")
        name = normalize_text(payload.get("name", ""), required=True, limit=120)
        description = normalize_text(payload.get("description", ""))
        criteria = normalize_criteria(payload.get("criteria"))
        resolution = payload.get("resolution", "best")
        if self.server["validate_download_request"]("https://example.com/", resolution, resolve_source=False):
            raise APIError("unsupported_resolution")
        candidates = payload.get("candidates")
        if not isinstance(candidates, list) or not candidates:
            raise APIError("candidates_required")
        if len(candidates) > batch_limit():
            raise APIError("batch_limit_exceeded")
        if any(not isinstance(candidate, dict) for candidate in candidates):
            raise APIError("invalid_candidate")
        plan_id = str(uuid.uuid4())
        candidate_ids = [str(uuid.uuid5(uuid.UUID(plan_id), str(index))) for index in range(len(candidates))]
        def inspect_candidate(candidate, item_id):
            if time.monotonic() >= deadline:
                raise APIError("preview_timeout", 504)
            return self._candidate(candidate, resolution, criteria, item_id)

        executor = ThreadPoolExecutor(max_workers=min(4, len(candidates)))
        try:
            futures = [
                executor.submit(inspect_candidate, candidate, item_id)
                for candidate, item_id in zip(candidates, candidate_ids)
            ]
            items = []
            for future in futures:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise APIError("preview_timeout", 504)
                items.append(future.result(timeout=remaining))
        except FutureTimeoutError:
            raise APIError("preview_timeout", 504) from None
        finally:
            executor.shutdown(wait=False, cancel_futures=True)
        seen = set()
        for item in items:
            identity = (item.get("extractor", "").casefold(), item["media_id"]) if item.get("media_id") else self.server["normalize_media_url"](item["url"])
            if identity and identity in seen:
                item.update(status="invalid", reason="duplicate_candidate")
            seen.add(identity)
        now = time.time()
        plan = {
            "id": plan_id, "name": name, "description": description, "criteria": criteria,
            "resolution": resolution, "items": items, "created_at": utc_timestamp(now),
            "expires_at": utc_timestamp(now + PLAN_TTL_SECONDS),
            "expires_at_epoch": now + PLAN_TTL_SECONDS,
            "batch_id": None,
        }
        with self.lock:
            if time.monotonic() >= deadline:
                raise APIError("preview_timeout", 504)
            state = copy.deepcopy(self.state)
            state["plans"][plan_id] = plan
            self._save(state)
            return self._plan_view(plan)

    def _plan_view(self, plan):
        matching = [
            self._summary(self.state, collection)
            for collection in self.state["collections"].values()
            if match_text(collection["name"]) == match_text(plan["name"])
            or (match_text(plan["description"]) and match_text(collection["description"]) == match_text(plan["description"]))
        ]
        return {
            key: copy.deepcopy(value) for key, value in plan.items()
            if key not in {"expires_at_epoch", "commit_receipt"}
        } | {
            "matching_collections": matching,
            "expired": time.time() >= plan["expires_at_epoch"],
            "committed": bool(plan.get("batch_id")),
        }

    @nonblocking_io
    def get_plan(self, plan_id):
        with self.lock:
            self._require_current()
            plan = self.state["plans"].get(plan_id)
            if not plan:
                raise APIError("plan_not_found", 404)
            return self._plan_view(plan)

    def _selected_items(self, plan, payload):
        selected = payload.get("selected_item_ids")
        unknown = payload.get("include_unknown_dates", [])
        if not isinstance(selected, list) or not selected or any(not isinstance(value, str) for value in selected):
            raise APIError("selection_required")
        if not isinstance(unknown, list) or any(not isinstance(value, str) for value in unknown):
            raise APIError("invalid_unknown_date_selection")
        if len(set(selected)) != len(selected) or not set(unknown) <= set(selected):
            raise APIError("invalid_selection")
        by_id = {item["id"]: item for item in plan["items"]}
        if not set(selected) <= set(by_id):
            raise APIError("invalid_selection")
        items = [by_id[item_id] for item_id in selected]
        for item in items:
            if item["status"] in {"invalid", "outside_date_range"}:
                raise APIError("ineligible_plan_item")
            if item["status"] == "date_unknown" and item["id"] not in unknown:
                raise APIError("unknown_date_approval_required")
        return items, set(unknown)

    @nonblocking_io
    def commit(self, plan_id, payload):
        reject_client_paths(payload)
        if set(payload) - {"collection_id", "create_collection", "selected_item_ids", "include_unknown_dates"}:
            raise APIError("invalid_commit")
        with self.lock:
            self._require_current()
            preview = self.state["plans"].get(plan_id)
            if not preview:
                raise APIError("plan_not_found", 404)
            committed = bool(preview.get("batch_id"))
            if not committed:
                if time.time() >= preview["expires_at_epoch"]:
                    raise APIError("plan_expired", 410)
                self._selected_items(preview, payload)
        library = self.server["download_manager"].combined_history() if not committed else []
        with self.server["queue_operation_lock"], self.lock:
            self._require_current()
            plan = self.state["plans"].get(plan_id)
            if not plan:
                raise APIError("plan_not_found", 404)
            if plan.get("batch_id"):
                self._reconcile_locked()
                self.server["start_download_thread_if_needed"]()
                receipt = copy.deepcopy(self.state["plans"][plan_id]["commit_receipt"])
                receipt["batch"].setdefault("criteria", copy.deepcopy(plan["criteria"]))
                return receipt
            if time.time() >= plan["expires_at_epoch"]:
                raise APIError("plan_expired", 410)
            items, unknown = self._selected_items(plan, payload)
            collection_id = payload.get("collection_id")
            if collection_id is not None and not isinstance(collection_id, str):
                raise APIError("invalid_commit")
            if "create_collection" in payload and not isinstance(payload["create_collection"], bool):
                raise APIError("invalid_commit")
            create = payload.get("create_collection") is True
            if bool(collection_id) == create:
                raise APIError("collection_selection_required")
            if collection_id and collection_id not in self.state["collections"]:
                raise APIError("collection_not_found", 404)
            # Approval uses the server-fetched preview; network/date revalidation
            # happens at preflight and in yt-dlp, outside state locks.
            for item in items:
                status = date_status(item, plan["criteria"])
                if status == "outside_date_range":
                    raise APIError("ineligible_plan_item")
                if status == "date_unknown" and item["id"] not in unknown:
                    raise APIError("unknown_date_approval_required")
            state = copy.deepcopy(self.state)
            now = utc_timestamp()
            if create:
                collection_id = str(uuid.uuid4())
                slug = unicodedata.normalize("NFKD", plan["name"]).encode("ascii", "ignore").decode("ascii").lower()
                slug = re.sub(r"[^a-z0-9]+", "-", slug).strip("-")[:60].rstrip("-") or "collection"
                collection = {
                    "id": collection_id, "name": plan["name"], "description": plan["description"],
                    "criteria": copy.deepcopy(plan["criteria"]),
                    "relative_directory": f"collections/{slug}--{uuid.UUID(collection_id).hex[:12]}",
                    "created_at": now, "updated_at": now,
                }
                state["collections"][collection_id] = collection
            collection = state["collections"][collection_id]
            collection["updated_at"] = now
            if safe_media_path(self.server["DOWNFOLDER_DIR"], collection["relative_directory"]) is None:
                raise APIError("unsafe_path")
            batch = {
                "id": str(uuid.uuid4()), "plan_id": plan_id, "collection_id": collection_id,
                "created_at": now, "criteria": copy.deepcopy(plan["criteria"]),
                "items": [], "jobs": [], "dispatch_complete": False,
            }
            new_jobs = {}
            for item in items:
                policy = {**plan["criteria"], "include_unknown_date": item["id"] in unknown}
                existing = self.server["find_existing_download"](
                    item["url"], plan["resolution"], media_id=item["media_id"], extractor=item["extractor"],
                    items=library,
                )
                prototype = self.server["create_queue_job"](item["url"], plan["resolution"], "collection")
                prototype.update(media_id=item["media_id"], extractor=item["extractor"])
                duplicate = self.server["find_queued_duplicate"](prototype)
                identity = (item["extractor"].casefold(), item["media_id"]) if item["media_id"] else prototype["normalized_url"]
                duplicate = duplicate or new_jobs.get(identity)
                if existing:
                    action, job_id = "reused", None
                    media = self._normalize_media({
                        **existing, "url": item["url"], "upload_date": item["upload_date"],
                        "media_id": item["media_id"], "extractor": item["extractor"],
                    })
                    member_status = "completed"
                else:
                    action, job_id = ("existing_queue", duplicate["id"]) if duplicate else ("queued", prototype["id"])
                    media = {
                        "uuid": job_id, "url": item["url"], "title": item["title"],
                        "resolution": plan["resolution"], "upload_date": item["upload_date"],
                        "channel": item["channel"], "media_id": item["media_id"], "extractor": item["extractor"],
                    }
                    member_status = "queued"
                    if not duplicate:
                        job = self.server["normalize_queue_job"]({
                            **prototype,
                            **{key: item[key] for key in ("title", "channel", "media_id", "extractor", "upload_date", "thumbnail")},
                            "collection_id": collection_id, "batch_id": batch["id"],
                            "target_relative_directory": collection["relative_directory"], "date_policy": policy,
                        })
                        if not job:
                            raise StateError("Collection queue job could not be reserved")
                        batch["jobs"].append({"job": job, "status": "reserved"})
                        new_jobs[identity] = job
                member = next((
                    row for row in state["memberships"].values()
                    if row["collection_id"] == collection_id and self._matches_member_request(state, row, prototype)
                ), None)
                if member is None:
                    member = {
                        "id": str(uuid.uuid4()), "collection_id": collection_id, "batch_id": batch["id"],
                        "job_id": job_id, "media": media, "status": member_status,
                        "request": self._request_snapshot(prototype),
                        "date_policy": policy, "date_policies": [policy], "created_at": now, "updated_at": now,
                    }
                    state["memberships"][member["id"]] = member
                else:
                    if policy not in member.setdefault("date_policies", [member["date_policy"]]):
                        member["date_policies"].append(policy)
                    if job_id:
                        self._bind_members_to_job(state, {member["id"]}, {**prototype, "id": job_id}, action)
                    else:
                        member.update(job_id=None, media=media, status="completed", failure_code="")
                        for previous_batch in state["batches"].values():
                            for entry in previous_batch["items"]:
                                if entry["membership_id"] == member["id"]:
                                    entry.update(job_id=None, uuid=media["uuid"], media=media, status="completed", action="reused")
                        self._apply_history(state, [media])
                    member.update(
                        request=self._request_snapshot(prototype), batch_id=batch["id"],
                        date_policy=policy, updated_at=now,
                    )
                batch["items"].append({
                    "id": item["id"], "membership_id": member["id"], "job_id": job_id,
                    "uuid": media.get("uuid") if existing else None, "url": item["url"],
                    "title": item["title"], "status": member_status, "action": action,
                    "media": media, "date_policy": policy,
                })
            if batch["jobs"] and self.server["get_storage_status"]()["blocking"]:
                raise APIError("storage_critical", 507)
            if time.time() >= plan["expires_at_epoch"]:
                raise APIError("plan_expired", 410)
            state["batches"][batch["id"]] = batch
            state["plans"][plan_id]["batch_id"] = batch["id"]
            state["plans"][plan_id]["committed_at"] = now
            receipt = {
                "batch": self._batch_view(state, batch),
                "collection": self._summary(state, collection),
            }
            state["plans"][plan_id]["commit_receipt"] = copy.deepcopy(receipt)
            # This is the commit point: all IDs and the approval are durable before queue dispatch.
            self._save(state)
            self._reconcile_locked()
        self.server["start_download_thread_if_needed"]()
        self.server["download_manager"].broadcast_to_all_clients("[QUEUE_UPDATED], {}")
        return receipt

    def _apply_history(self, state, history):
        changed = False
        for media in history:
            job_id = media.get("job_id") or media.get("uuid")
            if media.get("status") not in {"completed", "missing", "file_only", "failed", "error", "canceled", "skipped"}:
                continue
            status = "completed" if media["status"] in {"completed", "missing", "file_only"} else ("skipped" if media["status"] == "skipped" else "failed")
            for member in state["memberships"].values():
                if member.get("job_id") != job_id and member["media"].get("uuid") != media.get("uuid"):
                    continue
                member_media = dict(media)
                if member.get("job_id") != job_id and not metadata_upload_date(member_media):
                    member_media["upload_date"] = member["media"].get("upload_date")
                rejections = [
                    policy_rejection(member_media, policy)
                    for policy in member.get("date_policies", [member.get("date_policy")])
                ] if status == "completed" else []
                reason = next(iter(rejections), None) if rejections and all(rejections) else None
                final_status = "skipped" if reason else status
                updated_media = copy.deepcopy(member_media) if not reason else {
                    "uuid": job_id, "url": media.get("url", ""), "title": media.get("title", ""),
                    "resolution": media.get("resolution", ""), "upload_date": media.get("upload_date"),
                }
                if member["media"] != updated_media or member["status"] != final_status:
                    member.update(media=updated_media, status=final_status, updated_at=utc_timestamp(),
                                  failure_code=reason or media.get("failure_code", ""))
                    changed = True
            for batch in state["batches"].values():
                for entry in batch["items"]:
                    if entry.get("job_id") != job_id and (entry.get("media") or {}).get("uuid") != media.get("uuid"):
                        continue
                    entry_media = dict(media)
                    if entry.get("job_id") != job_id and not metadata_upload_date(entry_media):
                        entry_media["upload_date"] = (entry.get("media") or {}).get("upload_date")
                    reason = policy_rejection(entry_media, entry.get("date_policy")) if status == "completed" else None
                    updates = {
                        "status": "skipped" if reason else status,
                        "media": copy.deepcopy(entry_media) if not reason else {},
                        "uuid": None if reason else media.get("uuid"),
                        "failure_code": reason or media.get("failure_code", ""),
                    }
                    if any(entry.get(key) != value for key, value in updates.items()):
                        entry.update(updates)
                        changed = True
                for reserved in batch["jobs"]:
                    if reserved["job"]["id"] == job_id and reserved["status"] != status:
                        reserved["status"] = status
                        changed = True
        return changed

    @nonblocking_io
    def observe_history(self, history):
        with self.server["queue_operation_lock"], self.lock:
            self._require_current()
            state = copy.deepcopy(self.state)
            if self._apply_history(state, [self._normalize_media(item) for item in history]):
                self._save(state)

    @nonblocking_io
    def record_job_end(self, job, status, failure_code="", existing=None):
        media = dict(existing or {
            "uuid": job["id"], "url": job["url"], "resolution": job["resolution"],
            "title": job.get("title", ""), "collection_id": job.get("collection_id"),
            "batch_id": job.get("batch_id"), "date_policy": job.get("date_policy"),
        })
        media.update(job_id=job["id"], status=status, failure_code=failure_code)
        with self.server["queue_operation_lock"], self.lock:
            self._require_current()
            state = copy.deepcopy(self.state)
            changed = self._apply_history(state, [self._normalize_media(media)])
            if existing:
                for batch in state["batches"].values():
                    for entry in batch["items"]:
                        if entry.get("job_id") == job["id"] and entry["action"] != "reused":
                            entry["action"] = "reused"
                            changed = True
            if changed:
                self._save(state)

    @nonblocking_io
    def job_is_terminal(self, job_id):
        with self.lock:
            self._require_current()
            return any(
                reserved["job"]["id"] == job_id and reserved["status"] in TERMINAL_STATES
                for batch in self.state["batches"].values() for reserved in batch["jobs"]
            )

    def _reconcile_locked(self):
        self._require_current()
        state = copy.deepcopy(self.state)
        history = self.server["download_manager"].normalized_history()
        changed = self._apply_history(state, history)
        queue = self._queue()
        jobs = []
        terminal_job_ids = set()
        for batch in state["batches"].values():
            for reserved in batch["jobs"]:
                job = reserved["job"]
                if reserved["status"] in TERMINAL_STATES:
                    terminal_job_ids.add(job["id"])
                    continue
                if job["id"] not in queue:
                    jobs.append(job)
                    queue[job["id"]] = job
                if reserved["status"] != "queued":
                    reserved["status"] = "queued"
                    changed = True
            if not batch["dispatch_complete"]:
                batch["dispatch_complete"] = True
                changed = True
        # The queue writer persists the whole snapshot before exposing jobs to the worker.
        if jobs or terminal_job_ids.intersection(queue):
            self.server["apply_collection_queue_journal"](jobs, terminal_job_ids)
        if changed:
            self._save(state)

    @nonblocking_io
    def reconcile(self):
        with self.server["queue_operation_lock"], self.lock:
            self._reconcile_locked()

    @nonblocking_io
    def get_batch(self, batch_id):
        self.reconcile()
        with self.lock:
            batch = self.state["batches"].get(batch_id)
            if not batch:
                raise APIError("batch_not_found", 404)
            return self._batch_view(self.state, batch)

    @nonblocking_io
    def media_snapshots(self):
        with self.lock:
            self._require_current()
            return [copy.deepcopy(member["media"]) for member in self.state["memberships"].values() if member["media"]]

    @nonblocking_io
    def retry_context(self, item):
        with self.lock:
            self._require_current()
            references = {"retry_of": item.get("job_id"), "retry_uuid": item.get("uuid")}
            member = next((
                row for row in self.state["memberships"].values()
                if self._references_retry(row, references)
            ), None)
            if not member:
                previous_request = self._request_snapshot(item)
                member = next((
                    row for row in self.state["memberships"].values()
                    if previous_request and self._matches_member_request(self.state, row, previous_request)
                ), None)
            if not member:
                return None
            collection = self.state["collections"].get(member["collection_id"])
            if not collection:
                return None
            return {
                "collection_id": collection["id"], "batch_id": member["batch_id"],
                "target_relative_directory": collection["relative_directory"],
                "date_policy": member.get("date_policy"),
                "retry_of": member.get("job_id") or item["uuid"],
                "retry_uuid": item["uuid"],
                "retry_current_uuid": member["media"].get("uuid"),
                "request": copy.deepcopy(self._member_request(self.state, member)),
            }

    @nonblocking_io
    def reserve_retry(self, job, context):
        with self.lock:
            state = copy.deepcopy(self.state)
            batch = state["batches"].get(job["batch_id"])
            if not batch:
                raise StateError("Retry batch is unavailable")
            batch["jobs"].append({"job": job, "status": "reserved"})
            members = {row["id"] for row in state["memberships"].values() if self._references_retry(row, context)}
            self._bind_members_to_job(state, members, job, "queued", context)
            self._save(state)

    @nonblocking_io
    def bind_retry_to_job(self, context, job_id):
        with self.lock:
            state = copy.deepcopy(self.state)
            job = self._queue().get(job_id)
            if not job:
                raise StateError("Retry queue job is unavailable")
            if not any(
                reserved["job"]["id"] == job_id
                for batch in state["batches"].values() for reserved in batch["jobs"]
            ):
                batch = state["batches"].get(context["batch_id"])
                if not batch:
                    raise StateError("Retry batch is unavailable")
                batch["jobs"].append({"job": job, "status": "queued"})
            members = {row["id"] for row in state["memberships"].values() if self._references_retry(row, context)}
            self._bind_members_to_job(state, members, job, "existing_queue", context)
            self._save(state)
