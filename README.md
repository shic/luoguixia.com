# luoguixia.com static site

This repository contains a static export workflow for the current WordPress site at
`https://luoguixia.com`.

## Hosting

The deployable static site lives at the repository root so GitHub Pages can
serve it from `main` / `/root`. Keep `index.html`, `CNAME`, `.nojekyll`,
`robots.txt`, `sitemap.xml`, and the page directories at the top level.

## Export the current WordPress site

```bash
python3 scripts/export_static.py
```

The script reads the live Yoast sitemap, fetches the published same-domain
HTML pages, downloads same-domain CSS, JavaScript, images, and fonts, then
writes a fresh export to `public/` as a staging folder. Review the export, then
move the contents of `public/` to the repository root for GitHub Pages. By
default it does not expand every WordPress `srcset` image size; it keeps the
direct `src` / lazy-load assets so the Git repository stays deployable.

## Local preview

```bash
python3 -m http.server 4173
```

Open `http://127.0.0.1:4173/`.

## Validate the static export

```bash
python3 scripts/validate_static.py
python3 scripts/validate_static.py --base-url http://127.0.0.1:4173
```

The validator checks required Pages files, large-file limits, sitemap coverage,
unwanted same-domain absolute URLs, `srcset` expansion, and key HTTP paths when
a local preview URL is provided.

## GitHub Pages setup

1. Push this repository to GitHub.
2. In repository settings, enable Pages.
3. Set the source to `Deploy from a branch`.
4. Select branch `main` and folder `/root`.
5. Keep root-level `CNAME` if using the apex domain `luoguixia.com`.
6. Point DNS to GitHub Pages.

## Static-site caveats

The exported site cannot run WordPress PHP, `/wp-admin`, WooCommerce cart,
checkout, account pages, comments, or Avada form submissions. For launch:

- The exported Avada contact form falls back to `mailto:luoguixia@gmail.com`
  through `static-form-mailto.js`. Replace it with a static form
  provider or Cloudflare Pages Function if inbox delivery without a local email
  client is required.
- Remove or replace WooCommerce checkout/account/cart if they are not actively
  used.
- Cart, checkout, account, WordPress API, and login URLs are redirected in
  `_redirects` so visitors do not land on broken dynamic pages.
- Keep the SiteGround WordPress install private or password-protected as the
  editing/source system until the new static workflow fully replaces it.
