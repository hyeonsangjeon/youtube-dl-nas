import json
import socketserver
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Event, Thread
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

import pytest

import webhooks
from test_server import server
from webhooks import WebhookConfigError, WebhookNotifier, build_request, parse_events, parse_target


COMPLETED = {
    "uuid": "done-1",
    "status": "completed",
    "title": "보름달 타임랩스",
    "channel": "Night Sky",
    "url": "https://youtu.be/moon",
    "resolution": "best",
    "relative_path": "보름달 타임랩스.mp4",
    "filename": "보름달 타임랩스.mp4",
    "file_size_bytes": 157286400,
    "download_type": "video",
}
FAILED = {"uuid": "fail-1", "status": "error", "title": "Broken", "url": "https://youtu.be/x", "failure_code": "network"}
CANCELED = {"uuid": "cancel-1", "status": "canceled", "title": "Stopped"}


class LocalHTTPServer(ThreadingHTTPServer):
    def server_bind(self):
        # HTTPServer.server_bind() calls socket.getfqdn(), which stalls for tens of
        # seconds on resolvers that answer reverse lookups for 127.0.0.1.
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address[:2]


def payload(request):
    return json.loads(request.data.decode("utf-8"))


@pytest.mark.parametrize("url,expected", [
    ("https://discord.com/api/webhooks/1/token", "discord"),
    ("https://discordapp.com/api/webhooks/1/token", "discord"),
    ("https://hooks.slack.com/services/T/B/token", "slack"),
    ("https://ntfy.sh/my-topic", "ntfy"),
    ("https://api.telegram.org/bot123:abc/sendMessage?chat_id=42", "telegram"),
    ("http://homeassistant.local:8123/api/webhook/nas", "json"),
    ("https://discord.com/not-a-webhook", "json"),
])
def test_format_follows_the_webhook_host(url, expected):
    assert parse_target(url)["format"] == expected


def test_format_prefix_overrides_the_host_and_is_removed_from_the_url():
    target = parse_target("ntfy+http://ntfy.home.lan/downloads")
    assert target == {"url": "http://ntfy.home.lan/downloads", "format": "ntfy", "host": "ntfy.home.lan"}
    assert parse_target("https://example.com/a+b")["url"] == "https://example.com/a+b"


def test_invalid_targets_are_rejected_without_echoing_secrets():
    with pytest.raises(WebhookConfigError) as error:
        parse_target("ftp://example.com/secret-token")
    assert "secret-token" not in str(error.value)

    with pytest.raises(WebhookConfigError, match="needs \\?chat_id="):
        parse_target("https://api.telegram.org/botSECRET/sendMessage")


def test_events_default_to_completed_and_failed_and_reject_unknown_names():
    assert parse_events(None) == {"completed", "failed"}
    assert parse_events(" completed, canceled ,skipped") == {"completed", "canceled", "skipped"}
    with pytest.raises(WebhookConfigError, match="unknown started"):
        parse_events("completed,started")


def test_environment_accepts_several_urls_and_logs_hosts_only(capsys):
    notifier = WebhookNotifier.from_environment({
        "YDLNAS_WEBHOOK_URL": "https://discord.com/api/webhooks/1/discord-secret,\n"
                              "ntfy+http://ntfy.home.lan/topic-secret  ftp://bad/ftp-secret",
    }, app_version="26.1028")

    assert [target["format"] for target in notifier.targets] == ["discord", "ntfy"]
    logged = capsys.readouterr().err
    assert "discord.com (discord)" in logged and "ntfy.home.lan (ntfy)" in logged
    assert "skipped one target" in logged
    assert "secret" not in logged


def test_environment_reads_the_secret_file_when_the_variable_is_empty(tmp_path):
    secret = tmp_path / "webhook"
    secret.write_text("https://ntfy.sh/from-file\n", encoding="utf-8")
    notifier = WebhookNotifier.from_environment({"YDLNAS_WEBHOOK_URL": "", "YDLNAS_WEBHOOK_URL_FILE": str(secret)})
    assert [target["url"] for target in notifier.targets] == ["https://ntfy.sh/from-file"]

    missing = WebhookNotifier.from_environment({"YDLNAS_WEBHOOK_URL_FILE": str(tmp_path / "missing")})
    assert not missing.enabled


