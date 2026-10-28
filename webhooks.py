"""Download notifications sent to webhooks the administrator configured.

``YDLNAS_WEBHOOK_URL`` holds one or more URLs separated by commas, spaces or new
lines (``YDLNAS_WEBHOOK_URL_FILE`` may point to a file holding them instead). Each
URL may start with a format prefix such as ``ntfy+https://ntfy.home.lan/nas``.
Without one, the host decides: Discord and Slack webhooks, ntfy.sh and the Telegram
Bot API get their own payloads, and every other URL receives a JSON document whose
``text`` field also suits Slack-compatible chat servers.

``YDLNAS_WEBHOOK_EVENTS`` lists which outcomes notify: ``completed``, ``failed``,
``canceled`` and ``skipped``. The default is ``completed,failed``.

Delivery runs on one background thread so a slow or offline webhook never delays
the download worker. Webhook URLs often embed tokens, so logs name only the host.
"""

import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from queue import Full, Queue
from threading import Lock, Thread
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, build_opener


FORMATS = ("json", "discord", "slack", "ntfy", "telegram")
EVENTS = ("completed", "failed", "canceled", "skipped")
DEFAULT_EVENTS = ("completed", "failed")
EVENT_BY_STATUS = {
    "completed": "completed",
    "failed": "failed",
    "error": "failed",
    "canceled": "canceled",
    "skipped": "skipped",
}
TITLES = {
    "completed": "Downloaded",
    "failed": "Download failed",
    "canceled": "Download canceled",
    "skipped": "Download skipped",
    "test": "Test notification",
}
NTFY_TAGS = {
    "completed": "white_check_mark", "failed": "x", "canceled": "stop_sign", "skipped": "fast_forward", "test": "bell",
}
SEPARATORS = re.compile(r"[\s,]+")
BROADCAST_MENTION = re.compile(r"@(?=(?:channel|here|all|everyone)\b)", re.IGNORECASE)
MAX_ITEMS = 20
MAX_TEXT = 1800
QUEUE_SIZE = 100
REQUEST_TIMEOUT_SECONDS = 10
RETRY_DELAYS_SECONDS = (2, 10)


class WebhookConfigError(ValueError):
    """A configured webhook cannot be used; the message never contains the URL."""


def log(message):
    print(f"[webhook] {message}", file=sys.stderr, flush=True)


def describe(url):
    """Name a target for logs without its path or query, which often hold tokens."""
    try:
        parts = urlsplit(url)
        return parts.hostname or "invalid host"
    except ValueError:
        return "invalid host"


def detect_format(url):
    host = (urlsplit(url).hostname or "").casefold()
    path = urlsplit(url).path
    if host in {"discord.com", "discordapp.com", "ptb.discord.com", "canary.discord.com"} and path.startswith("/api/webhooks/"):
        return "discord"
    if host == "hooks.slack.com":
        return "slack"
    if host == "ntfy.sh":
        return "ntfy"
    if host == "api.telegram.org":
        return "telegram"
    return "json"


def parse_target(value):
    value = value.strip()
    kind = None
    prefix, separator, rest = value.partition("+")
    if separator and prefix.casefold() in FORMATS and rest.lower().startswith(("http://", "https://")):
        kind, value = prefix.casefold(), rest
    try:
        parts = urlsplit(value)
    except ValueError:
        raise WebhookConfigError("a webhook URL could not be parsed") from None
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise WebhookConfigError("a webhook URL must start with http:// or https:// and name a host")
    kind = kind or detect_format(value)
    target = {"url": value, "format": kind, "host": parts.hostname}
    if kind == "telegram":
        chat_ids = parse_qs(parts.query).get("chat_id")
        if not chat_ids or not chat_ids[0].strip():
            raise WebhookConfigError(f"the Telegram webhook for {parts.hostname} needs ?chat_id= in its URL")
        target["chat_id"] = chat_ids[0].strip()
    return target


def parse_events(value):
    if value is None or not value.strip():
        return set(DEFAULT_EVENTS)
    requested = {item.casefold() for item in SEPARATORS.split(value.strip()) if item}
    unknown = sorted(requested - set(EVENTS))
    if unknown:
        raise WebhookConfigError("YDLNAS_WEBHOOK_EVENTS accepts " + ", ".join(EVENTS) + "; unknown " + ", ".join(unknown))
    return requested


