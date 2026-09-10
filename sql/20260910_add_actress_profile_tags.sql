ALTER TABLE actress_profiles
    ADD COLUMN tags TEXT[] NOT NULL DEFAULT '{}';

CREATE INDEX idx_actress_profiles_tags_gin
    ON actress_profiles USING gin (tags);

ALTER TABLE actress_profiles
    ALTER COLUMN tags DROP DEFAULT;
