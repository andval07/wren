"""HTTP/1.1 client on raw sockets, plus file:// and data: URLs."""

import base64
import gzip
import os
import socket
import ssl
import urllib.parse
import zlib

MAX_REDIRECTS = 5
TIMEOUT_S = 10
USER_AGENT = "wren/0.1"


class NetError(Exception):
    pass


class URL:
    """An absolute URL. Supports http, https, file and data."""

    def __init__(self, text):
        text = text.strip()
        if text.startswith("data:"):
            self.scheme, self.data = "data", text[5:]
            self.host, self.port, self.path = "", 0, ""
            return
        if "://" not in text:
            text = "http://" + text
        self.scheme, rest = text.split("://", 1)
        self.scheme = self.scheme.lower()
        if self.scheme not in ("http", "https", "file"):
            raise NetError(f"unsupported scheme: {self.scheme}")
        if self.scheme == "file":
            self.host, self.port, self.path = "", 0, rest
            return
        if "/" not in rest:
            rest += "/"
        hostport, path = rest.split("/", 1)
        self.path = "/" + path.split("#", 1)[0]
        self.port = 443 if self.scheme == "https" else 80
        if ":" in hostport:
            hostport, port = hostport.rsplit(":", 1)
            self.port = int(port)
        self.host = hostport.lower()

    def resolve(self, href):
        """Turn a link found on this page into an absolute URL."""
        href = href.strip()
        if "://" in href or href.startswith("data:"):
            return URL(href)
        if self.scheme == "data":
            raise NetError("relative link inside a data: URL")
        if href.startswith("//"):
            return URL(self.scheme + ":" + href)
        if self.scheme == "file":
            base = self.path
        else:
            base = self.path
        if href.startswith("#"):
            href = base.split("#")[0] + href
        elif not href.startswith("/"):
            directory = base.split("?", 1)[0].rsplit("/", 1)[0]
            href = directory + "/" + href
        href = _normalize_dots(href)
        if self.scheme == "file":
            return URL("file://" + href)
        default = 443 if self.scheme == "https" else 80
        port = "" if self.port == default else f":{self.port}"
        return URL(f"{self.scheme}://{self.host}{port}{href}")

    def __str__(self):
        if self.scheme == "data":
            return "data:" + self.data
        if self.scheme == "file":
            return "file://" + self.path
        default = 443 if self.scheme == "https" else 80
        port = "" if self.port == default else f":{self.port}"
        return f"{self.scheme}://{self.host}{port}{self.path}"


def _normalize_dots(path):
    path, sep, query = path.partition("?")
    out = []
    for part in path.split("/"):
        if part == "..":
            if len(out) > 1:
                out.pop()
        elif part != ".":
            out.append(part)
    return "/".join(out) + sep + query


class Response:
    def __init__(self, url, status, headers, body):
        self.url = url
        self.status = status
        self.headers = headers
        self.body = body

    def text(self):
        ctype = self.headers.get("content-type", "")
        charset = "utf-8"
        if "charset=" in ctype:
            charset = ctype.split("charset=", 1)[1].split(";")[0].strip()
        try:
            return self.body.decode(charset, errors="replace")
        except LookupError:
            return self.body.decode("utf-8", errors="replace")


def fetch(url, max_redirects=MAX_REDIRECTS):
    """Load a URL and follow redirects. Returns a Response."""
    if isinstance(url, str):
        url = URL(url)
    for _ in range(max_redirects + 1):
        if url.scheme == "data":
            return _fetch_data(url)
        if url.scheme == "file":
            return _fetch_file(url)
        resp = _fetch_http(url)
        if 300 <= resp.status < 400 and "location" in resp.headers:
            url = url.resolve(resp.headers["location"])
            continue
        return resp
    raise NetError(f"too many redirects (> {max_redirects})")


def _fetch_data(url):
    meta, _, payload = url.data.partition(",")
    if meta.endswith(";base64"):
        body = base64.b64decode(payload)
        meta = meta[: -len(";base64")]
    else:
        body = urllib.parse.unquote_to_bytes(payload)
    ctype = meta or "text/plain;charset=US-ASCII"
    return Response(url, 200, {"content-type": ctype}, body)


def _fetch_file(url):
    path = urllib.parse.unquote(url.path)
    # file:///C:/x on Windows arrives as /C:/x
    if os.name == "nt" and len(path) > 2 and path[0] == "/" and path[2] == ":":
        path = path[1:]
    try:
        with open(path, "rb") as f:
            body = f.read()
    except OSError as e:
        raise NetError(f"cannot read {path}: {e.strerror}") from e
    return Response(url, 200, {"content-type": "text/html"}, body)


def _fetch_http(url):
    try:
        sock = socket.create_connection((url.host, url.port), TIMEOUT_S)
    except OSError as e:
        raise NetError(f"cannot connect to {url.host}:{url.port}: {e}") from e
    try:
        if url.scheme == "https":
            ctx = ssl.create_default_context()
            sock = ctx.wrap_socket(sock, server_hostname=url.host)
        request = (
            f"GET {url.path} HTTP/1.1\r\n"
            f"Host: {url.host}\r\n"
            f"User-Agent: {USER_AGENT}\r\n"
            "Accept-Encoding: gzip, deflate\r\n"
            "Connection: close\r\n"
            "\r\n"
        )
        sock.sendall(request.encode("ascii"))
        stream = sock.makefile("rb")
        status, headers = _read_head(stream)
        body = _read_body(stream, headers)
    except (OSError, ssl.SSLError) as e:
        raise NetError(f"{url.host}: {e}") from e
    finally:
        sock.close()
    body = _decode_body(body, headers.get("content-encoding", ""))
    return Response(url, status, headers, body)


def _read_head(stream):
    line = stream.readline().decode("latin-1")
    parts = line.split(" ", 2)
    if len(parts) < 2 or not parts[0].startswith("HTTP/"):
        raise NetError(f"bad status line: {line!r}")
    status = int(parts[1])
    headers = {}
    while True:
        line = stream.readline().decode("latin-1")
        if line in ("\r\n", "\n", ""):
            break
        name, _, value = line.partition(":")
        headers[name.strip().lower()] = value.strip()
    return status, headers


def _read_body(stream, headers):
    if headers.get("transfer-encoding", "").lower() == "chunked":
        return _read_chunked(stream)
    if "content-length" in headers:
        return stream.read(int(headers["content-length"]))
    return stream.read()


def _read_chunked(stream):
    chunks = []
    while True:
        size_line = stream.readline().decode("latin-1")
        size = int(size_line.split(";")[0].strip(), 16)
        if size == 0:
            # skip trailers up to the empty line
            while stream.readline() not in (b"\r\n", b"\n", b""):
                pass
            return b"".join(chunks)
        chunks.append(stream.read(size))
        stream.readline()


def _decode_body(body, encoding):
    encoding = encoding.lower()
    if encoding == "gzip":
        return gzip.decompress(body)
    if encoding == "deflate":
        try:
            return zlib.decompress(body)
        except zlib.error:
            return zlib.decompress(body, -zlib.MAX_WBITS)
    return body
