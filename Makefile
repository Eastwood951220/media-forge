APP_NAME ?= media-forge
IMAGE ?= $(APP_NAME)
IMAGE_TAG ?= latest
ARM64_TAG ?= arm64
AMD64_TAG ?= amd64
CONTAINER_NAME ?= media-forge
HOST_PORT ?= 18642
CONTAINER_PORT ?= 18642
DATA_DIR ?= $(CURDIR)/data
OUTPUT_DIR ?= $(CURDIR)/output
ARM64_TAR ?= $(OUTPUT_DIR)/media-forge-linux-arm64.tar
AMD64_TAR ?= $(OUTPUT_DIR)/media-forge-linux-amd64.tar

.PHONY: frontend-build docker-build docker-build-arm64 docker-build-amd64 docker-save-arm64 docker-save-amd64 docker-run docker-stop output-dir

frontend-build:
	cd frontend && npm ci && npm run build

docker-build:
	docker buildx build --platform linux/amd64 --load -t $(IMAGE):$(IMAGE_TAG) .

output-dir:
	mkdir -p $(OUTPUT_DIR)

docker-build-arm64: output-dir
	docker buildx build --platform linux/arm64 --load -t $(IMAGE):$(ARM64_TAG) .
	docker save $(IMAGE):$(ARM64_TAG) -o $(ARM64_TAR)
	@echo "ARM64 image tar written to $(ARM64_TAR)"

docker-build-amd64: output-dir
	docker buildx build --platform linux/amd64 --load -t $(IMAGE):$(AMD64_TAG) .
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
