#!/usr/bin/env python3
from __future__ import annotations

import base64
import html
import json
import mimetypes
import re
import secrets
import subprocess
import sys
import webbrowser
from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse


ROOT = Path(__file__).resolve().parents[1]
EDITOR_DIR = ROOT / "editor"
STATIC_DIR = EDITOR_DIR / "static"
POSTS_DIR = ROOT / "content" / "posts"
IMAGE_DIR = ROOT / "post-images"
BUILD_SCRIPT = ROOT / "scripts" / "build-posts.py"
HOST = "127.0.0.1"
PORT = 8765


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = value.strip("-")
    return value or f"post-{datetime.now().strftime('%Y%m%d-%H%M%S')}"


def parse_front_matter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}, text
    raw = text[4:end].strip().splitlines()
    body = text[end + 5 :]
    meta: dict[str, str] = {}
    for line in raw:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        meta[key.strip()] = value.strip().strip('"')
    return meta, body


def front_matter(meta: dict[str, str]) -> str:
    fields = ["title", "date", "tags", "description", "feature_image"]
    lines = ["---"]
    for field in fields:
        lines.append(f"{field}: {meta.get(field, '').strip()}")
    lines.append("---")
    lines.append("")
    lines.append("<!-- more -->")
    lines.append("")
    return "\n".join(lines)


def inline_markdown(text: str) -> str:
    text = html.unescape(text)
    text = text.replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


@dataclass
class MarkdownChunk:
    block: str
    text: str = ""
    attrs: dict[str, str] | None = None


class SimpleMarkdownParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.parts: list[str] = []
        self.stack: list[str] = []
        self.href_stack: list[str] = []
        self.list_depth = 0
        self.in_pre = False

    def add_block(self, text: str) -> None:
        text = text.strip()
        if text:
            self.parts.append(text)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {key: value or "" for key, value in attrs}
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6", "p", "blockquote"}:
            self.parts.append("\n")
            if tag.startswith("h"):
                self.parts.append("#" * int(tag[1]) + " ")
            elif tag == "blockquote":
                self.parts.append("> ")
        elif tag == "br":
            self.parts.append("\n")
        elif tag in {"strong", "b"}:
            self.parts.append("**")
        elif tag in {"em", "i"}:
            self.parts.append("*")
        elif tag == "code" and not self.in_pre:
            self.parts.append("`")
        elif tag == "pre":
            self.in_pre = True
            self.parts.append("\n```\n")
        elif tag == "a":
            self.href_stack.append(attr.get("href", ""))
            self.parts.append("[")
        elif tag == "img":
            src = attr.get("data-md-src") or attr.get("src", "")
            alt = attr.get("alt", "")
            if src.startswith("/post-images/"):
                src = "../.." + src
            self.parts.append(f"![{alt}]({src})")
        elif tag == "ul":
            self.list_depth += 1
            self.parts.append("\n")
        elif tag == "li":
            indent = "  " * max(0, self.list_depth - 1)
            self.parts.append(f"\n{indent}- ")
        self.stack.append(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6", "p", "blockquote"}:
            self.parts.append("\n")
        elif tag in {"strong", "b"}:
            self.parts.append("**")
        elif tag in {"em", "i"}:
            self.parts.append("*")
        elif tag == "code" and not self.in_pre:
            self.parts.append("`")
        elif tag == "pre":
            self.in_pre = False
            self.parts.append("\n```\n")
        elif tag == "a":
            href = self.href_stack.pop() if self.href_stack else ""
            self.parts.append(f"]({href})")
        elif tag == "ul":
            self.list_depth = max(0, self.list_depth - 1)
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self.in_pre:
            self.parts.append(html.unescape(data))
        else:
            self.parts.append(inline_markdown(data))

    def markdown(self) -> str:
        text = "".join(self.parts)
        text = re.sub(r"[ \t]+\n", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip() + "\n"


def html_to_markdown(fragment: str) -> str:
    parser = SimpleMarkdownParser()
    parser.feed(fragment)
    return parser.markdown()


def markdown_to_editor_html(markdown: str) -> str:
    lines = markdown.replace("\r\n", "\n").split("\n")
    out: list[str] = []
    paragraph: list[str] = []
    in_list = False
    in_code = False
    code: list[str] = []

    def render_inline(value: str) -> str:
        value = html.escape(value)
        value = re.sub(
            r"!\[([^\]]*)\]\(([^)]+)\)",
            lambda m: image_html(m.group(2), m.group(1)),
            value,
        )
        value = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', value)
        value = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", value)
        value = re.sub(r"`([^`]+)`", r"<code>\1</code>", value)
        return value

    def flush_paragraph() -> None:
        nonlocal paragraph
        if paragraph:
            out.append("<p>" + render_inline(" ".join(paragraph)) + "</p>")
            paragraph = []

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            out.append("</ul>")
            in_list = False

    for line in lines:
        if line.strip() == "<!-- more -->":
            continue
        if line.startswith("```"):
            if in_code:
                out.append("<pre><code>" + html.escape("\n".join(code)) + "</code></pre>")
                code = []
                in_code = False
            else:
                flush_paragraph()
                close_list()
                in_code = True
            continue
        if in_code:
            code.append(line)
            continue
        if not line.strip():
            flush_paragraph()
            close_list()
            continue
        heading = re.match(r"^(#{1,6})\s+(.+)$", line)
        if heading:
            flush_paragraph()
            close_list()
            level = len(heading.group(1))
            out.append(f"<h{level}>{render_inline(heading.group(2))}</h{level}>")
            continue
        item = re.match(r"^[-*]\s+(.+)$", line)
        if item:
            flush_paragraph()
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append("<li>" + render_inline(item.group(1)) + "</li>")
            continue
        paragraph.append(line.strip())
    flush_paragraph()
    close_list()
    return "\n".join(out) or "<p></p>"


def image_html(src: str, alt: str = "") -> str:
    display_src = src
    if src.startswith("../../post-images/"):
        display_src = "/post-images/" + src.split("/")[-1]
    return f'<img src="{html.escape(display_src)}" data-md-src="{html.escape(src)}" alt="{html.escape(alt)}">'


def json_response(handler: BaseHTTPRequestHandler, data: object, status: int = 200) -> None:
    payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(payload)))
    handler.end_headers()
    handler.wfile.write(payload)


