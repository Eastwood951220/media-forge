CREATE TABLE crawl_task_tags (
    id UUID NOT NULL,
    owner_id UUID NOT NULL,
    name VARCHAR(50) NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITHOUT TIME ZONE,
    PRIMARY KEY (id),
    CONSTRAINT uq_crawl_task_tags_owner_name UNIQUE (owner_id, name),
    FOREIGN KEY(owner_id) REFERENCES users (id)
);

CREATE INDEX idx_crawl_task_tags_owner_name
    ON crawl_task_tags (owner_id, name);

CREATE INDEX ix_crawl_task_tags_owner_id
    ON crawl_task_tags (owner_id);

CREATE TABLE crawl_task_tag_links (
    task_id UUID NOT NULL,
    tag_id UUID NOT NULL,
    PRIMARY KEY (task_id, tag_id),
    CONSTRAINT uq_crawl_task_tag_links_task_tag UNIQUE (task_id, tag_id),
    FOREIGN KEY(task_id) REFERENCES crawl_tasks (id) ON DELETE CASCADE,
    FOREIGN KEY(tag_id) REFERENCES crawl_task_tags (id) ON DELETE CASCADE
);

CREATE INDEX idx_crawl_task_tag_links_task_id
    ON crawl_task_tag_links (task_id);

CREATE INDEX idx_crawl_task_tag_links_tag_id
    ON crawl_task_tag_links (tag_id);
