"""Download notifications sent to webhooks the administrator configured.

``YDLNAS_WEBHOOK_URL`` holds one or more URLs separated by commas, spaces or new
lines (``YDLNAS_WEBHOOK_URL_FILE`` may point to a file holding them instead). Each
URL may start with a format prefix such as ``ntfy+https://ntfy.home.lan/nas``.
Without one, the host decides: Discord and Slack webhooks, ntfy.sh and the Telegram
Bot API get their own payloads, and every other URL receives a JSON document whose
``text`` field also suits Slack-compatible chat servers.

``YDLNAS_WEBHOOK_EVENTS`` lists which outcomes notify: ``completed``, ``failed``,
``canceled`` and ``skipped``. The default is ``completed,failed``.

Each target has its own background thread and queue, so a slow or offline webhook
never delays the download worker or the other targets. Webhook URLs often embed
tokens, so logs name only the host.
"""

import base64
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from queue import Full, Queue
from threading import Lock, Thread
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, unquote, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


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
DISCORD_HOSTS = {"discord.com", "discordapp.com", "ptb.discord.com", "canary.discord.com"}
DISCORD_WEBHOOK_PATH = re.compile(r"^/api(?:/v\d+)?/webhooks/")
SEPARATORS = re.compile(r"[\s,]+")
BROADCAST_MENTION = re.compile(r"@(?=(?:channel|here|all|everyone)\b)", re.IGNORECASE)
MAX_ITEMS = 20
MAX_TITLES_IN_TEXT = 5
MAX_TEXT = 1800
QUEUE_SIZE = 100
REQUEST_TIMEOUT_SECONDS = 10
RETRY_DELAYS_SECONDS = (2, 10)
MAX_RETRY_AFTER_SECONDS = 60


class WebhookConfigError(ValueError):
    """A configured webhook cannot be used; the message never contains the URL."""


