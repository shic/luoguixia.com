#!/usr/bin/env python3
"""Validate the generated static export before deploying to Pages."""

from __future__ import annotations

import argparse
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_DIR = ROOT / "public"
MAX_FILE_BYTES = 24 * 1024 * 1024
CANONICAL_HOST_PATTERN = re.compile(
    rb"https?://(www\.)?luoguixia\.com|//(www\.)?luoguixia\.com"
)

REQUIRED_FILES = [
    ".nojekyll",
    "404.html",
    "CNAME",
    "_headers",
    "_redirects",
    "index.html",
    "robots.txt",
    "sitemap.xml",
    "static-fixes.css",
    "static-form-mailto.js",
]

KEY_PATHS = [
    "/",
    "/projects/",
    "/about/",
    "/contact/",
    "/blog/",
    "/sitemap.xml",
    "/static-form-mailto.js",
    "/wp-content/uploads/2021/02/logo-100-200.png",
]


def fail(message: str) -> None:
    print(f"FAIL: {message}")
    raise SystemExit(1)


def check_required_files() -> None:
    missing = [name for name in REQUIRED_FILES if not (PUBLIC_DIR / name).exists()]
    if missing:
        fail(f"missing required files: {', '.join(missing)}")


def check_large_files() -> None:
    large = [
        path.relative_to(PUBLIC_DIR)
        for path in PUBLIC_DIR.rglob("*")
        if path.is_file() and path.stat().st_size > MAX_FILE_BYTES
    ]
    if large:
        fail("files exceed 24 MiB Pages limit: " + ", ".join(map(str, large)))


def check_html_rewrites() -> None:
    srcset_matches: list[str] = []
    absolute_matches: list[str] = []
    translation_matches: list[str] = []
    dynamic_tracking_matches: list[str] = []
    missing_static_fixes: list[str] = []

    for path in PUBLIC_DIR.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in {".html", ".css"}:
            continue
        body = path.read_bytes()
        if path.suffix.lower() == ".html":
            if b"srcset=" in body or b"data-srcset=" in body:
                srcset_matches.append(str(path.relative_to(PUBLIC_DIR)))
            if b"gtx-trans" in body:
                translation_matches.append(str(path.relative_to(PUBLIC_DIR)))
            if b"woocommerce-analytics-client.js" in body:
                dynamic_tracking_matches.append(str(path.relative_to(PUBLIC_DIR)))
            if b"/static-fixes.css" not in body:
                missing_static_fixes.append(str(path.relative_to(PUBLIC_DIR)))
        if CANONICAL_HOST_PATTERN.search(body):
            absolute_matches.append(str(path.relative_to(PUBLIC_DIR)))

    if srcset_matches:
        fail("srcset/data-srcset still present: " + ", ".join(srcset_matches[:10]))
    if translation_matches:
        fail(
            "Google Translate artifacts still present: "
            + ", ".join(translation_matches[:10])
        )
    if dynamic_tracking_matches:
        fail(
            "dynamic WooCommerce analytics script still present: "
            + ", ".join(dynamic_tracking_matches[:10])
        )
    if missing_static_fixes:
        fail("static-fixes.css not linked: " + ", ".join(missing_static_fixes[:10]))
    if absolute_matches:
        fail(
            "same-domain absolute URLs still present: "
            + ", ".join(absolute_matches[:10])
        )


def check_sitemap() -> None:
    sitemap = PUBLIC_DIR / "sitemap.xml"
    root = ET.parse(sitemap).getroot()
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    urls = root.findall("sm:url", ns)
    if len(urls) < 40:
        fail(f"sitemap contains only {len(urls)} URLs")


def check_contact_fallback() -> None:
    contact = (PUBLIC_DIR / "contact" / "index.html").read_text(errors="ignore")
    script = (PUBLIC_DIR / "static-form-mailto.js").read_text(errors="ignore")
    if "/static-form-mailto.js" not in contact:
        fail("contact page does not include static-form-mailto.js")
    if "luoguixia@gmail.com" not in script:
        fail("contact mailto fallback recipient missing")


def check_http(base_url: str) -> None:
    base = base_url.rstrip("/")
    for path in KEY_PATHS:
        url = urllib.parse.urljoin(base + "/", path.lstrip("/"))
        with urllib.request.urlopen(url, timeout=10) as response:
            if response.status != 200:
                fail(f"{path} returned HTTP {response.status}")
            print(f"HTTP {response.status} {path} {response.headers.get_content_type()}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", help="Optional local preview URL to check.")
    args = parser.parse_args()

    check_required_files()
    check_large_files()
    check_html_rewrites()
    check_sitemap()
    check_contact_fallback()
    if args.base_url:
        check_http(args.base_url)

    print("static export validation passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
