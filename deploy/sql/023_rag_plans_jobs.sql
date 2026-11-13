-- R1: plans, approvals, jobs, runs, lease. No RAG payloads.

BEGIN;

CREATE TABLE IF NOT EXISTS public.rag_plans (
    plan_id       text PRIMARY KEY,
    intent        text NOT NULL,
    status        text NOT NULL DEFAULT 'proposed'
                  CHECK (status IN ('proposed','approved','dispatched','running','succeeded','failed','cancelled','expired')),
    risk_level    text NOT NULL DEFAULT 'low' CHECK (risk_level IN ('low','medium','high')),
    plan_hash     text NOT NULL,
    created_by    text NOT NULL,
    approved_by   text,
    approved_at   timestamptz,
    expires_at    timestamptz,
    payload       jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.rag_plan_steps (
    step_id         text PRIMARY KEY,
    plan_id         text NOT NULL REFERENCES public.rag_plans(plan_id) ON DELETE CASCADE,
    step_order      integer NOT NULL,
    action          text NOT NULL,
    rag_id          text NOT NULL,
    library_id      text NOT NULL DEFAULT '',
    query           text NOT NULL DEFAULT '',
    snapshot        text NOT NULL DEFAULT '',
    depends_on      jsonb NOT NULL DEFAULT '[]'::jsonb,
    status          text NOT NULL DEFAULT 'proposed'
                    CHECK (status IN ('proposed','queued','leased','running','succeeded','failed','cancelled')),
    risk_level      text NOT NULL DEFAULT 'low' CHECK (risk_level IN ('low','medium','high')),
    timeout_seconds integer NOT NULL DEFAULT 300
);

CREATE TABLE IF NOT EXISTS public.rag_jobs (
    job_id          text PRIMARY KEY,
    plan_id         text NOT NULL REFERENCES public.rag_plans(plan_id) ON DELETE CASCADE,
    step_id         text NOT NULL REFERENCES public.rag_plan_steps(step_id) ON DELETE CASCADE,
    rag_id          text NOT NULL,
    library_id      text NOT NULL DEFAULT '',
    job_type        text NOT NULL,
    priority        integer NOT NULL DEFAULT 0,
    status          text NOT NULL DEFAULT 'queued'
                    CHECK (status IN ('queued','leased','running','succeeded','failed','cancelled')),
    payload         jsonb NOT NULL DEFAULT '{}'::jsonb,
    resource_request jsonb NOT NULL DEFAULT '{}'::jsonb,
    lease_owner     text,
    lease_expires_at timestamptz,
    attempts        integer NOT NULL DEFAULT 0,
    max_attempts    integer NOT NULL DEFAULT 3,
    error           text NOT NULL DEFAULT '',
    created_at      timestamptz NOT NULL DEFAULT now(),
    started_at      timestamptz,
    finished_at     timestamptz
);

CREATE TABLE IF NOT EXISTS public.rag_runs (
    run_id       text PRIMARY KEY,
    job_id       text NOT NULL REFERENCES public.rag_jobs(job_id) ON DELETE CASCADE,
    rag_id       text NOT NULL,
    library_id   text NOT NULL DEFAULT '',
    snapshot     text NOT NULL DEFAULT '',
    model_version text NOT NULL DEFAULT '',
    env_hash     text NOT NULL DEFAULT '',
    exit_code    integer,
    artifact_uri text NOT NULL DEFAULT '',
    metrics      jsonb NOT NULL DEFAULT '{}'::jsonb,
    started_at   timestamptz,
    finished_at  timestamptz
);

CREATE INDEX IF NOT EXISTS rag_jobs_queue_idx
    ON public.rag_jobs (status, priority DESC, created_at);
CREATE INDEX IF NOT EXISTS rag_jobs_lease_idx
    ON public.rag_jobs (lease_expires_at);
CREATE INDEX IF NOT EXISTS rag_plan_steps_plan_idx
    ON public.rag_plan_steps (plan_id, step_order);

GRANT SELECT, INSERT, UPDATE, DELETE ON
    public.rag_plans,
    public.rag_plan_steps,
    public.rag_jobs,
    public.rag_runs
TO scipal_core_app;

COMMIT;
