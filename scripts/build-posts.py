#!/usr/bin/env python3
from __future__ import annotations

import email.utils
import hashlib
import html
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "content" / "posts"
POST_DIR = ROOT / "post"
TAG_DIR = ROOT / "tag"
SITE_URL = "https://VendettaMask.github.io"
SITE_TITLE = "地球屋"
SITE_DESCRIPTION = "嘘，侧耳倾听~"
LEGACY_TAG_SLUGS = {
    "光学设计": "N55L8ROXk",
    "zemax": "xccatPvT1r",
}


@dataclass
class Post:
    slug: str
    title: str
    date: str
    tags: list[str]
    description: str
    feature_image: str
    body: str
    body_html: str
    abstract_html: str
    text_excerpt: str


def parse_front_matter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---\n"):
        return {}, text

    end = text.find("\n---\n", 4)
    if end == -1:
        return {}, text

    raw_meta = text[4:end].strip().splitlines()
    body = text[end + 5 :]
    meta: dict[str, str] = {}

    for line in raw_meta:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        meta[key.strip()] = value.strip().strip('"')

    return meta, body


def path_from_root(page_depth: int) -> str:
    return "" if page_depth == 0 else "../" * page_depth


def abs_url(path: str) -> str:
    return f"{SITE_URL}/{path.lstrip('/')}"


def tag_slug(tag: str) -> str:
    if tag in LEGACY_TAG_SLUGS:
        return LEGACY_TAG_SLUGS[tag]
    ascii_slug = re.sub(r"[^a-z0-9]+", "-", tag.lower()).strip("-")
    if ascii_slug:
        return ascii_slug
    return "tag-" + hashlib.sha1(tag.encode("utf-8")).hexdigest()[:10]


def html_date(date_value: str) -> str:
    return html.escape(date_value)


def atom_date(date_value: str) -> str:
    try:
        date = datetime.strptime(date_value, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        date = datetime.now(timezone.utc)
    return date.isoformat().replace("+00:00", "Z")


def render_inline(value: str) -> str:
    value = html.escape(value)
    value = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", r'<img src="\2" alt="\1" loading="lazy">', value)
    value = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', value)
    value = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", value)
    value = re.sub(r"`([^`]+)`", r"<code>\1</code>", value)
    return value


def is_table_separator(line: str) -> bool:
    cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell or "") for cell in cells)


