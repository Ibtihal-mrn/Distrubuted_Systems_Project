-- Comptes utilisateurs. Un seul mot de passe haché par utilisateur : jamais le mot de passe en clair.
CREATE TABLE IF NOT EXISTS users (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email            TEXT NOT NULL UNIQUE,          -- UNIQUE : impossible de créer deux comptes avec le même email
    mot_de_passe_hash TEXT NOT NULL,                -- résultat de generate_password_hash()
    date_creation    TIMESTAMP NOT NULL DEFAULT now()
);

-- Albums. "partage" = false : privé (propriétaire seul). true : visible par les membres.
CREATE TABLE IF NOT EXISTS albums (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nom             TEXT NOT NULL,
    proprietaire_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,  -- si l'utilisateur est supprimé, ses albums aussi
    partage         BOOLEAN NOT NULL DEFAULT FALSE,
    date_creation   TIMESTAMP NOT NULL DEFAULT now()
);

-- Membres d'un album partagé (en plus du propriétaire).
CREATE TABLE IF NOT EXISTS album_membres (
    album_id UUID NOT NULL REFERENCES albums(id) ON DELETE CASCADE,
    user_id  UUID NOT NULL REFERENCES users(id)  ON DELETE CASCADE,
    PRIMARY KEY (album_id, user_id)                -- un utilisateur ne peut être membre qu'une fois
);

-- Photos rangées dans un album. Une photo peut être dans plusieurs albums.
-- Pas de clé étrangère sur photo_id : la photo peut se trouver sur l'autre shard.
CREATE TABLE IF NOT EXISTS album_photos (
    album_id UUID NOT NULL REFERENCES albums(id) ON DELETE CASCADE,
    photo_id UUID NOT NULL,
    PRIMARY KEY (album_id, photo_id)
);

-- Propriétaire d'une photo. Nullable : les photos déjà envoyées n'en ont pas.
-- Pas de clé étrangère non plus : l'utilisateur est sur le shard 0, la photo peut être sur le shard 1.
ALTER TABLE photos ADD COLUMN IF NOT EXISTS user_id UUID;
CREATE INDEX IF NOT EXISTS idx_photos_user ON photos (user_id);