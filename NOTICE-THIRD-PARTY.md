# Third-party notices

Runtime dependencies shipped in the images, with the licence each declares in its package metadata.
Generated 2026-10-01 from `uv export --no-dev` (backend) and `pnpm licenses list --prod` (web).
Development tools (pytest, ruff, mypy, Vite, Vitest, Playwright) are not shipped and are not listed.

Obligations to note:

- psycopg and psycopg-binary are LGPL-3.0-only. They are used unmodified as a dynamically loaded library; a
  changed copy would have to be published under the LGPL.
- certifi is MPL-2.0, used unmodified; changes to its files would have to be published.
- IBM Plex fonts are OFL-1.1: they may be bundled and served, not sold on their own.

## Backend (Python)

| Package | Version | Licence |
| --- | --- | --- |
| alembic | 1.20.0 | MIT |
| annotated-doc | 0.0.5 | MIT |
| annotated-types | 0.8.0 | MIT |
| anyio | 4.15.1 | MIT |
| attrs | 26.1.0 | MIT |
| certifi | 2026.7.22 | Mozilla Public License 2.0 (MPL 2.0) |
| cffi | 2.1.1 | MIT-0 |
| click | 8.5.0 | BSD-3-Clause |
| cryptography | 50.0.1 | Apache-2.0 OR BSD-3-Clause |
| fastapi | 0.142.2 | MIT |
| h11 | 0.16.0 | MIT License |
| httpcore | 1.0.9 | BSD-3-Clause |
| httpcore2 | 2.13.1 | BSD-3-Clause |
| httpx | 0.28.1 | BSD License |
| httpx2 | 2.13.1 | BSD-3-Clause |
| idna | 3.20 | BSD-3-Clause |
| jsonschema | 4.26.0 | MIT |
| jsonschema-specifications | 2025.9.1 | MIT |
| mako | 1.4.3 | MIT |
| markupsafe | 3.0.3 | BSD-3-Clause |
| mcp | 2.2.0 | MIT License |
| mcp-types | 2.2.0 | MIT License |
| opentelemetry-api | 1.45.0 | Apache-2.0 |
| psycopg | 3.3.6 | LGPL-3.0-only |
| psycopg-binary | 3.3.6 | LGPL-3.0-only |
| pycparser | 3.0 | BSD-3-Clause |
| pydantic | 2.13.5 | MIT |
| pydantic-core | 2.46.5 | MIT |
| pydantic-settings | 2.15.0 | MIT |
| pyjwt | 2.15.1 | MIT |
| python-dotenv | 1.2.3 | BSD-3-Clause |
| python-multipart | 0.0.32 | Apache-2.0 |
| pyyaml | 6.0.3 | MIT License |
| referencing | 0.37.0 | MIT |
| rpds-py | 2026.6.3 | MIT |
| sqlalchemy | 2.1.1 | MIT |
| sse-starlette | 3.5.0 | BSD-3-Clause |
| starlette | 1.7.0 | BSD-3-Clause |
| truststore | 0.10.4 | MIT |
| typing-extensions | 4.16.0 | PSF-2.0 |
| typing-inspection | 0.4.4 | MIT |
| uvicorn | 0.54.0 | BSD-3-Clause |

Platform-only entries (pywin32, tzdata, httpx2-jsfetch) apply to other platforms and are not installed in the Linux image.

## Web console (JavaScript)

| Package | Licence |
| --- | --- |
| @fontsource/ibm-plex-mono 5.3.0 | OFL-1.1 |
| @fontsource/ibm-plex-sans 5.3.0 | OFL-1.1 |
| @fontsource/ibm-plex-sans-condensed 5.3.0 | OFL-1.1 |
| @tanstack/query-core 5.104.0 | MIT |
| @tanstack/react-query 5.104.0 | MIT |
| react 19.3.0 | MIT |
| react-dom 19.3.0 | MIT |
| scheduler 0.28.0 | MIT |
| zod 3.25.76 | MIT |
