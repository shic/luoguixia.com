# luoguixia.com static site

This repository contains a static export workflow for the current WordPress site at
`https://luoguixia.com`.

## Recommended hosting

Use Cloudflare Pages for the first migration. The site is mostly a portfolio,
but the current WordPress install includes Avada forms and WooCommerce assets.
Cloudflare Pages gives the static hosting path plus a clean upgrade path for
forms via Pages Functions. GitHub Pages is fine for a fully static portfolio,
but it is less flexible if contact forms or small dynamic endpoints are needed.

## Export the current WordPress site

```bash
python3 scripts/export_static.py
```

The script reads the live Yoast sitemap, fetches the published same-domain
HTML pages, downloads same-domain CSS, JavaScript, images, and fonts, then
writes the deployable site to `public/`. By default it does not expand every
WordPress `srcset` image size; it keeps the direct `src` / lazy-load assets so
the Git repository stays deployable.

## Local preview

```bash
python3 -m http.server 4173 -d public
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

## Cloudflare Pages setup

1. Push this repository to GitHub.
2. In Cloudflare Pages, create a project from the Git repository.
3. Use no build command.
4. Set the output directory to `public`.
5. Preview the `*.pages.dev` deployment.
6. Add the custom domain `luoguixia.com`.
7. Before changing nameservers, copy all existing DNS records from SiteGround,
   especially email-related `MX`, `TXT`, `SPF`, `DKIM`, and `DMARC` records.
8. Change the registrar nameservers from SiteGround to Cloudflare after the
   preview site is verified.

## GitHub Pages alternative

GitHub Pages can deploy the same `public/` directory. Keep `public/CNAME` if
using the apex domain, enable Pages in repository settings, and point DNS to
GitHub Pages. This is best only if the site remains purely static.

## Static-site caveats

The exported site cannot run WordPress PHP, `/wp-admin`, WooCommerce cart,
checkout, account pages, comments, or Avada form submissions. For launch:

- The exported Avada contact form falls back to `mailto:luoguixia@gmail.com`
  through `public/static-form-mailto.js`. Replace it with a static form
  provider or Cloudflare Pages Function if inbox delivery without a local email
  client is required.
- Remove or replace WooCommerce checkout/account/cart if they are not actively
  used.
- Cart, checkout, account, WordPress API, and login URLs are redirected in
  `public/_redirects` so visitors do not land on broken dynamic pages.
- Keep the SiteGround WordPress install private or password-protected as the
  editing/source system until the new static workflow fully replaces it.
