import gzip
import http.server
import threading

import pytest

from wren.net import URL, NetError, fetch

PAGE = b"<p>hello</p>"


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def send_body(self, body, headers=()):
        self.send_response(200)
        for name, value in headers:
            self.send_header(name, value)
        if not any(name == "Transfer-Encoding" for name, _ in headers):
            self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/plain":
            self.send_body(PAGE, [("Content-Type", "text/html")])
        elif self.path == "/gzip":
            self.send_body(gzip.compress(PAGE), [("Content-Encoding", "gzip")])
        elif self.path == "/chunked":
            parts = [b"<p>hel", b"lo</p>"]
            body = b"".join(b"%x\r\n%s\r\n" % (len(p), p) for p in parts)
            self.send_body(body + b"0\r\n\r\n",
                           [("Transfer-Encoding", "chunked")])
        elif self.path == "/redirect":
            self.send_response(301)
            self.send_header("Location", "/plain")
            self.send_header("Content-Length", "0")
            self.end_headers()
        elif self.path == "/loop":
            self.send_response(302)
            self.send_header("Location", "/loop")
            self.send_header("Content-Length", "0")
            self.end_headers()
        elif self.path == "/latin1":
            self.send_body("café".encode("latin-1"),
                           [("Content-Type", "text/html; charset=iso-8859-1")])
        elif self.path == "/echo-headers":
            self.send_body(str(self.headers).encode())
        else:
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()


@pytest.fixture(scope="module")
def server():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def test_plain_get(server):
    resp = fetch(server + "/plain")
    assert resp.status == 200
    assert resp.body == PAGE


def test_gzip_body_is_decoded(server):
    assert fetch(server + "/gzip").body == PAGE


def test_chunked_body_is_joined(server):
    assert fetch(server + "/chunked").body == PAGE


def test_redirect_is_followed(server):
    resp = fetch(server + "/redirect")
    assert resp.body == PAGE
    assert resp.url.path == "/plain"


def test_redirect_loop_stops(server):
    with pytest.raises(NetError, match="too many redirects"):
        fetch(server + "/loop")


def test_404_is_returned_not_raised(server):
    assert fetch(server + "/missing").status == 404


def test_charset_from_content_type(server):
    assert fetch(server + "/latin1").text() == "café"


def test_request_headers(server):
    sent = fetch(server + "/echo-headers").text().lower()
    assert "host: 127.0.0.1" in sent
    assert "accept-encoding: gzip" in sent


def test_connection_refused_is_neterror():
    with pytest.raises(NetError):
        fetch("http://127.0.0.1:1/")


def test_data_url_plain_and_base64():
    assert fetch("data:text/html,<b>hi%20there</b>").body == b"<b>hi there</b>"
    assert fetch("data:text/plain;base64,aGVsbG8=").body == b"hello"


def test_file_url(tmp_path):
    page = tmp_path / "a.html"
    page.write_bytes(PAGE)
    url = "file://" + ("/" if not str(page).startswith("/") else "") \
        + str(page).replace("\\", "/")
    assert fetch(url).body == PAGE


def test_missing_file_is_neterror(tmp_path):
    with pytest.raises(NetError):
        fetch("file:///" + str(tmp_path / "nope.html").replace("\\", "/"))


@pytest.mark.parametrize("base,href,expected", [
    ("http://a.com/x/y.html", "z.html", "http://a.com/x/z.html"),
    ("http://a.com/x/y.html", "/z", "http://a.com/z"),
    ("http://a.com/x/y.html", "../z", "http://a.com/z"),
    ("http://a.com/x/y/", "./z", "http://a.com/x/y/z"),
    ("https://a.com/x", "//b.org/p", "https://b.org/p"),
    ("http://a.com:8080/x", "y", "http://a.com:8080/y"),
    ("http://a.com/x", "https://c.net/", "https://c.net/"),
    ("http://a.com/x?q=1", "#top", "http://a.com/x?q=1#top"),
])
def test_resolve(base, href, expected):
    assert str(URL(base).resolve(href)) == expected.split("#")[0]


def test_url_defaults():
    url = URL("example.com")
    assert (url.scheme, url.host, url.port, url.path) == \
        ("http", "example.com", 80, "/")
    assert URL("https://Example.com:8443/a#frag").path == "/a"
    with pytest.raises(NetError):
        URL("ftp://x/")