def read_urls(env):
    value = env.get("YDLNAS_WEBHOOK_URL", "")
    if not value.strip() and env.get("YDLNAS_WEBHOOK_URL_FILE"):
        try:
            with open(env["YDLNAS_WEBHOOK_URL_FILE"], encoding="utf-8") as handle:
                value = handle.read()
        except (OSError, UnicodeError):
            raise WebhookConfigError("YDLNAS_WEBHOOK_URL_FILE points to a missing or unreadable file") from None
    return [item for item in SEPARATORS.split(value.strip()) if item]


def format_size(size):
    try:
        size = float(size)
    except (TypeError, ValueError):
        return ""
    if size <= 0:
        return ""
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return ""


def item_label(item):
    return str(item.get("title") or item.get("filename") or item.get("url") or "Untitled").strip()


def public_item(item):
    return {
        "uuid": item.get("uuid") or "",
        "status": item.get("status") or "",
        "failure_code": item.get("failure_code") or "",
        "title": item.get("title") or "",
        "channel": item.get("channel") or "",
        "url": item.get("url") or "",
        "resolution": item.get("resolution") or "",
        "download_type": item.get("download_type") or "",
        "relative_path": item.get("relative_path") or "",
        "filename": item.get("filename") or "",
        "file_size_bytes": item.get("file_size_bytes") or 0,
        "duration_seconds": item.get("duration_seconds") or 0,
        "collection_id": item.get("collection_id") or None,
        "timestamp": item.get("timestamp") or "",
    }


def quiet_mentions(text):
    """Keep an untrusted title such as "@everyone" from pinging a whole chat channel."""
    return BROADCAST_MENTION.sub("@\u2060", text)


