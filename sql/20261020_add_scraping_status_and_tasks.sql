ALTER TABLE movies
    ADD COLUMN scraping_status VARCHAR(20),
    ADD COLUMN scraping_folder TEXT,
    ADD COLUMN scraping_checked_at TIMESTAMP WITHOUT TIME ZONE;

CREATE TABLE scraping_tasks (
    id UUID NOT NULL,
    status VARCHAR(30) NOT NULL,
    total_count INTEGER NOT NULL,
    success_count INTEGER NOT NULL,
    failed_count INTEGER NOT NULL,
    skipped_count INTEGER NOT NULL,
    cancel_requested BOOLEAN NOT NULL,
    config_snapshot JSONB NOT NULL,
    created_by UUID NOT NULL,
    queued_at TIMESTAMP WITHOUT TIME ZONE,
    started_at TIMESTAMP WITHOUT TIME ZONE,
    finished_at TIMESTAMP WITHOUT TIME ZONE,
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE,
    PRIMARY KEY (id),
    FOREIGN KEY (created_by) REFERENCES users (id)
);

CREATE INDEX ix_scraping_tasks_status ON scraping_tasks (status);
CREATE INDEX ix_scraping_tasks_created_by ON scraping_tasks (created_by);
CREATE INDEX idx_scraping_tasks_status_created ON scraping_tasks (status, created_at);
CREATE INDEX idx_scraping_tasks_created_by_status ON scraping_tasks (created_by, status);

CREATE TABLE scraping_task_items (
    id UUID NOT NULL,
    task_id UUID NOT NULL,
    movie_id UUID NOT NULL,
    movie_code VARCHAR(100) NOT NULL,
    movie_title TEXT NOT NULL,
    status VARCHAR(30) NOT NULL,
    source VARCHAR(30) NOT NULL,
    folder TEXT NOT NULL,
    duration_ms INTEGER NOT NULL,
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE,
    PRIMARY KEY (id),
    FOREIGN KEY (task_id) REFERENCES scraping_tasks (id) ON DELETE CASCADE,
    FOREIGN KEY (movie_id) REFERENCES movies (id) ON DELETE CASCADE
);

CREATE INDEX ix_scraping_task_items_task_id ON scraping_task_items (task_id);
CREATE INDEX ix_scraping_task_items_status ON scraping_task_items (status);
CREATE INDEX idx_scraping_items_task_status ON scraping_task_items (task_id, status);
CREATE INDEX idx_scraping_items_created ON scraping_task_items (created_at);
