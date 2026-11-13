-- R18: public key directory for seal signatures.

BEGIN;

CREATE TABLE IF NOT EXISTS public.rag_signing_keys (
    key_id       text PRIMARY KEY,
    public_key   text NOT NULL,
    algorithm    text NOT NULL DEFAULT 'ed25519',
    first_seen_at timestamptz NOT NULL DEFAULT now(),
    last_seen_at  timestamptz NOT NULL DEFAULT now()
);

GRANT SELECT, INSERT, UPDATE, DELETE ON public.rag_signing_keys TO scipal_core_app;

COMMIT;