def test_unconfigured_notifier_is_disabled_and_ignores_history():
    notifier = WebhookNotifier.from_environment({})
    assert not notifier.enabled
    assert notifier.notify([COMPLETED]) == 0


def test_notifications_group_by_event_and_honor_the_event_filter():
    notifier = WebhookNotifier([parse_target("https://example.com/hook")], app_version="26.1028")
    notifications = list(notifier.notifications([COMPLETED, FAILED, CANCELED, {"status": "missing"}]))

    assert [item["event"] for item in notifications] == ["download.completed", "download.failed"]
    completed, failed = notifications
    assert completed["text"] == "Downloaded: 보름달 타임랩스 (Night Sky, 150.0 MB)"
    assert completed["items"][0]["relative_path"] == "보름달 타임랩스.mp4"
    assert completed["version"] == "26.1028" and completed["count"] == 1
    assert failed["text"] == "Download failed: Broken (network)"


def test_playlist_completion_is_one_notification_with_a_short_summary():
    notifier = WebhookNotifier([parse_target("https://example.com/hook")])
    items = [{**COMPLETED, "uuid": str(index), "title": f"Episode {index}"} for index in range(30)]
    (notification,) = notifier.notifications(items)

    assert notification["count"] == 30
    assert len(notification["items"]) == webhooks.MAX_ITEMS
    assert notification["text"].startswith("Downloaded: 30 items. Episode 0; Episode 1;")
    assert notification["text"].endswith("; and 25 more")


def test_untrusted_titles_cannot_ping_a_whole_channel():
    notifier = WebhookNotifier()
    (notification,) = notifier.notifications([{**COMPLETED, "title": "@everyone <!channel> @Here & more", "channel": ""}])
    assert "@everyone" not in notification["text"] and "@Here" not in notification["text"]
    assert notification["text"].startswith("Downloaded: @\u2060everyone <!channel> @\u2060Here & more")

    slack = build_request(parse_target("https://hooks.slack.com/services/T/B/t"), notification)
    assert "&lt;!channel&gt;" in payload(slack)["text"]
    assert "<!channel>" not in payload(slack)["text"]
    assert "@user" in webhooks.quiet_mentions("@user")


def test_requests_match_each_service_format():
    notifier = WebhookNotifier(app_version="26.1028")
    (notification,) = notifier.notifications([COMPLETED])

    discord = build_request(parse_target("https://discord.com/api/webhooks/1/t"), notification)
    assert payload(discord) == {"content": notification["text"], "allowed_mentions": {"parse": []}}

    slack = build_request(parse_target("https://hooks.slack.com/services/T/B/t"), notification)
    assert payload(slack) == {"text": notification["text"]}

    telegram = build_request(parse_target("https://api.telegram.org/bot1:t/sendMessage?chat_id=-100"), notification)
    assert payload(telegram) == {"chat_id": "-100", "text": notification["text"], "disable_web_page_preview": True}

    ntfy = build_request(parse_target("https://ntfy.sh/topic"), notification)
    assert ntfy.data.decode("utf-8") == notification["text"]
    assert ntfy.get_header("Title") == "youtube-dl-nas: downloaded"
    assert ntfy.get_header("Tags") == "white_check_mark"
    assert ntfy.get_header("Title").isascii()

    generic = build_request(parse_target("https://example.com/hook"), notification)
    assert payload(generic) == notification
    assert generic.get_method() == "POST"
    assert generic.get_header("User-agent") == "youtube-dl-nas/26.1028"


