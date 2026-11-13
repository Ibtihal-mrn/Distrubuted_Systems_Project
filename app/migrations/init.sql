CREATE TABLE IF NOT EXISTS photos (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nom         TEXT NOT NULL,
    sha256      TEXT NOT NULL,
    contenu     BYTEA NOT NULL,
    type_mime   TEXT NOT NULL,
    taille      INTEGER NOT NULL,
    date_ajout  TIMESTAMP NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_photos_sha256 ON photos (sha256);