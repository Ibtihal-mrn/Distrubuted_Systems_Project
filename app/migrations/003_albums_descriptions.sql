-- Description facultative d'un album.
-- Migration additive : la colonne est nullable, donc l'ancienne version de l'application
-- (qui ne la connaît pas) continue de fonctionner pendant le rolling update.
ALTER TABLE albums ADD COLUMN IF NOT EXISTS description TEXT;