"""Accès aux deux shards PostgreSQL : routage, ajout, lecture, suppression, doublons."""
import hashlib   # calcul de l'empreinte SHA-256
import os        # lecture des variables d'environnement

import psycopg   # pilote PostgreSQL

# Variables d'environnement qui contiennent l'adresse de chaque shard.
# L'indice dans la liste = le numéro du shard (0 ou 1).
SHARD_VARS = ["SHARD0_DSN", "SHARD1_DSN"]
N_SHARDS = len(SHARD_VARS)   # = 2


def sha256_hex(contenu):
    """Empreinte SHA-256 d'une suite d'octets, en 64 caractères hexadécimaux."""
    # hashlib.sha256(octets) calcule l'empreinte, .hexdigest() la donne en texte.
    return hashlib.sha256(contenu).hexdigest()


def shard_for(empreinte):
    """Numéro du shard (0 ou 1) pour une empreinte SHA-256 en hexadécimal."""
    # empreinte[:8]      -> les 8 premiers caractères
    # int(..., 16)       -> lus comme un nombre écrit en base 16
    # % N_SHARDS         -> reste de la division par 2 : donne 0 ou 1
    # Même formule que scripts/shard-demo.sh : les deux doivent toujours router pareil.
    return int(empreinte[:8], 16) % N_SHARDS


def connect(shard):
    """Ouvre une connexion vers le shard demandé (0 ou 1)."""
    # SHARD_VARS[shard] = nom de la variable ; os.environ[...] = sa valeur (l'adresse).
    return psycopg.connect(os.environ[SHARD_VARS[shard]])


def add_photo(nom, type_mime, contenu):
    """Enregistre une photo dans le bon shard.

    Renvoie un dictionnaire décrivant la photo, avec la liste des photos
    déjà présentes qui ont exactement le même contenu (doublons).
    """
    empreinte = sha256_hex(contenu)    # empreinte du contenu
    shard = shard_for(empreinte)       # shard choisi à partir de l'empreinte

    # "with connect(...) as conn" : la transaction est validée (commit) à la sortie
    # du bloc si tout va bien, annulée (rollback) en cas d'erreur.
    with connect(shard) as conn:
        with conn.cursor() as cur:
            # Photos déjà enregistrées avec la même empreinte = doublons.
            # Les %s sont des emplacements : les valeurs sont transmises à part.
            cur.execute("SELECT id, nom FROM photos WHERE sha256 = %s", (empreinte,))
            # str(ligne[0]) : l'id est un objet UUID, on le convertit en texte.
            doublons = [{"id": str(ligne[0]), "nom": ligne[1]} for ligne in cur.fetchall()]

            # Insertion. RETURNING renvoie des valeurs générées par la base
            # (l'id aléatoire et la date), qu'on récupère avec fetchone().
            cur.execute(
                "INSERT INTO photos (nom, sha256, contenu, type_mime, taille)"
                " VALUES (%s, %s, %s, %s, %s) RETURNING id, date_ajout",
                (nom, empreinte, contenu, type_mime, len(contenu)),
            )
            photo_id, date_ajout = cur.fetchone()

    return {
        "id": str(photo_id),
        "nom": nom,
        "sha256": empreinte,
        "type_mime": type_mime,
        "taille": len(contenu),                # nombre d'octets
        "date_ajout": date_ajout.isoformat(),  # date convertie en texte
        "shard": shard,
        "doublons": doublons,
    }


def list_photos():
    """Liste toutes les photos (sans leur contenu), les plus récentes d'abord."""
    resultat = []
    # On ne sait pas où sont les photos : on interroge les deux shards.
    for shard in range(N_SHARDS):
        with connect(shard) as conn:
            with conn.cursor() as cur:
                # On ne sélectionne PAS "contenu" : lire les octets de toutes
                # les images pour une simple liste serait très lourd.
                cur.execute(
                    "SELECT id, nom, sha256, type_mime, taille, date_ajout FROM photos"
                )
                for ligne in cur.fetchall():
                    resultat.append(
                        {
                            "id": str(ligne[0]),
                            "nom": ligne[1],
                            "sha256": ligne[2],
                            "type_mime": ligne[3],
                            "taille": ligne[4],
                            "date_ajout": ligne[5].isoformat(),
                            "shard": shard,
                        }
                    )
    # Fusionne les deux listes : tri par date, la plus récente en premier.
    resultat.sort(key=lambda photo: photo["date_ajout"], reverse=True)
    return resultat


def get_photo(photo_id):
    """Renvoie (nom, type_mime, contenu) d'une photo, ou None si elle n'existe pas.

    L'identifiant ne dit pas dans quel shard se trouve la photo :
    on interroge les deux, l'un après l'autre.
    """
    for shard in range(N_SHARDS):
        with connect(shard) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT nom, type_mime, contenu FROM photos WHERE id = %s",
                    (photo_id,),
                )
                ligne = cur.fetchone()   # une ligne, ou None si rien trouvé
                if ligne is not None:
                    return ligne[0], ligne[1], ligne[2]
    return None   # introuvable dans les deux shards


def get_info(photo_id):
    """Renvoie les informations d'une photo (sans le contenu), ou None."""
    for shard in range(N_SHARDS):
        with connect(shard) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, nom, sha256, type_mime, taille, date_ajout"
                    " FROM photos WHERE id = %s",
                    (photo_id,),
                )
                ligne = cur.fetchone()
                if ligne is not None:
                    return {
                        "id": str(ligne[0]),
                        "nom": ligne[1],
                        "sha256": ligne[2],
                        "type_mime": ligne[3],
                        "taille": ligne[4],
                        "date_ajout": ligne[5].isoformat(),
                        "shard": shard,
                    }
    return None


def delete_photo(photo_id):
    """Supprime une photo. Renvoie True si elle existait, False sinon."""
    for shard in range(N_SHARDS):
        with connect(shard) as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM photos WHERE id = %s", (photo_id,))
                # rowcount = nombre de lignes supprimées par la requête.
                if cur.rowcount > 0:
                    return True
    return False


def find_duplicates():
    """Groupes de photos ayant exactement le même contenu.

    Deux fichiers identiques ont la même empreinte, donc le même shard :
    il suffit de chercher les doublons à l'intérieur de chaque shard.
    """
    groupes = []
    for shard in range(N_SHARDS):
        with connect(shard) as conn:
            with conn.cursor() as cur:
                # GROUP BY sha256 : une ligne par empreinte.
                # HAVING count(*) > 1 : on garde les empreintes qui apparaissent
                # plusieurs fois. array_agg regroupe les id et les noms en listes.
                cur.execute(
                    "SELECT sha256, array_agg(id), array_agg(nom), max(taille)"
                    " FROM photos GROUP BY sha256 HAVING count(*) > 1"
                )
                for empreinte, ids, noms, taille in cur.fetchall():
                    groupes.append(
                        {
                            "sha256": empreinte,
                            "taille": taille,
                            # zip(ids, noms) associe chaque id à son nom.
                            "photos": [
                                {"id": str(i), "nom": n} for i, n in zip(ids, noms)
                            ],
                        }
                    )
    return groupes