def text_response(handler: BaseHTTPRequestHandler, text: str, status: int = 200, content_type: str = "text/plain") -> None:
    payload = text.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", f"{content_type}; charset=utf-8")
    handler.send_header("Content-Length", str(len(payload)))
    handler.end_headers()
    handler.wfile.write(payload)


class BlogEditorHandler(BaseHTTPRequestHandler):
    def do_HEAD(self) -> None:
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        target = STATIC_DIR / "index.html" if path in {"/", "/index.html"} else STATIC_DIR / path.lstrip("/")
        if path.startswith("/post-images/"):
            target = IMAGE_DIR / path.split("/")[-1]
        if target.exists() and target.is_file():
            content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(target.stat().st_size))
            self.end_headers()
            return
        self.send_response(404)
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        if path == "/api/posts":
            self.handle_posts()
            return
        if path == "/api/post":
            slug = parse_qs(parsed.query).get("slug", [""])[0]
            self.handle_post(slug)
            return
        if path.startswith("/post-images/"):
            self.serve_file(IMAGE_DIR / path.split("/")[-1])
            return
        if path in {"/", "/index.html"}:
            self.serve_file(STATIC_DIR / "index.html")
            return
        self.serve_file(STATIC_DIR / path.lstrip("/"))

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/post":
            self.save_post()
            return
        if parsed.path == "/api/image":
            self.save_image()
            return
        if parsed.path == "/api/build":
            self.build_site()
            return
        text_response(self, "not found", 404)

    def read_json(self) -> dict[str, object]:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8")
        return json.loads(raw) if raw else {}

    def handle_posts(self) -> None:
        posts = []
        for path in sorted(POSTS_DIR.glob("*.md")):
            meta, _body = parse_front_matter(path.read_text(encoding="utf-8"))
            posts.append(
                {
                    "slug": path.stem,
                    "title": meta.get("title", path.stem),
                    "date": meta.get("date", ""),
                    "tags": meta.get("tags", ""),
                }
            )
        posts.sort(key=lambda item: item["date"], reverse=True)
        json_response(self, {"posts": posts})

    def handle_post(self, slug: str) -> None:
        path = POSTS_DIR / f"{slug}.md"
        if not path.exists():
            json_response(self, {"error": "not found"}, 404)
            return
        meta, body = parse_front_matter(path.read_text(encoding="utf-8"))
        json_response(self, {"slug": slug, "meta": meta, "html": markdown_to_editor_html(body)})

    def save_post(self) -> None:
        data = self.read_json()
        meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
        html_body = str(data.get("html", ""))
        old_slug = str(data.get("oldSlug", "")).strip()
        slug = slugify(str(data.get("slug") or meta.get("title") or old_slug))
        path = POSTS_DIR / f"{slug}.md"
        meta = {str(key): str(value) for key, value in meta.items()}
        if not meta.get("date"):
            meta["date"] = datetime.now().strftime("%Y-%m-%d")
        markdown = front_matter(meta) + html_to_markdown(html_body)
        POSTS_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(markdown, encoding="utf-8")
        if old_slug and old_slug != slug:
            old_path = POSTS_DIR / f"{old_slug}.md"
            if old_path.exists():
                old_path.unlink()
        json_response(self, {"ok": True, "slug": slug})

    def save_image(self) -> None:
        data = self.read_json()
        name = str(data.get("name", "image.png"))
        payload = str(data.get("data", ""))
        match = re.match(r"data:(.*?);base64,(.*)", payload)
        if not match:
            json_response(self, {"error": "bad image"}, 400)
            return
        mime = match.group(1)
        ext = mimetypes.guess_extension(mime) or Path(name).suffix or ".png"
        if ext == ".jpe":
            ext = ".jpg"
        filename = f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(3)}{ext}"
        IMAGE_DIR.mkdir(parents=True, exist_ok=True)
        (IMAGE_DIR / filename).write_bytes(base64.b64decode(match.group(2)))
        json_response(
            self,
            {
                "ok": True,
                "src": f"/post-images/{filename}",
                "markdownSrc": f"../../post-images/{filename}",
            },
        )

    def build_site(self) -> None:
        result = subprocess.run(
            [sys.executable, str(BUILD_SCRIPT)],
            cwd=str(ROOT),
            text=True,
            capture_output=True,
            check=False,
        )
        json_response(self, {"ok": result.returncode == 0, "output": result.stdout + result.stderr})

    def serve_file(self, path: Path) -> None:
        try:
            path = path.resolve()
            allowed = [STATIC_DIR.resolve(), IMAGE_DIR.resolve()]
            if not any(path == base or base in path.parents for base in allowed):
                text_response(self, "forbidden", 403)
                return
            if not path.exists() or not path.is_file():
                text_response(self, "not found", 404)
                return
            content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            payload = path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        except BrokenPipeError:
            pass

    def log_message(self, format: str, *args: object) -> None:
        return


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), BlogEditorHandler)
    url = f"http://{HOST}:{PORT}/"
    print(f"博客编辑器已启动：{url}")
    print("关闭这个窗口即可停止编辑器。")
    webbrowser.open(url)
    server.serve_forever()


if __name__ == "__main__":
    main()
