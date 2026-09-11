# Frontend service

The frontend is a React and TypeScript application built with Vite. It uses TanStack Router, TanStack Query, and Tailwind CSS. Dependencies and commands are defined in [package.json](package.json); Vite plugins and the `@` → `src` alias are configured in [vite.config.ts](vite.config.ts).

## Requirements

- **Bun** for the repository's workspace commands and Playwright scripts. The [Playwright workflow](../.github/workflows/playwright.yml) uses Bun **1.3.12**; the frontend [Dockerfile](Dockerfile) uses `oven/bun:1`.
- **Docker with Compose** if running the backend dependencies or the containerized frontend locally.
- A configured, reachable backend for login and API-backed features. Backend setup is documented in [backend/README.md](../backend/README.md).
- **uv** and the backend Python dependencies if regenerating the API client with the repository script.

## Local development

Run these commands from the **repository root**:

```bash
bun install
```

Configure the repository-root `.env` for the backend and Compose. If it does not exist, copy [.env.example](../.env.example) to `.env` and fill in the backend settings. This is separate from the frontend environment described below.

Start the backend and its dependencies:

```bash
docker compose up -d --build --wait backend
```

The [Compose configuration](../compose.yml) starts PostgreSQL, Weaviate, and the prestart service as backend dependencies. The [local override](../compose.override.yml) exposes the backend at `http://localhost:8000`.

Set the following entry in `frontend/.env`:

```dotenv
VITE_API_URL=http://localhost:8000
```

Then start the frontend from the repository root:

```bash
bun run dev
```

The [root package script](../package.json) forwards this to the frontend workspace's `vite` command. Open `http://localhost:5173` (also the URL expected by [Playwright](playwright.config.ts)); check Vite's terminal output for the actual address. You can alternatively run `bun run dev` from `frontend/`.

Keep port 5173 free: the Docker frontend also publishes that port. If it is already running, stop it before starting Vite:

```bash
docker compose stop frontend
```

## Configuration

### API connection

| Setting | Where to configure it | Purpose |
| --- | --- | --- |
| `VITE_API_URL` | `frontend/.env`, the environment running Vite, or the Docker build argument | Backend base URL used by the browser, for example `http://localhost:8000`. |
| `FRONTEND_HOST` | Backend/root `.env` | Frontend origin; defaults to `http://localhost:5173` in backend settings and is included in the backend's allowed CORS origins. |
| `BACKEND_CORS_ORIGINS` | Backend/root `.env` | Additional origins permitted by the backend's CORS middleware. |

[src/main.tsx](src/main.tsx) assigns `import.meta.env.VITE_API_URL` directly to `OpenAPI.BASE`; there is no application-level fallback. Use the backend origin without `/api/v1`, because the [generated client](src/client/sdk.gen.ts) already includes that prefix in its endpoint paths. The URL must be reachable from the user's browser.

For a remote backend, replace the local value, for example:

```dotenv
VITE_API_URL=https://api.example.com
```

The backend must allow the frontend's actual origin, including its scheme and port. [Backend settings](../backend/app/core/config.py) combine `BACKEND_CORS_ORIGINS` with `FRONTEND_HOST`, and [backend/app/main.py](../backend/app/main.py) installs the CORS middleware. Vite has no API proxy configured in [vite.config.ts](vite.config.ts).

Restart Vite after changing its environment. For a built frontend, rebuild the assets/image after changing `VITE_API_URL`: the [Dockerfile](Dockerfile) supplies it during `bun run build`, and the final Nginx container only contains static assets. Setting a new environment variable on an already-built Nginx container does not reconfigure the client.

### Compose build settings

[compose.yml](../compose.yml) sets the frontend image to `${DOCKER_IMAGE_FRONTEND}:${TAG-latest}`, builds with `VITE_API_URL=https://api.${DOMAIN}`, and routes the frontend through Traefik at `dashboard.${DOMAIN}`. `DOCKER_IMAGE_FRONTEND`, `DOMAIN`, and `STACK_NAME` are required by that configuration.

For local Compose runs, [compose.override.yml](../compose.override.yml) overrides the API build URL to `http://localhost:8000` and maps host port **5173** to Nginx port **80**. Compose also passes `NODE_ENV`, but the frontend Dockerfile only declares `ARG VITE_API_URL`; its build command is always `bun run build`.

## Build and serve

### Local build preview

From `frontend/`:

```bash
bun run build
bun run preview
```

