#!/usr/bin/env python3
"""Serve app/ and save lottery photos into the demo root pics/ folder."""

import argparse
import base64
import json
import re
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "app"
PICS = ROOT / "pics"
EMAIL_RE = re.compile(r"^[^@\s/\\]+@[^@\s/\\]+\.[^@\s/\\]+$")
MAX_BODY = 12_000_000
MAX_EMAIL_COPIES = 10000


def save_photo(email, blob):
    """Write pics/{email}.jpg, or pics/{email} N.jpg when that name is taken."""
    PICS.mkdir(parents=True, exist_ok=True)
    pics = PICS.resolve()
    for n in range(MAX_EMAIL_COPIES):
        stem = email if n == 0 else f"{email} {n}"
        dest = (PICS / f"{stem}.jpg").resolve()
        if pics not in dest.parents:
            raise ValueError("bad path")
        try:
            with dest.open("xb") as handle:
                handle.write(blob)
        except FileExistsError:
            continue
        return stem
    raise ValueError("too many photos for this email")


class DemoHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(APP), **kwargs)

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        if path != "/api/photo":
            self._json(404, {"ok": False, "error": "not found"})
            return
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0 or length > MAX_BODY:
            self._json(413, {"ok": False, "error": "image too large"})
            return
        raw = self.rfile.read(length)
        try:
            body = json.loads(raw.decode("utf-8"))
            email = str(body.get("email", "")).strip()
            data = str(body.get("image", ""))
            if not EMAIL_RE.match(email) or ".." in email:
                raise ValueError("bad email")
            if "," not in data or not data.startswith("data:image/"):
                raise ValueError("bad image")
            blob = base64.b64decode(data.split(",", 1)[1], validate=True)
            if len(blob) < 32 or len(blob) > 8_000_000:
                raise ValueError("bad image size")
            if not (blob.startswith(b"\xff\xd8") or blob.startswith(b"\x89PNG")):
                raise ValueError("not a jpeg or png")
            stem = save_photo(email, blob)
        except Exception as exc:
            self._json(400, {"ok": False, "error": str(exc)})
            return
        self._json(200, {"ok": True, "file": f"pics/{stem}.jpg"})

    def _json(self, code, payload):
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    PICS.mkdir(parents=True, exist_ok=True)
    httpd = ThreadingHTTPServer((args.bind, args.port), DemoHandler)
    print(f"Serving {APP}")
    print(f"URL:     http://{args.bind}:{args.port}/")
    print(f"Photos:  {PICS}")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
