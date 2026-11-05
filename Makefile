APP_NAME ?= media-forge
IMAGE ?= $(APP_NAME)
IMAGE_TAG ?= latest
ARM64_TAG ?= arm64
AMD64_TAG ?= amd64
NODE_BASE_IMAGE ?= node:22-bookworm-slim
PYTHON_BASE_IMAGE ?= python:3.12-slim
APT_MIRROR ?= https://mirrors.tuna.tsinghua.edu.cn
PLAYWRIGHT_DOWNLOAD_HOST ?= https://npmmirror.com/mirrors/playwright
PIP_INDEX_URL ?= https://pypi.tuna.tsinghua.edu.cn/simple
CONTAINER_NAME ?= media-forge
HOST_PORT ?= 18642
CONTAINER_PORT ?= 18642
DATA_DIR ?= $(CURDIR)/data
OUTPUT_DIR ?= $(CURDIR)/output
ARM64_TAR ?= $(OUTPUT_DIR)/media-forge-linux-arm64.tar
AMD64_TAR ?= $(OUTPUT_DIR)/media-forge-linux-amd64.tar
EXTENSION_ZIP ?= $(OUTPUT_DIR)/media-forge-chrome-extension.zip
DOCKER_BUILD_ARGS ?= --build-arg NODE_BASE_IMAGE=$(NODE_BASE_IMAGE) --build-arg PYTHON_BASE_IMAGE=$(PYTHON_BASE_IMAGE) --build-arg APT_MIRROR=$(APT_MIRROR) --build-arg PLAYWRIGHT_DOWNLOAD_HOST=$(PLAYWRIGHT_DOWNLOAD_HOST) --build-arg PIP_INDEX_URL=$(PIP_INDEX_URL)

.PHONY: chrome-extension-build chrome-extension-package frontend-build docker-build docker-build-arm64 docker-build-amd64 docker-save-arm64 docker-save-amd64 docker-run docker-stop output-dir

frontend-build:
	cd frontend && CI=true pnpm install --frozen-lockfile && pnpm run build

chrome-extension-build:
	cd chrome-extension && CI=true pnpm install --frozen-lockfile && pnpm typecheck && pnpm build && node scripts/verify-agent-extension.mjs

chrome-extension-package: chrome-extension-build output-dir
	mkdir -p "$(dir $(abspath $(EXTENSION_ZIP)))"
	rm -f "$(abspath $(EXTENSION_ZIP))"
	cd chrome-extension/dist && zip -q -r "$(abspath $(EXTENSION_ZIP))" . -x '*.DS_Store'
	@echo "Chrome extension zip written to $(abspath $(EXTENSION_ZIP))"

docker-build:
	docker buildx build --platform linux/amd64 --load $(DOCKER_BUILD_ARGS) -t $(IMAGE):$(IMAGE_TAG) .

output-dir:
	mkdir -p $(OUTPUT_DIR)

docker-build-arm64: output-dir
	docker buildx build --platform linux/arm64 --load $(DOCKER_BUILD_ARGS) -t $(IMAGE):$(ARM64_TAG) .
	docker save $(IMAGE):$(ARM64_TAG) -o $(ARM64_TAR)
	@echo "ARM64 image tar written to $(ARM64_TAR)"

docker-build-amd64: output-dir
	docker buildx build --platform linux/amd64 --load $(DOCKER_BUILD_ARGS) -t $(IMAGE):$(AMD64_TAG) .
	docker save $(IMAGE):$(AMD64_TAG) -o $(AMD64_TAR)
	@echo "AMD64 image tar written to $(AMD64_TAR)"

docker-save-arm64: output-dir
	docker save $(IMAGE):$(ARM64_TAG) -o $(ARM64_TAR)
	@echo "ARM64 image tar written to $(ARM64_TAR)"

docker-save-amd64: output-dir
	docker save $(IMAGE):$(AMD64_TAG) -o $(AMD64_TAR)
	@echo "AMD64 image tar written to $(AMD64_TAR)"

docker-run: docker-build
	mkdir -p $(DATA_DIR)
	docker rm -f $(CONTAINER_NAME) >/dev/null 2>&1 || true
	docker run -d \
		--name $(CONTAINER_NAME) \
		-p $(HOST_PORT):$(CONTAINER_PORT) \
		-v $(DATA_DIR):/app/data \
		$(IMAGE):$(IMAGE_TAG)

docker-stop:
	docker rm -f $(CONTAINER_NAME) >/dev/null 2>&1 || true
