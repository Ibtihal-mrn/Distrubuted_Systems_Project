CREATE TABLE IF NOT EXISTS photos (      -- « IF NOT EXISTS » : pas d'erreur si elle existe déjà
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),   -- identifiant unique, généré automatiquement
    nom         TEXT NOT NULL,           -- nom du fichier
    sha256      TEXT NOT NULL,           -- empreinte du contenu (sert à détecter les doublons et à choisir le shard)
    contenu     BYTEA NOT NULL,          -- les octets de l'image, stockés dans la base
    type_mime   TEXT NOT NULL,           -- image/jpeg, image/png...
    taille      INTEGER NOT NULL,        -- en octets
    date_ajout  TIMESTAMP NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_photos_sha256 ON photos (sha256);   -- accélère la recherche par empreinte