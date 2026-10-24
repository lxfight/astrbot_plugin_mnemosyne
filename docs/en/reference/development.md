# Development and Documentation Deployment

This page is for contributors changing plugin code or documentation. Python tests and the VitePress build use separate toolchains.

## Requirements

- Python 3.11 or the version required by the current AstrBot checkout
- Node.js 20 or newer
- An AstrBot development environment with usable LLM and Embedding providers

## Install Dependencies

```bash
pip install -r requirements.txt pytest pytest-asyncio ruff
npm ci
```

## Run Tests

```bash
pytest tests -q
ruff check --select E,F --ignore E501 --exclude tests .
```

Some historical diagnostic scripts under `tests/` are not part of the current Ruff scope. New tests should remain clean for the E/F rules.

## Build the Documentation

```bash
npm run docs:dev
npm run docs:build
npm run docs:preview
```

The development server listens on `0.0.0.0`. Production output is written to `docs/.vitepress/dist`.

When deploying to a GitHub Pages project path, set the site base path:

```powershell
$env:DOCS_BASE='/astrbot_plugin_mnemosyne/'
npm run docs:build
```

```bash
DOCS_BASE=/astrbot_plugin_mnemosyne/ npm run docs:build
```

## Documentation Layout

| Path | Contents |
| --- | --- |
| `docs/guide/` | Chinese installation, configuration, administration, and performance guides. |
| `docs/reference/` | Chinese architecture, development, and troubleshooting references. |
| `docs/en/` | Matching English pages. |
| `docs/.vitepress/` | Navigation, site configuration, theme, and build output. |
| `docs/public/` | Static assets published without Markdown processing. |

When adding a user-facing page, update both language trees and the navigation entries in `.vitepress/config.ts`.

## GitHub Pages

`.github/workflows/docs.yml` runs after documentation or site configuration changes land on `main`:

1. Install locked dependencies with `npm ci`.
2. Build VitePress with the base path reported by the Pages configuration.
3. Upload the static artifact and deploy it to GitHub Pages.

Before the first deployment, set **Settings → Pages → Source** to **GitHub Actions**. The public site is <https://lxfight.github.io/astrbot_plugin_mnemosyne/>.

The documentation build also runs in CI, so broken navigation, links, or Markdown processing fail before a pull request is merged.