class RefuseRedirects(HTTPRedirectHandler):
    """urllib would turn a redirected POST into a body-less GET and report success."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def log(message):
    print(f"[webhook] {message}", file=sys.stderr, flush=True)


def detect_format(parts):
    host = (parts.hostname or "").casefold()
    if host in DISCORD_HOSTS and DISCORD_WEBHOOK_PATH.match(parts.path):
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
        hostname, port = parts.hostname, parts.port
    except ValueError:
        raise WebhookConfigError("a webhook URL could not be parsed") from None
    if parts.scheme not in {"http", "https"} or not hostname:
        raise WebhookConfigError("a webhook URL must start with http:// or https:// and name a host")
    target = {"url": value, "format": kind or detect_format(parts), "host": hostname}
    if parts.username is not None or parts.password is not None:
        # urllib cannot send user:pass@host itself; move it into a Basic header.
        credentials = f"{unquote(parts.username or '')}:{unquote(parts.password or '')}"
        target["authorization"] = "Basic " + base64.b64encode(credentials.encode("utf-8")).decode("ascii")
        netloc = (f"[{hostname}]" if ":" in hostname else hostname) + (f":{port}" if port else "")
        target["url"] = urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))
    if target["format"] == "telegram":
        chat_ids = parse_qs(parts.query).get("chat_id")
        if not chat_ids or not chat_ids[0].strip():
            raise WebhookConfigError(f"the Telegram webhook for {hostname} needs ?chat_id= in its URL")
        target["chat_id"] = chat_ids[0].strip()
    return target


def parse_events(value):
    """Return (events, ignored names). Unknown names are skipped, not fatal."""
    if value is None or not value.strip():
        return set(DEFAULT_EVENTS), []
    requested = [item.casefold() for item in SEPARATORS.split(value.strip()) if item]
    ignored = sorted({item for item in requested if item not in EVENTS})
    events = {item for item in requested if item in EVENTS}
    return (events or set(DEFAULT_EVENTS)), ignored


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
    """Keep an untrusted title such as "@everyone" or "<!channel>" from pinging a whole channel."""
    return BROADCAST_MENTION.sub("@⁠", text).replace("<!", "<⁠!")


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
    shown = [item_label(item) for item in items[:MAX_TITLES_IN_TEXT]]
    text = f"{heading}: {len(items)} items. " + "; ".join(shown)
    if len(items) > len(shown):
        text += f"; and {len(items) - len(shown)} more"
    return quiet_mentions(text)[:MAX_TEXT]


def build_request(target, notification):
    event = notification["event"].removeprefix("download.")
    text = notification["text"]
    version = notification.get("version") or ""
    headers = {"User-Agent": "youtube-dl-nas" + (f"/{version}" if version else "")}
    if target.get("authorization"):
        headers["Authorization"] = target["authorization"]
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
    with build_opener(RefuseRedirects).open(request, timeout=timeout) as response:
        response.read(4096)
        return response.status


def retry_after_seconds(error):
    try:
        value = int(str(error.headers.get("Retry-After", "")).strip())
    except (AttributeError, TypeError, ValueError):
        return None
    return max(0, min(value, MAX_RETRY_AFTER_SECONDS))


def failure_reason(error):
    """Describe a delivery failure without the URL, which may hold a token."""
    if isinstance(error, HTTPError):
        if 300 <= error.code < 400:
            return f"HTTP {error.code} redirect; configure the final URL"
        return f"HTTP {error.code}"
    if isinstance(error, URLError) and isinstance(error.reason, BaseException):
        return type(error.reason).__name__
    return type(error).__name__


class WebhookNotifier:
    def __init__(self, targets=(), events=DEFAULT_EVENTS, app_version="", send=default_send,
                 retry_delays=RETRY_DELAYS_SECONDS, sleep=time.sleep, queue_size=QUEUE_SIZE):
        self.targets = list(targets)
        self.events = set(events)
        self.app_version = app_version
        self.send = send
        self.retry_delays = tuple(retry_delays)
        self.sleep = sleep
        self.channels = [
            {"target": target, "queue": Queue(maxsize=queue_size), "thread": None}
            for target in self.targets
        ]
        self.thread_lock = Lock()

    @classmethod
    def from_environment(cls, env=None, app_version="", **options):
        env = os.environ if env is None else env
        try:
            urls = read_urls(env)
        except WebhookConfigError as error:
            log(f"disabled: {error}")
            return cls(app_version=app_version, **options)
        events, ignored = parse_events(env.get("YDLNAS_WEBHOOK_EVENTS"))
        if ignored:
            log("YDLNAS_WEBHOOK_EVENTS ignored unknown names: " + ", ".join(ignored)
                + "; valid names are " + ", ".join(EVENTS))
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
        """Queue notifications for finished history rows; never blocks or raises.

        Returns how many notifications at least one target accepted.
        """
        if not self.enabled:
            return 0
        accepted = 0
        try:
            for notification in self.notifications(history_items):
                queued = False
                for channel in self.channels:
                    try:
                        channel["queue"].put_nowait(notification)
                        queued = True
                    except Full:
                        log(f"{channel['target']['host']}: queue full; dropped {notification['event']}")
                        continue
                    self._ensure_thread(channel)
                accepted += queued
        except Exception as error:  # A notification problem must never fail a download.
            log(f"could not queue a notification: {type(error).__name__}")
        return accepted

    def _ensure_thread(self, channel):
        with self.thread_lock:
            if channel["thread"] and channel["thread"].is_alive():
                return
            channel["thread"] = Thread(
                target=self._run, args=(channel,), name=f"webhook-{channel['target']['host']}", daemon=True,
            )
            channel["thread"].start()

    def _run(self, channel):
        while True:
            notification = channel["queue"].get()
            try:
                self.deliver(channel["target"], notification)
            finally:
                channel["queue"].task_done()

    def deliver(self, target, notification):
        """Send one notification to one target, retrying network errors, 429 and 5xx."""
        attempts = len(self.retry_delays) + 1
        for attempt in range(attempts):
            delay = self.retry_delays[attempt] if attempt < len(self.retry_delays) else 0
            try:
                return self.send(build_request(target, notification), REQUEST_TIMEOUT_SECONDS)
            except HTTPError as error:
                retryable = error.code == 429 or error.code >= 500
                if error.code == 429:
                    delay = max(delay, retry_after_seconds(error) or 0)
                reason = failure_reason(error)
            except (URLError, OSError, TimeoutError) as error:
                retryable = True
                reason = failure_reason(error)
            except Exception as error:
                retryable = False
                reason = failure_reason(error)
            if not retryable or attempt == attempts - 1:
                log(f"{target['host']}: {notification['event']} not delivered ({reason})")
                return None
            self.sleep(delay)
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
        print("No usable webhook URL is configured; see the [webhook] lines above.")
        return 1
    print("Events: " + ", ".join(sorted(notifier.events)))
    failed = 0
    for target, status in notifier.send_test():
        outcome = f"HTTP {status}" if status else "not delivered"
        print(f"{target['host']} ({target['format']}): {outcome}")
        failed += status is None
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
