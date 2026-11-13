-- R14: Ed25519 seal signature + local signed_at. Not an external TSA.

BEGIN;

ALTER TABLE public.rag_multi_finalizations
    ADD COLUMN IF NOT EXISTS signature text,
    ADD COLUMN IF NOT EXISTS public_key text,
    ADD COLUMN IF NOT EXISTS signature_algorithm text NOT NULL DEFAULT 'ed25519',
    ADD COLUMN IF NOT EXISTS key_id text NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS signed_at timestamptz;

COMMIT;