def split_table_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def render_markdown(markdown: str) -> str:
    lines = markdown.replace("\r\n", "\n").split("\n")
    output: list[str] = []
    paragraph: list[str] = []
    code: list[str] = []
    in_code = False
    in_list = False
    list_type = ""
    in_quote = False
    in_table = False
    table_header: list[str] = []
    table_rows: list[list[str]] = []

    def flush_paragraph() -> None:
        nonlocal paragraph
        if paragraph:
            output.append("<p>" + render_inline(" ".join(paragraph)) + "</p>")
            paragraph = []

    def close_list() -> None:
        nonlocal in_list, list_type
        if in_list:
            output.append(f"</{list_type}>")
            in_list = False
            list_type = ""

    def close_quote() -> None:
        nonlocal in_quote
        if in_quote:
            output.append("</blockquote>")
            in_quote = False

    def close_table() -> None:
        nonlocal in_table, table_header, table_rows
        if not in_table:
            return
        header_html = "".join(f"<th>{render_inline(cell)}</th>" for cell in table_header)
        row_html = "\n".join(
            "<tr>" + "".join(f"<td>{render_inline(cell)}</td>" for cell in row) + "</tr>"
            for row in table_rows
        )
        output.append(
            '<div class="table-wrapper"><table>\n'
            f"<thead><tr>{header_html}</tr></thead>\n"
            f"<tbody>\n{row_html}\n</tbody>\n"
            "</table></div>"
        )
        in_table = False
        table_header = []
        table_rows = []

    index = 0
    while index < len(lines):
        line = lines[index]
        if line.strip() == "<!-- more -->":
            flush_paragraph()
            close_list()
            close_quote()
            close_table()
            index += 1
            continue

        if line.startswith("```"):
            if in_code:
                output.append("<pre><code>" + html.escape("\n".join(code)) + "</code></pre>")
                code = []
                in_code = False
            else:
                flush_paragraph()
                close_list()
                close_quote()
                close_table()
                in_code = True
            index += 1
            continue

        if in_code:
            code.append(line)
            index += 1
            continue

        if not line.strip():
            flush_paragraph()
            close_list()
            close_quote()
            close_table()
            index += 1
            continue

        if (
            "|" in line
            and index + 1 < len(lines)
            and is_table_separator(lines[index + 1])
        ):
            flush_paragraph()
            close_list()
            close_quote()
            close_table()
            in_table = True
            table_header = split_table_row(line)
            index += 2
            continue

        if in_table:
            if "|" in line:
                table_rows.append(split_table_row(line))
                index += 1
                continue
            close_table()

        heading = re.match(r"^(#{1,6})\s+(.+)$", line)
        if heading:
            flush_paragraph()
            close_list()
            close_quote()
            close_table()
            level = len(heading.group(1))
            output.append(f"<h{level}>{render_inline(heading.group(2))}</h{level}>")
            index += 1
            continue

        quote = re.match(r"^>\s+(.+)$", line)
        if quote:
            flush_paragraph()
            close_list()
            close_table()
            if not in_quote:
                output.append("<blockquote>")
                in_quote = True
            output.append("<p>" + render_inline(quote.group(1)) + "</p>")
            index += 1
            continue

        bullet = re.match(r"^[-*]\s+(.+)$", line)
        ordered = re.match(r"^\d+[.)]\s+(.+)$", line)
        if bullet or ordered:
            flush_paragraph()
            close_quote()
            close_table()
            target_list_type = "ol" if ordered else "ul"
            if not in_list:
                output.append(f"<{target_list_type}>")
                in_list = True
                list_type = target_list_type
            elif list_type != target_list_type:
                close_list()
                output.append(f"<{target_list_type}>")
                in_list = True
                list_type = target_list_type
            item_text = (ordered or bullet).group(1)
            output.append("<li>" + render_inline(item_text) + "</li>")
            index += 1
            continue

        paragraph.append(line.strip())
        index += 1

    flush_paragraph()
    close_list()
    close_quote()
    close_table()
    if in_code:
        output.append("<pre><code>" + html.escape("\n".join(code)) + "</code></pre>")

    return "\n".join(output)


def markdown_excerpt(markdown: str) -> str:
    return markdown.split("<!-- more -->", 1)[0].strip()


def plain_text(markdown: str) -> str:
    text = re.sub(r"---\n.*?\n---\n", "", markdown, flags=re.S)
    text = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"[#>*_`-]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:160]


def load_posts() -> list[Post]:
    posts: list[Post] = []
    for source in sorted(SOURCE_DIR.glob("*.md")):
        meta, body = parse_front_matter(source.read_text(encoding="utf-8"))
        title = meta.get("title", source.stem)
        date = meta.get("date", "")
        tags = [tag.strip() for tag in meta.get("tags", "").split(",") if tag.strip()]
        description = meta.get("description", plain_text(body) or title)
        posts.append(
            Post(
                slug=source.stem,
                title=title,
                date=date,
                tags=tags,
                description=description,
                feature_image=meta.get("feature_image", ""),
                body=body,
                body_html=render_markdown(body),
                abstract_html=render_markdown(markdown_excerpt(body)),
                text_excerpt=plain_text(body),
            )
        )
    return sorted(posts, key=lambda post: post.date, reverse=True)


def head(title: str, css_path: str, description: str) -> str:
    return f"""<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{html.escape(title)}</title>
<link rel="shortcut icon" href="{SITE_URL}/favicon.ico?v=1657033241791">
<link href="https://cdn.jsdelivr.net/npm/remixicon@2.3.0/fonts/remixicon.css" rel="stylesheet">
<link rel="stylesheet" href="{css_path}">
<link rel="alternate" type="application/atom+xml" title="{html.escape(title)} - Atom Feed" href="{SITE_URL}/atom.xml">
<link rel="stylesheet" href="https://fonts.googleapis.com/css?family=Droid+Serif:400,700">
<meta name="description" content="{html.escape(description)}" />"""


