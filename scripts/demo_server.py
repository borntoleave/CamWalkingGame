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
SOCIAL_BAD = re.compile(r'[/\\:*?"<>|]|\.\.')
MAX_BODY = 12_000_000
MAX_EMAIL_COPIES = 10000


def photo_base(email, social, email_photo, mention):
    """Two Y/N flags (email the photo, then mention), then the filled values."""
    if email and (not EMAIL_RE.match(email) or ".." in email):
        raise ValueError("bad email")
    if social and (len(social) > 64 or SOCIAL_BAD.search(social)):
        raise ValueError("bad social tag")
    if email_photo and not email:
        raise ValueError("email required")
    if mention and not social:
        raise ValueError("social tag required")
    if not email and not social:
        raise ValueError("need email or social tag")
    parts = ["Y" if email_photo else "N", "Y" if mention else "N"]
    if email:
        parts.append(email)
    if social:
        parts.append(social)
    return " ".join(parts)


def save_photo(email, social, blob, email_photo=False, mention=False):
    """Write pics/{email Y|N} {mention Y|N} {email} {tag}.jpg."""
    PICS.mkdir(parents=True, exist_ok=True)
    pics = PICS.resolve()
    base = photo_base(email, social, email_photo, mention)
    for n in range(MAX_EMAIL_COPIES):
        stem = base if n == 0 else f"{base} {n}"
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
            social = str(body.get("social", "")).strip()
            email_photo = body.get("emailPhoto") is True
            mention = body.get("mention") is True
            data = str(body.get("image", ""))
            if "," not in data or not data.startswith("data:image/"):
                raise ValueError("bad image")
            blob = base64.b64decode(data.split(",", 1)[1], validate=True)
            if len(blob) < 32 or len(blob) > 8_000_000:
                raise ValueError("bad image size")
            if not (blob.startswith(b"\xff\xd8") or blob.startswith(b"\x89PNG")):
                raise ValueError("not a jpeg or png")
            stem = save_photo(email, social, blob, email_photo, mention)
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
