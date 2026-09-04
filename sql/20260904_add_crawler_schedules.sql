CREATE TABLE crawler_schedules (
    id UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE,
    owner_id UUID NOT NULL,
    name VARCHAR(200) NOT NULL,
    enabled BOOLEAN NOT NULL,
    schedule_type VARCHAR(20) NOT NULL,
    time_of_day VARCHAR(5) NOT NULL,
    weekdays JSONB NOT NULL,
    auto_storage_enabled BOOLEAN NOT NULL,
    storage_mode VARCHAR(30) NOT NULL,
    selected_storage_location VARCHAR(500),
    last_triggered_at TIMESTAMP WITHOUT TIME ZONE,
    next_run_at TIMESTAMP WITHOUT TIME ZONE,
    PRIMARY KEY (id),
    CONSTRAINT uq_crawler_schedules_owner_name UNIQUE (owner_id, name),
    CONSTRAINT fk_crawler_schedules_owner_id_users FOREIGN KEY (owner_id) REFERENCES users (id)
);

CREATE INDEX idx_crawler_schedules_owner_enabled
    ON crawler_schedules (owner_id, enabled);

CREATE INDEX idx_crawler_schedules_next_run
    ON crawler_schedules (enabled, next_run_at);

CREATE INDEX ix_crawler_schedules_owner_id
    ON crawler_schedules (owner_id);

CREATE TABLE crawler_schedule_tasks (
    schedule_id UUID NOT NULL,
    task_id UUID NOT NULL,
    PRIMARY KEY (schedule_id, task_id),
    CONSTRAINT uq_crawler_schedule_tasks_schedule_task UNIQUE (schedule_id, task_id),
    CONSTRAINT fk_crawler_schedule_tasks_schedule_id_crawler_schedules
        FOREIGN KEY (schedule_id) REFERENCES crawler_schedules (id) ON DELETE CASCADE,
    CONSTRAINT fk_crawler_schedule_tasks_task_id_crawl_tasks
        FOREIGN KEY (task_id) REFERENCES crawl_tasks (id) ON DELETE CASCADE
);

CREATE INDEX idx_crawler_schedule_tasks_schedule_id
    ON crawler_schedule_tasks (schedule_id);

CREATE INDEX idx_crawler_schedule_tasks_task_id
    ON crawler_schedule_tasks (task_id);

CREATE TABLE crawler_schedule_runs (
    id UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE,
    schedule_id UUID NOT NULL,
    owner_id UUID NOT NULL,
    status VARCHAR(30) NOT NULL,
    triggered_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    finished_at TIMESTAMP WITHOUT TIME ZONE,
    trigger_type VARCHAR(30) NOT NULL,
    result JSONB NOT NULL,
    storage_status VARCHAR(30) NOT NULL,
    storage_task_id UUID,
    storage_error TEXT,
    PRIMARY KEY (id),
    CONSTRAINT fk_crawler_schedule_runs_schedule_id_crawler_schedules
        FOREIGN KEY (schedule_id) REFERENCES crawler_schedules (id) ON DELETE CASCADE,
    CONSTRAINT fk_crawler_schedule_runs_owner_id_users
        FOREIGN KEY (owner_id) REFERENCES users (id),
    CONSTRAINT fk_crawler_schedule_runs_storage_task_id_storage_main_tasks
        FOREIGN KEY (storage_task_id) REFERENCES storage_main_tasks (id) ON DELETE SET NULL
);

CREATE INDEX idx_crawler_schedule_runs_schedule_triggered
    ON crawler_schedule_runs (schedule_id, triggered_at);

CREATE INDEX idx_crawler_schedule_runs_owner_status
    ON crawler_schedule_runs (owner_id, status);

CREATE INDEX ix_crawler_schedule_runs_schedule_id
    ON crawler_schedule_runs (schedule_id);

CREATE INDEX ix_crawler_schedule_runs_owner_id
    ON crawler_schedule_runs (owner_id);

CREATE TABLE crawler_schedule_run_crawl_runs (
    schedule_run_id UUID NOT NULL,
    crawl_run_id UUID NOT NULL,
    task_id UUID,
    PRIMARY KEY (schedule_run_id, crawl_run_id),
    CONSTRAINT uq_crawler_schedule_run_crawl_run UNIQUE (schedule_run_id, crawl_run_id),
    FOREIGN KEY (schedule_run_id) REFERENCES crawler_schedule_runs (id) ON DELETE CASCADE,
    CONSTRAINT fk_crawler_schedule_run_crawl_runs_crawl_run_id_crawl_runs
        FOREIGN KEY (crawl_run_id) REFERENCES crawl_runs (id) ON DELETE CASCADE,
    CONSTRAINT fk_crawler_schedule_run_crawl_runs_task_id_crawl_tasks
        FOREIGN KEY (task_id) REFERENCES crawl_tasks (id) ON DELETE SET NULL
);

CREATE INDEX idx_crawler_schedule_run_crawl_runs_schedule_run
    ON crawler_schedule_run_crawl_runs (schedule_run_id);

CREATE INDEX idx_crawler_schedule_run_crawl_runs_crawl_run
    ON crawler_schedule_run_crawl_runs (crawl_run_id);

ALTER TABLE crawl_runs
    ADD COLUMN trigger_source VARCHAR(30);

ALTER TABLE crawl_runs
    ADD COLUMN schedule_id UUID;

ALTER TABLE crawl_runs
    ADD COLUMN schedule_run_id UUID;

ALTER TABLE crawl_runs
    ADD CONSTRAINT fk_crawl_runs_schedule_id_crawler_schedules
        FOREIGN KEY (schedule_id) REFERENCES crawler_schedules (id) ON DELETE SET NULL;

ALTER TABLE crawl_runs
    ADD CONSTRAINT fk_crawl_runs_schedule_run_id_crawler_schedule_runs
        FOREIGN KEY (schedule_run_id) REFERENCES crawler_schedule_runs (id) ON DELETE SET NULL;

CREATE INDEX ix_crawl_runs_trigger_source
    ON crawl_runs (trigger_source);

CREATE INDEX ix_crawl_runs_schedule_id
    ON crawl_runs (schedule_id);

CREATE INDEX ix_crawl_runs_schedule_run_id
    ON crawl_runs (schedule_run_id);

ALTER TABLE crawl_run_detail_tasks
    ADD COLUMN movie_id UUID;

ALTER TABLE crawl_run_detail_tasks
    ADD CONSTRAINT fk_crawl_run_detail_tasks_movie_id_movies
        FOREIGN KEY (movie_id) REFERENCES movies (id) ON DELETE SET NULL;

CREATE INDEX ix_crawl_run_detail_tasks_movie_id
    ON crawl_run_detail_tasks (movie_id);