def background() -> str:
    return """    <div class="dream-bg" aria-hidden="true">
      <div class="dream-bg__stars"></div>
      <div class="dream-bg__mist"></div>
    </div>"""


def header(prefix: str) -> str:
    return f"""        <div class="site-header">
  <a href="{prefix}">
  <img class="avatar" src="{prefix}images/avatar.png?v=1657033241791" alt="">
  </a>
  <h1 class="site-title">{SITE_TITLE}</h1>
  <p class="site-description">{SITE_DESCRIPTION}</p>
  <div class="menu-container">
    <a href="{prefix}" class="menu">首页</a>
    <a href="{prefix}archives" class="menu">归档</a>
    <a href="{prefix}tags" class="menu">标签</a>
    <a href="{prefix}post/about" class="menu">关于</a>
  </div>
</div>"""


def footer() -> str:
    return f"""        <div class="site-footer">
  Powered by <a href="{SITE_URL}" target="_blank">{SITE_TITLE}</a>
  <a class="rss" href="{SITE_URL}/atom.xml" target="_blank">
    <i class="ri-rss-line"></i> RSS
  </a>
</div>"""


def page(title: str, depth: int, description: str, content: str) -> str:
    prefix = path_from_root(depth)
    return f"""<html>
  <head>
{head(title, prefix + "styles/main.css", description)}
  </head>
  <body>
{background()}
    <div class="main">
      <div class="main-content">
{header(prefix)}
{content}
{footer()}
      </div>
    </div>
  </body>
</html>
"""


def post_tags_html(post: Post, prefix: str) -> str:
    return "\n".join(
        f'<a href="{prefix}tag/{tag_slug(tag)}/" class="post-tag"># {html.escape(tag)}</a>'
        for tag in post.tags
    )


def post_card(post: Post, prefix: str) -> str:
    feature = ""
    if post.feature_image:
        feature = f"""
      <a href="{prefix}post/{post.slug}/" class="post-feature-image" style="background-image: url('{prefix}{html.escape(post.feature_image)}')">
      </a>"""

    return f"""    <article class="post">
      <a href="{prefix}post/{post.slug}/">
        <h2 class="post-title">{html.escape(post.title)}</h2>
      </a>
      <div class="post-info">
        <span>{html_date(post.date)}</span>
        <span>1 min read</span>
        {post_tags_html(post, prefix)}
      </div>
{feature}
      <div class="post-abstract">
{post.abstract_html}
      </div>
    </article>"""


def write_post(post: Post) -> None:
    prefix = "../../"
    feature = ""
    if post.feature_image:
        feature = f'<img class="post-feature-image" src="{prefix}{html.escape(post.feature_image)}" alt="">'

    content = f"""        <div class="post-detail">
          <article class="post">
            <h2 class="post-title">{html.escape(post.title)}</h2>
            <div class="post-info">
              <span>{html_date(post.date)}</span>
              {post_tags_html(post, prefix)}
            </div>
            {feature}
            <div class="post-content-wrapper">
              <div class="post-content">
{post.body_html}
              </div>
            </div>
          </article>
        </div>"""
    out_dir = POST_DIR / post.slug
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "index.html").write_text(page(f"{post.title} | {SITE_TITLE}", 2, post.description, content), encoding="utf-8")


def write_index(posts: list[Post]) -> None:
    cards = "\n".join(post_card(post, "") for post in posts)
    content = f"""        <div class="post-container">
{cards}
</div>
        <div class="pagination-container"></div>"""
    (ROOT / "index.html").write_text(page(SITE_TITLE, 0, SITE_DESCRIPTION, content), encoding="utf-8")


