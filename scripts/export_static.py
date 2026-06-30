#!/usr/bin/env python3
"""Export luoguixia.com from WordPress HTML into a static Pages-ready folder."""

from __future__ import annotations

import html
import posixpath
import re
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import deque
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_DIR = ROOT / "public"

CANONICAL_HOST = "luoguixia.com"
BASE_URL = f"https://{CANONICAL_HOST}/"
SITEMAP_URL = f"{BASE_URL}sitemap.xml"
HOSTS = {CANONICAL_HOST, f"www.{CANONICAL_HOST}"}
CONTACT_EMAIL = "luoguixia@gmail.com"

MAX_PAGES = 300
REQUEST_DELAY_SECONDS = 0.05
DISCOVER_LINKED_PAGES = False
DOWNLOAD_SRCSETS = False
LOG_FETCHES = False
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36 "
    "luoguixia-static-export/1.0"
)

ASSET_EXTENSIONS = {
    ".avif",
    ".css",
    ".eot",
    ".gif",
    ".ico",
    ".jpeg",
    ".jpg",
    ".js",
    ".json",
    ".map",
    ".mp4",
    ".otf",
    ".pdf",
    ".png",
    ".svg",
    ".ttf",
    ".txt",
    ".webm",
    ".webp",
    ".woff",
    ".woff2",
    ".xml",
}

SKIP_PATH_PREFIXES = (
    "/wp-admin/",
    "/wp-json/",
    "/wp-content/plugins/jetpack/jetpack_vendor/automattic/woocommerce-analytics/",
    "/wp-content/uploads/wc-logs/",
    "/wp-content/uploads/woocommerce_transient_files/",
    "/wp-content/uploads/woocommerce_uploads/",
)

SKIP_PATHS = {
    "/wp-login.php",
    "/xmlrpc.php",
    "/wp-admin/admin-ajax.php",
}

SKIP_PAGE_PATHS = {
    "/shop/checkout/",
    "/shop/my-account/",
    "/shop/my-account/lost-password/",
    "/shop/shopping-cart/",
}


@dataclass(frozen=True)
class FetchResult:
    url: str
    content_type: str
    body: bytes


def fetch(url: str) -> FetchResult | None:
    if LOG_FETCHES:
        print(f"fetch: {url}", flush=True)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(1, 4):
        try:
            with urllib.request.urlopen(req, timeout=45) as response:
                body = response.read()
                content_type = response.headers.get_content_type()
                final_url = normalize_url(response.geturl()) or url
                return FetchResult(final_url, content_type, body)
        except urllib.error.HTTPError as exc:
            print(f"warn: {exc.code} {url}")
            return None
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt == 3:
                print(f"warn: failed {url}: {exc}")
                return None
            time.sleep(attempt)
    return None


def normalize_url(raw_url: str | None, base_url: str = BASE_URL) -> str | None:
    if not raw_url:
        return None

    value = html.unescape(raw_url).strip().strip("'\"")
    if not value:
        return None
    if (
        any(character.isspace() for character in value)
        and not value.startswith(("/", "./", "../", "http://", "https://", "//"))
    ):
        return None

    lower = value.lower()
    if lower.startswith(("data:", "mailto:", "tel:", "sms:", "javascript:", "#")):
        return None

    absolute = urllib.parse.urljoin(base_url, value)
    parsed = urllib.parse.urlparse(absolute)
    if parsed.scheme not in {"http", "https"} or parsed.netloc.lower() not in HOSTS:
        return None

    path = urllib.parse.quote(
        urllib.parse.unquote(parsed.path or "/"),
        safe="/:@!$&'()*+,;=-._~%",
    )
    return urllib.parse.urlunparse(
        ("https", CANONICAL_HOST, path, "", parsed.query, "")
    )


