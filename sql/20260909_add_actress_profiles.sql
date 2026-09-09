CREATE TABLE actress_profiles (
    id UUID NOT NULL,
    display_name TEXT NOT NULL,
    reading TEXT NOT NULL,
    aliases TEXT[] NOT NULL,
    canonical_names TEXT[] NOT NULL,
    source_url TEXT NOT NULL,
    source_site TEXT NOT NULL,
    source_task_ids UUID[] NOT NULL,
    source_task_url_ids UUID[] NOT NULL,
    image_url TEXT NOT NULL,
    debut_date DATE,
    birth_date DATE,
    height_cm INTEGER,
    bust_cm INTEGER,
    waist_cm INTEGER,
    hip_cm INTEGER,
    cup TEXT NOT NULL,
    birthplace TEXT NOT NULL,
    blood_type TEXT NOT NULL,
    hobbies TEXT NOT NULL,
    biography TEXT NOT NULL,
    exclusive_maker TEXT NOT NULL,
    sns_links JSONB NOT NULL,
    representative_works JSONB NOT NULL,
    similar_actresses JSONB NOT NULL,
    raw_profile JSONB NOT NULL,
    last_fetched_at TIMESTAMP WITHOUT TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE,
    PRIMARY KEY (id),
    CONSTRAINT uq_actress_profiles_source_url UNIQUE (source_url)
);

CREATE INDEX idx_actress_profiles_display_name
    ON actress_profiles (display_name);

CREATE INDEX idx_actress_profiles_source_url
    ON actress_profiles (source_url);

CREATE INDEX idx_actress_profiles_source_task_ids_gin
    ON actress_profiles USING gin (source_task_ids);

CREATE INDEX idx_actress_profiles_aliases_gin
    ON actress_profiles USING gin (aliases);

CREATE INDEX idx_actress_profiles_canonical_names_gin
    ON actress_profiles USING gin (canonical_names);

ALTER TABLE movies
    ADD COLUMN source_task_url_ids UUID[] NOT NULL DEFAULT '{}';

CREATE INDEX idx_movies_source_task_url_ids_gin
    ON movies USING gin (source_task_url_ids);