def write_archives(posts: list[Post]) -> None:
    years: dict[str, list[Post]] = {}
    for post in posts:
        years.setdefault(post.date[:4] or "未归档", []).append(post)

    blocks = []
    for year, year_posts in sorted(years.items(), reverse=True):
        links = "\n".join(
            f"""        <a href="../post/{post.slug}/" class="post">
          <h2 class="post-title">{html.escape(post.title)}</h2>
          <div class="time">{html_date(post.date)}</div>
        </a>"""
            for post in year_posts
        )
        blocks.append(f"""    <h2 class="year">{html.escape(year)}</h2>
{links}""")

    content = f"""        <div class="archives-container">
{chr(10).join(blocks)}
</div>
        <div class="pagination-container"></div>"""
    (ROOT / "archives" / "index.html").write_text(page(SITE_TITLE, 1, SITE_DESCRIPTION, content), encoding="utf-8")


def write_tags(posts: list[Post]) -> None:
    tags: dict[str, list[Post]] = {}
    for post in posts:
        for tag in post.tags:
            tags.setdefault(tag, []).append(post)

    tag_links = "\n".join(
        f'<a class="tag" href="../tag/{tag_slug(tag)}/">{html.escape(tag)}</a>'
        for tag in sorted(tags)
    )
    content = f"""        <div class="tags-container">
          {tag_links}
        </div>"""
    (ROOT / "tags" / "index.html").write_text(page(SITE_TITLE, 1, SITE_DESCRIPTION, content), encoding="utf-8")

    for tag, tag_posts in tags.items():
        out_dir = TAG_DIR / tag_slug(tag)
        out_dir.mkdir(parents=True, exist_ok=True)
        cards = "\n".join(post_card(post, "../../") for post in tag_posts)
        content = f"""        <div class="current-tag-container">
            <h2 class="title">标签：# {html.escape(tag)}</h2>
        </div>
        <div class="post-container">
{cards}
</div>
        <div class="pagination-container"></div>"""
        (out_dir / "index.html").write_text(page(f"{tag} | {SITE_TITLE}", 2, SITE_DESCRIPTION, content), encoding="utf-8")


def write_atom(posts: list[Post]) -> None:
    updated = atom_date(posts[0].date) if posts else datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    entries = []
    for post in posts:
        post_url = abs_url(f"post/{post.slug}/")
        entries.append(
            f"""    <entry>
        <title type="html"><![CDATA[{post.title}]]></title>
        <id>{post_url}</id>
        <link href="{post_url}"></link>
        <updated>{atom_date(post.date)}</updated>
        <summary type="html"><![CDATA[{post.abstract_html}]]></summary>
        <content type="html"><![CDATA[{post.body_html}]]></content>
    </entry>"""
        )

    atom = f"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
    <id>{SITE_URL}</id>
    <title>{SITE_TITLE}</title>
    <updated>{updated}</updated>
    <generator>scripts/build-posts.py</generator>
    <link rel="alternate" href="{SITE_URL}"/>
    <link rel="self" href="{SITE_URL}/atom.xml"/>
    <subtitle>{SITE_DESCRIPTION}</subtitle>
    <logo>{SITE_URL}/images/avatar.png</logo>
    <icon>{SITE_URL}/favicon.ico</icon>
    <rights>All rights reserved {datetime.now().year}, {SITE_TITLE}</rights>
{chr(10).join(entries)}
</feed>
"""
    (ROOT / "atom.xml").write_text(atom, encoding="utf-8")


def main() -> None:
    if not SOURCE_DIR.exists():
        raise SystemExit(f"source directory not found: {SOURCE_DIR}")

    posts = load_posts()
    for post in posts:
        write_post(post)
        print(f"generated post/{post.slug}/index.html")

    write_index(posts)
    write_archives(posts)
    write_tags(posts)
    write_atom(posts)
    print("generated index.html")
    print("generated archives/index.html")
    print("generated tags/index.html and tag pages")
    print("generated atom.xml")
    print(f"done: {len(posts)} post(s)")


if __name__ == "__main__":
    main()
