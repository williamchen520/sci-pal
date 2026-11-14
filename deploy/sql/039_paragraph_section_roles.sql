CREATE TABLE IF NOT EXISTS paragraph_section_roles (
    para_id text NOT NULL,
    role text NOT NULL,
    source text NOT NULL DEFAULT 'heuristic_v1',
    confidence real NOT NULL DEFAULT 0.5,
    version text NOT NULL DEFAULT 'v1',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (para_id, source)
);

CREATE INDEX IF NOT EXISTS paragraph_section_roles_role_idx
    ON paragraph_section_roles (role);

CREATE INDEX IF NOT EXISTS paragraph_section_roles_source_idx
    ON paragraph_section_roles (source);
