-- Create actress tag dictionary and links.
-- Copy existing actress_profiles.tags.
-- Copy matching task tags through actress_profiles.source_task_ids.
-- Drop old task tag tables and actress_profiles.tags.

CREATE TABLE actress_tags (
    id UUID NOT NULL,
    owner_id UUID NOT NULL,
    name VARCHAR(50) NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now(),
    updated_at TIMESTAMP WITHOUT TIME ZONE,
    PRIMARY KEY (id),
    CONSTRAINT uq_actress_tags_owner_name UNIQUE (owner_id, name),
    FOREIGN KEY(owner_id) REFERENCES users (id)
);

CREATE INDEX idx_actress_tags_owner_name
    ON actress_tags (owner_id, name);

CREATE INDEX ix_actress_tags_owner_id
    ON actress_tags (owner_id);

CREATE TABLE actress_tag_links (
    actress_profile_id UUID NOT NULL,
    tag_id UUID NOT NULL,
    PRIMARY KEY (actress_profile_id, tag_id),
    FOREIGN KEY(actress_profile_id) REFERENCES actress_profiles (id) ON DELETE CASCADE,
    FOREIGN KEY(tag_id) REFERENCES actress_tags (id) ON DELETE CASCADE
);

CREATE INDEX idx_actress_tag_links_profile_id
    ON actress_tag_links (actress_profile_id);

CREATE INDEX idx_actress_tag_links_tag_id
    ON actress_tag_links (tag_id);

-- Copy existing actress_profiles.tags array values into dictionary rows for
-- every owner that owns a crawler task or task tag.
INSERT INTO actress_tags (id, owner_id, name, created_at)
SELECT gen_random_uuid(), owners.owner_id, trimmed.name, now()
FROM (
    SELECT DISTINCT ct.owner_id
    FROM crawl_tasks ct
    UNION
    SELECT DISTINCT ctt.owner_id
    FROM crawl_task_tags ctt
) AS owners
CROSS JOIN LATERAL (
    SELECT DISTINCT btrim(tag_value) AS name
    FROM actress_profiles ap
    CROSS JOIN LATERAL unnest(ap.tags) AS tag_value
    WHERE btrim(tag_value) <> ''
) AS trimmed
ON CONFLICT (owner_id, name) DO NOTHING;

-- Copy existing task tag names into the actress tag dictionary.
INSERT INTO actress_tags (id, owner_id, name, created_at)
SELECT gen_random_uuid(), ctt.owner_id, ctt.name, now()
FROM crawl_task_tags ctt
WHERE btrim(ctt.name) <> ''
ON CONFLICT (owner_id, name) DO NOTHING;

-- Link actress_profiles.tags values through the owner of the source task.
INSERT INTO actress_tag_links (actress_profile_id, tag_id)
SELECT DISTINCT ap.id, at.id
FROM actress_profiles ap
JOIN crawl_tasks ct ON ct.id = ANY(ap.source_task_ids)
CROSS JOIN LATERAL unnest(ap.tags) AS tag_value
JOIN actress_tags at
    ON at.owner_id = ct.owner_id
   AND at.name = btrim(tag_value)
WHERE btrim(tag_value) <> ''
ON CONFLICT DO NOTHING;

-- Copy task tag links to actresses whose source_task_ids contain the tagged task.
INSERT INTO actress_tag_links (actress_profile_id, tag_id)
SELECT DISTINCT ap.id, at.id
FROM crawl_task_tag_links ctl
JOIN crawl_task_tags ctt ON ctt.id = ctl.tag_id
JOIN crawl_tasks ct ON ct.id = ctl.task_id
JOIN actress_profiles ap ON ctl.task_id = ANY(ap.source_task_ids)
JOIN actress_tags at ON at.owner_id = ct.owner_id AND at.name = ctt.name
ON CONFLICT DO NOTHING;

DROP INDEX idx_actress_profiles_tags_gin;

ALTER TABLE actress_profiles
    DROP COLUMN tags;

DROP INDEX idx_crawl_task_tag_links_tag_id;

DROP INDEX idx_crawl_task_tag_links_task_id;

DROP TABLE crawl_task_tag_links;

DROP INDEX ix_crawl_task_tags_owner_id;

DROP INDEX idx_crawl_task_tags_owner_name;

DROP TABLE crawl_task_tags;
