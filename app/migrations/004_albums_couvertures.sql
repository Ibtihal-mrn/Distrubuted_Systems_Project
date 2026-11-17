-- Photo de couverture facultative d'un album (identifiant d'une photo).
-- Pas de clé étrangère : la photo peut se trouver sur l'autre shard.
-- Additive : colonne nullable, compatible avec la version précédente de l'application.
ALTER TABLE albums ADD COLUMN IF NOT EXISTS couverture_photo_id UUID;