The build script runs `tsc -p tsconfig.build.json && vite build`; [tsconfig.build.json](tsconfig.build.json) excludes Playwright tests. The compiled output is `frontend/dist/`, the directory copied by the Dockerfile. `preview` runs `vite preview`; use the address printed in the terminal.

### Docker frontend

With the root `.env` configured, run from the **repository root**:

```bash
docker compose up -d --build --wait backend frontend
```

Open `http://localhost:5173`. This serves the compiled application through Nginx. Re-run the build/start command after frontend source or API URL changes; the frontend Compose service has no source watch configuration.

The [Dockerfile](Dockerfile) builds from the repository root so it can copy the workspace manifest and `bun.lock`. Its final `nginx:1` stage serves `/usr/share/nginx/html`. [nginx.conf](nginx.conf) falls back to `index.html` for frontend routes; [nginx-backend-not-found.conf](nginx-backend-not-found.conf) explicitly returns 404 for `/api`, `/docs`, and `/redoc`. API requests must go to the separately configured backend.

## Available commands

Run these from `frontend/`; definitions are in [package.json](package.json).

| Command | Behavior |
| --- | --- |
| `bun run dev` | Start Vite. |
| `bun run build` | Type-check the application and build static assets. |
| `bun run preview` | Preview the built assets with Vite. |
| `bun run lint` | Run Biome with `--write --unsafe`; this command modifies files. |
| `bun run generate-client` | Generate the API client from `frontend/openapi.json`. |
| `bun run test` | Run Playwright tests. |
| `bun run test:ui` | Run Playwright in UI mode. |

The root workspace forwards `dev`, `lint`, `test`, and `test:ui` to the frontend.

## Generate the API client

After backend API schema changes, run from the **repository root**, with Bun dependencies and the backend uv environment configured:

```bash
bash scripts/generate-client.sh
```

The [script](../scripts/generate-client.sh) imports the backend application using `uv run`, writes its OpenAPI schema to `frontend/openapi.json`, generates the client, and runs the root lint command. It does not require a running backend HTTP server, but importing the application requires valid backend configuration. Review the resulting schema, client, and lint changes.

Alternatively, with the local backend running, run from `frontend/`:

```bash
curl --fail http://localhost:8000/api/v1/openapi.json -o openapi.json
bun run generate-client
```

The schema URL comes from [backend/app/main.py](../backend/app/main.py). [openapi-ts.config.ts](openapi-ts.config.ts) reads `./openapi.json` and writes the Axios-based client to `./src/client`.

## End-to-end tests

[playwright.config.ts](playwright.config.ts) runs tests in `tests/`, starts `bun run dev` automatically, and targets `http://localhost:5173`. Outside CI it can reuse an existing server. The enabled browser project is Chromium, with an authentication setup dependency.

For local tests, configure:

- `VITE_API_URL=http://localhost:8000` and `MAILCATCHER_HOST=http://localhost:1080` in `frontend/.env`. Playwright loads dotenv, the [API helper](tests/utils/privateApi.ts) reads `VITE_API_URL`, and the [email helper](tests/utils/mailcatcher.ts) reads `MAILCATCHER_HOST`.
- `FIRST_SUPERUSER` and `FIRST_SUPERUSER_PASSWORD` in the root `.env`, matching the backend account. [tests/config.ts](tests/config.ts) requires both, and [auth.setup.ts](tests/auth.setup.ts) uses them to log in.

Start the supporting services from the repository root:

```bash
docker compose up -d --build --wait backend mailcatcher
```

From `frontend/`, with the Playwright Chromium browser installed:

```bash
bun run test
# Or use the interactive runner:
bun run test:ui
```

For the container-based runner used by [CI](../.github/workflows/playwright.yml), run from the repository root:

```bash
docker compose build playwright
docker compose run --rm playwright bunx playwright test
```

The [Playwright image](Dockerfile.playwright) provides the browser environment. The Compose service sets `VITE_API_URL=http://backend:8000` and `MAILCATCHER_HOST=http://mailcatcher:1080` for access inside Docker. CI enables two retries, one worker, and blob reports; local runs use HTML reports.

## Source layout

- `src/main.tsx`: application initialization, API base URL, and authentication token wiring.
- `src/routes/`: TanStack Router pages; the Vite router plugin generates route integration.
- `src/components/`: shared and feature UI components.
- `src/hooks/`: React hooks.
- `src/client/`: generated API client.
- `src/assets/`: application assets.
- `tests/`: Playwright tests and helpers.