def is_skipped(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    path = parsed.path
    query = parsed.query.lower()
    if path in SKIP_PATHS:
        return True
    if any(path.startswith(prefix) for prefix in SKIP_PATH_PREFIXES):
        return True
    if "add-to-cart" in query or "wc-ajax" in query or "replytocom" in query:
        return True
    return False


def is_probable_page(url: str) -> bool:
    if is_skipped(url):
        return False
    parsed = urllib.parse.urlparse(url)
    if parsed.query:
        return False
    path = parsed.path or "/"
    if path in SKIP_PAGE_PATHS:
        return False
    if path.endswith("/feed/") or path == "/feed/" or "/comments/feed/" in path:
        return False
    if path.startswith(("/wp-content/", "/wp-includes/")):
        return False
    suffix = Path(path).suffix.lower()
    return suffix in {"", ".html"}


def looks_like_url_reference(value: str) -> bool:
    stripped = value.strip()
    return stripped.startswith(("http://", "https://", "//", "/", "./", "../"))


def is_probable_asset(url: str) -> bool:
    if is_skipped(url):
        return False
    parsed = urllib.parse.urlparse(url)
    path = parsed.path or "/"
    suffix = Path(path).suffix.lower()
    if path.startswith(("/wp-content/", "/wp-includes/")):
        return True
    return suffix in ASSET_EXTENSIONS


def parse_srcset(value: str, base_url: str) -> set[str]:
    urls: set[str] = set()
    for candidate in value.split(","):
        parts = candidate.strip().split()
        if parts:
            normalized = normalize_url(parts[0], base_url)
            if normalized:
                urls.add(normalized)
    return urls


CSS_URL_RE = re.compile(r"url\(\s*(['\"]?)(.*?)\1\s*\)", re.IGNORECASE)
GTX_TRANS_RE = re.compile(
    r"\s*<div\s+id=(['\"])gtx-trans\1[^>]*>\s*"
    r"<div\s+class=(['\"])gtx-trans-icon\2>\s*</div>\s*</div>",
    re.IGNORECASE,
)
TRACKING_SCRIPT_RE = re.compile(
    r"\s*<script\b[^>]*\bsrc=(['\"])[^'\"]*woocommerce-analytics-client\.js[^'\"]*\1"
    r"[^>]*>\s*</script>",
    re.IGNORECASE,
)


def collect_css_urls(css_text: str, base_url: str) -> set[str]:
    urls: set[str] = set()
    for match in CSS_URL_RE.finditer(css_text):
        value = match.group(2).strip()
        normalized = normalize_url(value, base_url)
        if normalized:
            urls.add(normalized)
    return urls


class LinkCollector(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.urls: set[str] = set()
        self._in_style = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._collect(tag, attrs)
        if tag.lower() == "style":
            self._in_style = True

    def handle_startendtag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        self._collect(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "style":
            self._in_style = False

    def handle_data(self, data: str) -> None:
        if self._in_style:
            self.urls.update(collect_css_urls(data, self.base_url))

    def _collect(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {name.lower(): value for name, value in attrs if value}
        for attr in (
            "href",
            "src",
            "poster",
            "data-src",
            "data-orig-file",
            "data-full-url",
            "data-retina_logo_url",
            "data-bg",
        ):
            value = attr_map.get(attr)
            normalized = normalize_url(value, self.base_url)
            if normalized:
                self.urls.add(normalized)

        meta_content = attr_map.get("content")
        meta_name = (attr_map.get("property") or attr_map.get("name") or "").lower()
        if meta_content and looks_like_url_reference(meta_content) and any(
            marker in meta_name for marker in ("image", "video", "audio", "url")
        ):
            normalized = normalize_url(meta_content, self.base_url)
            if normalized:
                self.urls.add(normalized)

        if DOWNLOAD_SRCSETS:
            for attr in ("srcset", "data-srcset"):
                value = attr_map.get(attr)
                if value:
                    self.urls.update(parse_srcset(value, self.base_url))

        style = attr_map.get("style")
        if style:
            self.urls.update(collect_css_urls(style, self.base_url))


def rewrite_same_domain_refs(text: str) -> str:
    replacements = (
        ("https://www.luoguixia.com", ""),
        ("http://www.luoguixia.com", ""),
        ("//www.luoguixia.com", ""),
        ("https://luoguixia.com", ""),
        ("http://luoguixia.com", ""),
        ("//luoguixia.com", ""),
        ("https:\\/\\/www.luoguixia.com", ""),
        ("http:\\/\\/www.luoguixia.com", ""),
        ("https:\\/\\/luoguixia.com", ""),
        ("http:\\/\\/luoguixia.com", ""),
    )
    for old, new in replacements:
        text = text.replace(old, new)
    return text


def strip_srcset_attrs(text: str) -> str:
    if DOWNLOAD_SRCSETS:
        return text
    text = re.sub(r"\s(?:srcset|data-srcset)=\"[^\"]*\"", "", text)
    text = re.sub(r"\s(?:srcset|data-srcset)='[^']*'", "", text)
    return text


def remove_translation_artifacts(text: str) -> str:
    return GTX_TRANS_RE.sub("", text)


def remove_dynamic_tracking_scripts(text: str) -> str:
    return TRACKING_SCRIPT_RE.sub("", text)


def inject_static_fixes(text: str) -> str:
    if "/static-fixes.css" not in text and "</head>" in text:
        text = text.replace(
            "</head>",
            '<link rel="stylesheet" href="/static-fixes.css"></head>',
            1,
        )
    return text


def sanitize_html(text: str) -> str:
    text = inject_static_fixes(
        remove_dynamic_tracking_scripts(
            remove_translation_artifacts(
                strip_srcset_attrs(rewrite_same_domain_refs(text))
            )
        )
    )
    if "fusion-form" in text and "static-form-mailto.js" not in text:
        text = text.replace(
            "</body>",
            '<script src="/static-form-mailto.js"></script></body>',
        )
    return text


def safe_output_path(url: str, is_page: bool) -> Path:
    parsed = urllib.parse.urlparse(url)
    raw_path = urllib.parse.unquote(parsed.path or "/")
    clean_path = posixpath.normpath(raw_path)
    if raw_path.endswith("/") and not clean_path.endswith("/"):
        clean_path += "/"
    if clean_path == ".":
        clean_path = "/"
    if clean_path.startswith("../") or clean_path == "..":
        raise ValueError(f"unsafe path: {url}")

    if is_page:
        if clean_path.endswith("/"):
            rel = f"{clean_path.lstrip('/')}index.html"
        elif Path(clean_path).suffix:
            rel = clean_path.lstrip("/")
        else:
            rel = f"{clean_path.lstrip('/')}/index.html"
    else:
        rel = clean_path.lstrip("/") or "index.html"

    path = (PUBLIC_DIR / rel).resolve()
    public_root = PUBLIC_DIR.resolve()
    if public_root not in path.parents and path != public_root:
        raise ValueError(f"unsafe output path: {path}")
    return path


def write_bytes(path: Path, body: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def parse_sitemap_locations(xml_body: bytes) -> list[str]:
    root = ET.fromstring(xml_body)
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    locs = [node.text or "" for node in root.findall(".//sm:loc", ns)]
    normalized: list[str] = []
    for loc in locs:
        url = normalize_url(loc)
        if url:
            normalized.append(url)
    return normalized


def load_sitemap_pages() -> set[str]:
    index = fetch(SITEMAP_URL)
    if not index:
        raise SystemExit(f"Could not fetch {SITEMAP_URL}")

    sitemap_urls = parse_sitemap_locations(index.body)
    pages: set[str] = set()
    for sitemap_url in sitemap_urls:
        result = fetch(sitemap_url)
        if not result:
            continue
        for loc in parse_sitemap_locations(result.body):
            if is_probable_page(loc):
                pages.add(loc)
    pages.add(BASE_URL)
    return pages


def write_support_files(pages: set[str]) -> None:
    write_text(PUBLIC_DIR / ".nojekyll", "")
    write_text(PUBLIC_DIR / "CNAME", f"{CANONICAL_HOST}\n")
    write_text(
        PUBLIC_DIR / "_headers",
        """/*
  X-Content-Type-Options: nosniff
  Referrer-Policy: strict-origin-when-cross-origin
""",
    )
    write_text(
        PUBLIC_DIR / "_redirects",
        """/wp-admin/* /
/wp-login.php /
/xmlrpc.php /404.html 404
/wp-json/* /404.html 404
/feed/ /sitemap.xml 301
/comments/feed/ /sitemap.xml 301
/shop/checkout/ /shop/ 302
/shop/checkout/* /shop/ 302
/shop/my-account/ /shop/ 302
/shop/my-account/* /shop/ 302
/shop/shopping-cart/ /shop/ 302
/shop/shopping-cart/* /shop/ 302
""",
    )
    write_text(
        PUBLIC_DIR / "robots.txt",
        f"""User-agent: *
Disallow:

Sitemap: https://{CANONICAL_HOST}/sitemap.xml
""",
    )
    write_text(
        PUBLIC_DIR / "static-fixes.css",
        """#gtx-trans,
.gtx-trans-icon {
  display: none !important;
  pointer-events: none !important;
  visibility: hidden !important;
}

.fusion-column-has-bg-image,
.fusion-column-has-bg-image.fusion-layout-column,
.fusion-column-has-bg-image .fusion-column-wrapper {
  background-image: var(--awb-bg-image) !important;
  background-position: var(--awb-bg-position, center center) !important;
  background-repeat: no-repeat !important;
  background-size: var(--awb-bg-size, cover) !important;
}

body.page-id-13 .fusion-builder-row-2 .fusion-column-has-bg-image {
  overflow: hidden;
}

body.page-id-13 .fusion-builder-row-2 .fusion-column-inner-bg-wrapper {
  --awb-inner-bg-color: rgba(255, 255, 255, 0.78) !important;
  --awb-inner-bg-color-hover: rgba(255, 255, 255, 0.62) !important;
  background-color: rgba(255, 255, 255, 0.78) !important;
}
""",
    )

    sitemap_urls = "\n".join(
        f"  <url><loc>{url}</loc></url>" for url in sorted(pages)
    )
    write_text(
        PUBLIC_DIR / "sitemap.xml",
        f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{sitemap_urls}
</urlset>
""",
    )
    write_text(
        PUBLIC_DIR / "404.html",
        """<!doctype html>
<html lang="it">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link rel="stylesheet" href="/static-fixes.css">
    <title>Pagina non trovata - Luo Guixia</title>
  </head>
  <body>
    <main style="font-family: sans-serif; max-width: 42rem; margin: 12vh auto; padding: 1rem;">
      <h1>Pagina non trovata</h1>
      <p><a href="/">Torna alla home</a></p>
    </main>
  </body>
</html>
""",
    )
    write_text(
        PUBLIC_DIR / "static-form-mailto.js",
        f"""(() => {{
  const recipient = "{CONTACT_EMAIL}";

  function labelFor(name) {{
    return name.replace(/[_-]+/g, " ").replace(/\\b\\w/g, (char) => char.toUpperCase());
  }}

  document.addEventListener("submit", (event) => {{
    const form = event.target;
    if (!(form instanceof HTMLFormElement) || !form.matches(".fusion-form")) {{
      return;
    }}

    event.preventDefault();
    const data = new FormData(form);
    const lines = [];

    for (const [name, value] of data.entries()) {{
      if (typeof value !== "string" || !value.trim()) {{
        continue;
      }}
      if (name.startsWith("fusion_") || name.startsWith("privacy_")) {{
        continue;
      }}
      lines.push(`${{labelFor(name)}}: ${{value.trim()}}`);
    }}

    const subject = data.get("subject") || "Website contact";
    const body = lines.join("\\n");
    window.location.href = `mailto:${{recipient}}?subject=${{encodeURIComponent(subject)}}&body=${{encodeURIComponent(body)}}`;
  }});
}})();
""",
    )


def export_site() -> None:
    if PUBLIC_DIR.exists():
        shutil.rmtree(PUBLIC_DIR)
    PUBLIC_DIR.mkdir(parents=True)

    sitemap_pages = load_sitemap_pages()
    page_queue: deque[str] = deque(sorted(sitemap_pages))
    asset_queue: deque[str] = deque()
    seen_pages: set[str] = set()
    seen_assets: set[str] = set()
    written_pages: set[str] = set()

    while page_queue and len(seen_pages) < MAX_PAGES:
        page_url = page_queue.popleft()
        if page_url in seen_pages or not is_probable_page(page_url):
            continue

        seen_pages.add(page_url)
        print(f"page: {page_url}", flush=True)
        result = fetch(page_url)
        time.sleep(REQUEST_DELAY_SECONDS)
        if not result or "html" not in result.content_type:
            continue

        text = result.body.decode("utf-8", errors="replace")
        collector = LinkCollector(page_url)
        collector.feed(text)

        for url in sorted(collector.urls):
            if DISCOVER_LINKED_PAGES and is_probable_page(url) and url not in seen_pages:
                page_queue.append(url)
            elif is_probable_asset(url) and url not in seen_assets:
                asset_queue.append(url)

        output = safe_output_path(page_url, is_page=True)
        write_text(output, sanitize_html(text))
        written_pages.add(page_url)

    while asset_queue:
        asset_url = asset_queue.popleft()
        if asset_url in seen_assets or not is_probable_asset(asset_url):
            continue

        seen_assets.add(asset_url)
        print(f"asset: {asset_url}", flush=True)
        result = fetch(asset_url)
        time.sleep(REQUEST_DELAY_SECONDS)
        if not result:
            continue

        body = result.body
        suffix = Path(urllib.parse.urlparse(asset_url).path).suffix.lower()
        if result.content_type == "text/css" or suffix == ".css":
            css = body.decode("utf-8", errors="replace")
            for url in sorted(collect_css_urls(css, asset_url)):
                if is_probable_asset(url) and url not in seen_assets:
                    asset_queue.append(url)
            body = rewrite_same_domain_refs(css).encode("utf-8")

        output = safe_output_path(asset_url, is_page=False)
        write_bytes(output, body)

    write_support_files(written_pages)
    print(
        f"done: wrote {len(written_pages)} pages and {len(seen_assets)} assets to "
        f"{PUBLIC_DIR}"
    )


if __name__ == "__main__":
    export_site()