def test_delivery_retries_server_errors_but_not_client_errors(capsys):
    target = parse_target("https://example.com/hook/secret-path")
    (notification,) = WebhookNotifier().notifications([FAILED])
    sleeps = []

    outcomes = [HTTPError(target["url"], 503, "busy", {}, None), 204]

    def flaky(request, timeout):
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    notifier = WebhookNotifier([target], send=flaky, sleep=sleeps.append)
    assert notifier.deliver(target, notification) == 204
    assert sleeps == [2]

    rejected = MagicMock(side_effect=HTTPError(target["url"], 400, "bad", {}, None))
    notifier = WebhookNotifier([target], send=rejected, sleep=sleeps.append)
    assert notifier.deliver(target, notification) is None
    assert rejected.call_count == 1

    offline = MagicMock(side_effect=URLError("offline"))
    notifier = WebhookNotifier([target], send=offline, sleep=lambda _: None)
    assert notifier.deliver(target, notification) is None
    assert offline.call_count == 3
    logged = capsys.readouterr().err
    assert "example.com: download.failed not delivered (HTTP 400)" in logged
    assert "secret-path" not in logged


def test_notify_never_blocks_or_raises_when_the_queue_is_full(capsys):
    notifier = WebhookNotifier([parse_target("https://example.com/hook")], queue_size=1)
    with patch.object(notifier, "_ensure_thread"):
        assert notifier.notify([COMPLETED]) == 1
        assert notifier.notify([COMPLETED]) == 0
    assert "queue full" in capsys.readouterr().err

    broken = WebhookNotifier([parse_target("https://example.com/hook")])
    with patch.object(broken, "notifications", side_effect=RuntimeError("boom")):
        assert broken.notify([COMPLETED]) == 0


def test_background_thread_posts_utf8_json_to_a_real_http_endpoint():
    received = []
    arrived = Event()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            received.append((self.path, self.headers["Content-Type"], json.loads(body.decode("utf-8"))))
            self.send_response(204)
            self.end_headers()
            arrived.set()

    endpoint = LocalHTTPServer(("127.0.0.1", 0), Handler)
    Thread(target=endpoint.serve_forever, daemon=True).start()
    try:
        notifier = WebhookNotifier.from_environment({
            "YDLNAS_WEBHOOK_URL": f"http://127.0.0.1:{endpoint.server_port}/hook",
        }, app_version="26.1028")
        assert notifier.notify([COMPLETED]) == 1
        assert arrived.wait(5)
    finally:
        endpoint.shutdown()
        endpoint.server_close()

    path, content_type, body = received[0]
    assert path == "/hook"
    assert content_type == "application/json; charset=utf-8"
    assert body["event"] == "download.completed"
    assert body["items"][0]["title"] == "보름달 타임랩스"


def test_send_test_reports_each_target(capsys):
    sent = []
    notifier = WebhookNotifier(
        [parse_target("https://ntfy.sh/topic"), parse_target("https://example.com/hook")],
        send=lambda request, timeout: sent.append(request) or 200,
    )
    results = notifier.send_test()
    assert [status for _, status in results] == [200, 200]
    assert sent[0].get_header("Tags") == "bell"
    assert payload(sent[1])["event"] == "download.test"


def test_history_completion_hands_finished_rows_to_the_notifier():
    manager = server.GlobalDownloadManager()
    notifier = MagicMock()
    with patch.object(server, "download_manager", manager), \
         patch.object(server, "collections_service", MagicMock()), \
         patch.object(server, "webhook_notifier", notifier), \
         patch.object(manager, "save_history"), \
         patch.object(manager, "broadcast_to_all_clients"):
        manager.complete_download({
            "uuid": "notify-job",
            "url": "https://youtu.be/notify",
            "resolution": "best",
            "status": "failed",
            "failure_code": "network",
        })

    (rows,) = notifier.notify.call_args.args
    assert [(row["uuid"], row["status"]) for row in rows] == [("notify-job", "failed")]


def test_secondary_download_managers_do_not_notify():
    manager = server.GlobalDownloadManager()
    notifier = MagicMock()
    with patch.object(server, "webhook_notifier", notifier), \
         patch.object(manager, "save_history"), \
         patch.object(manager, "broadcast_to_all_clients"):
        manager.complete_download({"uuid": "side", "url": "https://youtu.be/side", "status": "completed"})
    notifier.notify.assert_not_called()
