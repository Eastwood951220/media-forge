# Docker fnOS ARM64 Release Design

## Goal

Package Media Forge as a single Docker application image that runs on fnOS ARM64. The release must expose only one web address, serve the built frontend through the backend, and persist runtime state through one mounted `data` directory.

## Decisions

- Build one application image, not a Compose stack.
- Do not include PostgreSQL or Redis in the image.
- Do not run database migrations automatically on container startup.
- Expose only container port `18642`.
- Use `/app/data` as the only runtime volume.
- Provide Makefile targets for local architecture builds and fnOS ARM64 release packaging.
- `make docker-build-arm64` must automatically write an image tar file into `output/`.

## Runtime Architecture

The container runs FastAPI with Uvicorn:

```bash
uvicorn backend.app.main:app --host 0.0.0.0 --port 18642
```

FastAPI serves both the API and the frontend:

- `/api/*` remains owned by existing backend routers.
- `/api/events/stream` remains the realtime SSE endpoint.
- `/assets/*` and other Vite static assets are served from the copied frontend build.
- SPA routes such as `/`, `/login`, `/init`, `/crawler/tasks`, and `/content/movies` return `index.html`.

The current frontend already uses relative API URLs under `/api`, so it needs no deployment-specific API base URL for the single-port container.

## Frontend Build Integration

The Docker build uses multiple stages:

1. Node stage installs frontend dependencies and runs `npm run build`.
2. Python runtime stage installs `backend/requirements.txt`.
3. The runtime stage copies `backend/`, `shared/`, Alembic files, and the frontend `dist` output into the backend static directory.

The frontend build output is copied into this backend directory inside the image:

```text
backend/app/static/
```

The repository-level Makefile also provides a `frontend-build` target for local verification, but the Dockerfile remains self-contained so plain `docker build` is reproducible.

## Data Volume

The container uses:

```text
/app/data
```

as its only persistent runtime directory. The release sets:

```bash
APP_CONFIG_DIR=/app/data/configs
LOG_DIR=/app/data/logs
```

Runtime files are written under:

```text
/app/data/configs/database.conf
/app/data/configs/redis.conf
/app/data/configs/storage.conf
/app/data/logs/
```

The repository `data/` directory is runtime state, not release input. It must not be copied into the image or into the exported tar. The Docker build context excludes `data/`, `output/`, virtual environments, dependency directories, build output, caches, and local environment files through `.dockerignore`.

This prevents local runtime data from making fnOS packages stale, oversized, or environment-specific. fnOS users provide a fresh host directory and mount it to `/app/data`.

Example runtime command:

```bash
docker run -d \
  --name media-forge \
  -p 18642:18642 \
  -v /path/to/media-forge-data:/app/data \
  media-forge:latest
```

## Initialization Behavior

The image does not include PostgreSQL or Redis. Users configure external PostgreSQL and Redis through the existing `/init` page.

When the container starts without both `database.conf` and `redis.conf`, the backend keeps the current behavior: only initialization endpoints are usable, and the frontend routes users to `/init`.

When the user saves initialization settings, the current backend code performs the required bootstrap work:

- validates PostgreSQL connectivity;
- creates the target database if it does not exist;
- imports registered application models;
- creates the current application tables;
- repairs incompatible empty crawler task tables;
- seeds the default admin user `admin/admin123` if it does not exist;
- validates Redis connectivity;
- writes `database.conf` and `redis.conf`;
- reloads runtime configuration.

This means first-time Docker deployment can initialize the data needed by the current application through the UI. Future Alembic migration workflows remain explicit and are not run automatically at container startup.

## Makefile Design

The Makefile provides the release entry points:

```text
make frontend-build
make docker-build
make docker-build-arm64
make docker-save-arm64
make docker-run
make docker-stop
```

Expected behavior:

- `frontend-build`: install frontend dependencies and run `npm run build`.
- `docker-build`: build `media-forge:latest` for the host architecture.
- `docker-build-arm64`: build `media-forge:arm64` for `linux/arm64` and export `output/media-forge-linux-arm64.tar`.
- `docker-save-arm64`: save an existing ARM64 image to `output/media-forge-linux-arm64.tar`; this can be used by `docker-build-arm64` internally.
- `docker-run`: run the local image with `-p 18642:18642` and `-v ./data:/app/data`.
- `docker-stop`: stop and remove the local `media-forge` container if present.

The ARM64 target uses Docker Buildx. It should create `output/` before saving the tar file. The output tar contains the Docker image only, not the repository `data/` directory.

## Files To Add Or Modify

Expected implementation files:

- Add root `Dockerfile`.
- Add root `.dockerignore`.
- Add root `Makefile`.
- Modify `backend/app/main.py` to mount built frontend static files and SPA fallback routes.
- Add backend tests for API route precedence and SPA fallback behavior.
- Add or update a short deployment document that records the fnOS ARM64 tar output and `/app/data` mount requirement.

The implementation must preserve current API paths and frontend route behavior.

## Error Handling

- If frontend static files are missing during local backend development, backend API startup should still work. Static serving should be conditional on the build directory existing.
- API routes must take precedence over SPA fallback so missing or invalid `/api/*` requests return API-style 404 responses, not `index.html`.
- If `/app/data` is not writable, initialization or logging should fail visibly through existing backend errors rather than silently using an in-image fallback path.

## Verification

Implementation verification should include:

- `cd frontend && npm run build`
- backend tests for static serving and init API precedence
- `docker build` for the local image
- `make docker-build-arm64` producing `output/media-forge-linux-arm64.tar`
- container smoke test for `GET /`
- container smoke test for `GET /api/init/config`
- SPA refresh smoke test for `/login`, `/init`, and one authenticated app route path returning HTML
- confirmation that `data/` and `output/` are not copied into the image build context

## Out Of Scope

- Bundling PostgreSQL or Redis.
- Adding `docker-compose.yml` as the primary deployment path.
- Automatically running `alembic upgrade head` on startup.
- Changing frontend API paths.
- Changing authentication, initialization, crawler, storage, or media processing behavior.