def slack_escape(text):
    """Slack treats <...> as links and mentions such as <!channel>; send them as text."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def summary_text(event, items):
    heading = TITLES[event]
    if len(items) == 1:
        item = items[0]
        details = [part for part in (
            item.get("channel"),
            format_size(item.get("file_size_bytes")) if event == "completed" else "",
            item.get("failure_code") if event != "completed" else "",
        ) if part]
        text = f"{heading}: {item_label(item)}"
        if details:
            text += " (" + ", ".join(str(part) for part in details) + ")"
        return quiet_mentions(text)[:MAX_TEXT]
    shown = [item_label(item) for item in items[:5]]
    text = f"{heading}: {len(items)} items. " + "; ".join(shown)
    if len(items) > len(shown):
        text += f"; and {len(items) - len(shown)} more"
    return quiet_mentions(text)[:MAX_TEXT]


def build_request(target, notification):
    event = notification["event"].removeprefix("download.")
    text = notification["text"]
    headers = {"User-Agent": f"youtube-dl-nas/{notification['version']}"}
    kind = target["format"]
    if kind == "ntfy":
        body = text.encode("utf-8")
        headers.update({
            "Content-Type": "text/plain; charset=utf-8",
            "Title": f"youtube-dl-nas: {TITLES[event].lower()}",
            "Tags": NTFY_TAGS[event],
        })
    else:
        if kind == "discord":
            payload = {"content": text[:2000], "allowed_mentions": {"parse": []}}
        elif kind == "slack":
            payload = {"text": slack_escape(text)}
        elif kind == "telegram":
            payload = {"chat_id": target["chat_id"], "text": text, "disable_web_page_preview": True}
        else:
            payload = notification
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
    return Request(target["url"], data=body, headers=headers, method="POST")


def default_send(request, timeout):
    with build_opener().open(request, timeout=timeout) as response:
        response.read(4096)
        return response.status


class WebhookNotifier:
    def __init__(self, targets=(), events=DEFAULT_EVENTS, app_version="", send=default_send,
                 retry_delays=RETRY_DELAYS_SECONDS, sleep=time.sleep, queue_size=QUEUE_SIZE):
        self.targets = list(targets)
        self.events = set(events)
        self.app_version = app_version
        self.send = send
        self.retry_delays = tuple(retry_delays)
        self.sleep = sleep
        self.pending = Queue(maxsize=queue_size)
        self.thread = None
        self.thread_lock = Lock()

    @classmethod
    def from_environment(cls, env=None, app_version="", **options):
        env = os.environ if env is None else env
        try:
            urls = read_urls(env)
            events = parse_events(env.get("YDLNAS_WEBHOOK_EVENTS"))
        except WebhookConfigError as error:
            log(f"disabled: {error}")
            return cls(app_version=app_version, **options)
        targets = []
        for url in urls:
            try:
                targets.append(parse_target(url))
            except WebhookConfigError as error:
                log(f"skipped one target: {error}")
        if targets:
            hosts = ", ".join(f"{target['host']} ({target['format']})" for target in targets)
            log(f"{len(targets)} target(s) for {', '.join(sorted(events))}: {hosts}")
        return cls(targets, events, app_version, **options)

    @property
    def enabled(self):
        return bool(self.targets and self.events)

    def notifications(self, history_items):
        grouped = {}
        for item in history_items or ():
            event = EVENT_BY_STATUS.get(str((item or {}).get("status") or ""))
            if event in self.events:
                grouped.setdefault(event, []).append(item)
        sent_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        for event in EVENTS:
            items = grouped.get(event)
            if not items:
                continue
            yield {
                "event": f"download.{event}",
                "text": summary_text(event, items),
                "count": len(items),
                "items": [public_item(item) for item in items[:MAX_ITEMS]],
                "app": "youtube-dl-nas",
                "version": self.app_version,
                "sent_at": sent_at,
            }

    def notify(self, history_items):
        """Queue notifications for finished history rows; never blocks or raises."""
        if not self.enabled:
            return 0
        queued = 0
        try:
            for notification in self.notifications(history_items):
                try:
                    self.pending.put_nowait(notification)
                    queued += 1
                except Full:
                    log("queue full; dropped one notification")
            if queued:
                self._ensure_thread()
        except Exception as error:  # A notification problem must never fail a download.
            log(f"could not queue a notification: {type(error).__name__}")
        return queued

    def _ensure_thread(self):
        with self.thread_lock:
            if self.thread and self.thread.is_alive():
                return
            self.thread = Thread(target=self._run, name="webhook-notifier", daemon=True)
            self.thread.start()

    def _run(self):
        while True:
            notification = self.pending.get()
            try:
                for target in self.targets:
                    self.deliver(target, notification)
            finally:
                self.pending.task_done()

    def deliver(self, target, notification):
        """Send one notification to one target, retrying network and server errors."""
        attempts = len(self.retry_delays) + 1
        for attempt in range(attempts):
            try:
                status = self.send(build_request(target, notification), REQUEST_TIMEOUT_SECONDS)
                return status
            except HTTPError as error:
                retryable = error.code == 429 or error.code >= 500
                reason = f"HTTP {error.code}"
            except (URLError, OSError, TimeoutError) as error:
                retryable = True
                reason = type(error).__name__
            except Exception as error:
                retryable = False
                reason = type(error).__name__
            if not retryable or attempt == attempts - 1:
                log(f"{target['host']}: {notification['event']} not delivered ({reason})")
                return None
            self.sleep(self.retry_delays[attempt])
        return None

    def send_test(self):
        """Deliver one sample notification synchronously to every target."""
        notification = {
            "event": "download.test",
            "text": "youtube-dl-nas test notification: webhooks are configured.",
            "count": 0,
            "items": [],
            "app": "youtube-dl-nas",
            "version": self.app_version,
            "sent_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        return [(target, self.deliver(target, notification)) for target in self.targets]


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv != ["--test"]:
        print("Usage: python webhooks.py --test", file=sys.stderr)
        return 2
    notifier = WebhookNotifier.from_environment(app_version=os.environ.get("APP_VERSION", ""))
    if not notifier.targets:
        print("No usable webhook is configured in YDLNAS_WEBHOOK_URL or YDLNAS_WEBHOOK_URL_FILE.")
        return 1
    failed = 0
    for target, status in notifier.send_test():
        outcome = f"HTTP {status}" if status else "not delivered"
        print(f"{target['host']} ({target['format']}): {outcome}")
        failed += status is None
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
