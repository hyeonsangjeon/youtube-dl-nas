import json
import shutil
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from bottle import default_app
from webtest import TestApp

from test_server import server


ROOT = Path(__file__).resolve().parents[1]
BOOKMARKLET_MODULE = ROOT / "static" / "logical_js" / "bookmarklet.js"
NODE = shutil.which("node")


@pytest.fixture
def app():
    return TestApp(default_app())


def login(app):
    app.post("/login", {"id": "tester", "myPw": "secret", "next": "/youtube-dl"}, status=302)


def run_bookmarklet_script(body):
    if not NODE:
        pytest.skip("Node.js is unavailable")
    script = f"""
const bookmarklet = require(process.argv[1]);
{body}
"""
    completed = subprocess.run(
        [NODE, "-e", script, str(BOOKMARKLET_MODULE)],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def test_bookmarklet_get_prefills_review_and_never_queues(app):
    login(app)
    with patch.object(server, "enqueue_download") as enqueue:
        response = app.get(
            "/youtube-dl/bookmarklet",
            {"url": "https://www.youtube.com/watch?v=bookmark123&t=42"},
            headers={"Sec-Fetch-Site": "cross-site"},
            status=302,
        )
        assert response.location.endswith("/youtube-dl?shared=review")
        assert "bookmark123" not in response.location

        dashboard = app.get(response.location)
    enqueue.assert_not_called()
    assert 'window.YDLNAS_SHARED_URL = "https://www.youtube.com/watch?v=bookmark123&t=42"' in dashboard.text
    assert 'id="bookmarklet-link"' in dashboard.text
    assert "/youtube-dl/static/logical_js/bookmarklet.js" in dashboard.text


def test_bookmarklet_review_survives_login(app):
    response = app.get("/youtube-dl/bookmarklet", {"url": "https://youtu.be/after-login"}, status=302)
    assert response.location.endswith("/youtube-dl?shared=review")

    redirected = app.get(response.location, status=302)
    assert "next=%2Fyoutube-dl%3Fshared%3Dreview" in redirected.location
    assert "after-login" not in redirected.location

    signed_in = app.post(
        "/login",
        {"id": "tester", "myPw": "secret", "next": "/youtube-dl?shared=review"},
        status=302,
    )
    assert signed_in.location.endswith("/youtube-dl?shared=review")
    dashboard = app.get(signed_in.location)
    assert 'window.YDLNAS_SHARED_URL = "https://youtu.be/after-login"' in dashboard.text


def test_bookmarklet_keeps_non_ascii_page_urls(app):
    login(app)
    page_url = "https://example.com/영상/clip?title=한글"
    response = app.get("/youtube-dl/bookmarklet", {"url": page_url}, status=302)
    dashboard = app.get(response.location)
    assert "window.YDLNAS_SHARED_URL = " + json.dumps(page_url) in dashboard.text


def test_bookmarklet_keeps_exact_urls_that_end_in_punctuation(app):
    login(app)
    page_url = "https://en.wikipedia.org/wiki/Foo_(bar)"
    response = app.get("/youtube-dl/bookmarklet", {"url": page_url}, status=302)
    dashboard = app.get(response.location)
    assert 'window.YDLNAS_SHARED_URL = "https://en.wikipedia.org/wiki/Foo_(bar)"' in dashboard.text


def test_bookmarklet_rejects_urls_too_large_for_the_review_cookie(app):
    login(app)
    with patch.object(server, "enqueue_download") as enqueue:
        long_ascii = app.get("/youtube-dl/bookmarklet", {"url": "https://example.com/?q=" + "a" * 3000}, status=302)
        long_korean = app.get("/youtube-dl/bookmarklet", {"url": "https://example.com/" + "가" * 700}, status=302)
        fits = app.get("/youtube-dl/bookmarklet", {"url": "https://example.com/?q=" + "a" * 2000}, status=302)
    enqueue.assert_not_called()
    assert long_ascii.location.endswith("/youtube-dl?shared=invalid")
    assert long_korean.location.endswith("/youtube-dl?shared=invalid")
    assert fits.location.endswith("/youtube-dl?shared=review")
    assert "a" * 2000 in app.get(fits.location).text


def test_bookmarklet_reports_invalid_when_the_cookie_cannot_be_set(app, monkeypatch):
    login(app)

    def oversized(*args, **kwargs):
        raise ValueError("Content does not fit into a cookie.")

    monkeypatch.setattr(server, "set_share_review_cookie", oversized)
    response = app.get("/youtube-dl/bookmarklet", {"url": "https://youtu.be/x"}, status=302)
    assert response.location.endswith("/youtube-dl?shared=invalid")


def test_bookmarklet_without_url_reports_missing(app):
    login(app)
    response = app.get("/youtube-dl/bookmarklet", {"url": "not a link"}, status=302)
    assert response.location.endswith("/youtube-dl?shared=missing")


def test_bookmarklet_source_opens_review_page_for_current_location():
    result = run_bookmarklet_script("""
const source = bookmarklet.source('https://nas.example:8443/youtube-dl?x=1');
const opened = [];
const fakeWindow = { open: (url, name, features) => { opened.push({ url, name, features }); return {}; } };
const location = {
  href: 'https://www.youtube.com/watch?v=abc&list=xyz#access_token=secret',
  origin: 'https://www.youtube.com', pathname: '/watch', search: '?v=abc&list=xyz'
};
new Function('window', 'location', 'encodeURIComponent', source.slice('javascript:'.length))(
  fakeWindow, location, encodeURIComponent
);
console.log(JSON.stringify({ source, opened }));
""")

    assert result["source"].startswith("javascript:")
    assert "document.cookie" not in result["source"]
    assert "#" not in result["source"] and "%" not in result["source"]
    assert "secret" not in result["opened"][0]["url"]
    assert result["opened"] == [{
        "url": "https://nas.example:8443/youtube-dl/bookmarklet?url="
        "https%3A%2F%2Fwww.youtube.com%2Fwatch%3Fv%3Dabc%26list%3Dxyz",
        "name": "ydlnas",
        "features": "width=640,height=820",
    }]


def test_bookmarklet_source_falls_back_to_navigation_when_popups_are_blocked():
    result = run_bookmarklet_script("""
const source = bookmarklet.source('http://192.168.1.10:8080');
const fakeWindow = { open: () => null };
const location = { href: 'https://vimeo.com/123', origin: 'https://vimeo.com', pathname: '/123', search: '' };
new Function('window', 'location', 'encodeURIComponent', source.slice('javascript:'.length))(
  fakeWindow, location, encodeURIComponent
);
console.log(JSON.stringify({ href: location.href }));
""")

    assert result["href"] == "http://192.168.1.10:8080/youtube-dl/bookmarklet?url=https%3A%2F%2Fvimeo.com%2F123"


def test_bookmarklet_source_rejects_non_http_origins():
    result = run_bookmarklet_script("""
console.log(JSON.stringify([
  bookmarklet.source('javascript:alert(1)'),
  bookmarklet.source('file:///etc/passwd'),
  bookmarklet.source(''),
  bookmarklet.normalizeOrigin('https://nas.example/path?q=1'),
]));
""")

    assert result == ["", "", "", "https://nas.example"]
