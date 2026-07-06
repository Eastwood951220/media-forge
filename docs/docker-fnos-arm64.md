# Docker fnOS ARM64 Deployment

Media Forge is packaged as a single application image for fnOS ARM64. The image serves the React frontend and FastAPI backend on one port.

## Build ARM64 Package

Run from the repository root:

```bash
make docker-build-arm64
```

The build writes:

```text
output/media-forge-linux-arm64.tar
```

Upload this tar file to fnOS or load it on an ARM64 Docker host:

```bash
docker load -i output/media-forge-linux-arm64.tar
```

## Runtime Requirements

The image does not include PostgreSQL or Redis. Provide external PostgreSQL and Redis services that the container can reach from fnOS.

Only one host directory is required for persistence:

```text
/path/to/media-forge-data
```

It is mounted to:

```text
/app/data
```

Media Forge writes runtime files under:

```text
/app/data/configs/database.conf
/app/data/configs/redis.conf
/app/data/configs/storage.conf
/app/data/logs/
```

The repository `data/` directory is not packaged into the Docker image or ARM64 tar. The `output/` directory stores release tar files only and is not copied into the image.

## Run Container

```bash
docker run -d \
  --name media-forge \
  -p 18642:18642 \
  -v /path/to/media-forge-data:/app/data \
  media-forge:arm64
```

Open:

```text
http://<fnos-host>:18642
```

## First-Time Initialization

On first startup, if `database.conf` and `redis.conf` do not exist, Media Forge routes the browser to `/init`.

When initialization settings are saved, the backend:

- validates PostgreSQL;
- creates the target database when missing;
- creates application tables;
- repairs incompatible empty crawler task tables;
- creates the default admin user `admin/admin123` when missing;
- validates Redis;
- writes runtime config under `/app/data/configs`;
- reloads runtime configuration.

The container does not automatically run Alembic migrations on startup. Future schema migrations must be run explicitly.

## Local Smoke Check

```bash
curl -i http://127.0.0.1:18642/
curl -i http://127.0.0.1:18642/api/init/config
curl -i http://127.0.0.1:18642/login
```
