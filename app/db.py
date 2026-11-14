"""Accès aux deux shards PostgreSQL : routage, ajout, lecture, suppression, doublons.

Chaque photo a un propriétaire (colonne user_id). Les fonctions de ce fichier ne
décident PAS des droits d'accès via les albums : c'est app.py qui combine
"propriétaire" (ici) et "photo dans un album accessible" (comptes.py).
"""
import hashlib   # calcul de l'empreinte SHA-256
import os        # lecture des variables d'environnement
import uuid      # conversion de texte en identifiant UUID

import psycopg   # pilote PostgreSQL

# Variables d'environnement qui contiennent l'adresse de chaque shard.
# L'indice dans la liste = le numéro du shard (0 ou 1).
SHARD_VARS = ["SHARD0_DSN", "SHARD1_DSN"]
N_SHARDS = len(SHARD_VARS)   # = 2


def sha256_hex(contenu):
    """Empreinte SHA-256 d'une suite d'octets, en 64 caractères hexadécimaux."""
    return hashlib.sha256(contenu).hexdigest()


def shard_for(empreinte):
    """Numéro du shard (0 ou 1) pour une empreinte SHA-256 en hexadécimal."""
    # Même formule que scripts/shard-demo.sh : les deux doivent toujours router pareil.
    # Le routage ne dépend PAS de l'utilisateur : le même fichier va toujours au même shard.
    return int(empreinte[:8], 16) % N_SHARDS


def connect(shard):
    """Ouvre une connexion vers le shard demandé (0 ou 1)."""
    return psycopg.connect(os.environ[SHARD_VARS[shard]])


def _ligne_vers_info(ligne, shard):
    """Transforme une ligne SQL (id, nom, sha256, type_mime, taille, date_ajout, user_id) en dict."""
    return {
        "id": str(ligne[0]),
        "nom": ligne[1],
        "sha256": ligne[2],
        "type_mime": ligne[3],
        "taille": ligne[4],
        "date_ajout": ligne[5].isoformat(),
        # user_id peut être NULL pour les photos envoyées avant l'ajout des comptes
        "user_id": str(ligne[6]) if ligne[6] is not None else None,
        "shard": shard,
    }


# Colonnes lues pour décrire une photo (sans "contenu", trop lourd pour une liste).
_COLONNES_INFO = "id, nom, sha256, type_mime, taille, date_ajout, user_id"


def add_photo(nom, type_mime, contenu, user_id):
    """Enregistre une photo de user_id dans le bon shard.

    Renvoie un dictionnaire décrivant la photo, avec la liste des photos DE CET
    UTILISATEUR qui ont exactement le même contenu (doublons).
    """
    empreinte = sha256_hex(contenu)    # empreinte du contenu
    shard = shard_for(empreinte)       # shard choisi à partir de l'empreinte

    with connect(shard) as conn:
        with conn.cursor() as cur:
            # Doublons = mêmes octets ET même propriétaire. On ne filtre pas sur
            # l'empreinte seule : on révélerait l'existence (id, nom) des photos
            # privées d'un autre utilisateur.
            cur.execute(
                "SELECT id, nom FROM photos WHERE sha256 = %s AND user_id = %s",
                (empreinte, user_id),
            )
            doublons = [{"id": str(ligne[0]), "nom": ligne[1]} for ligne in cur.fetchall()]

            cur.execute(
                "INSERT INTO photos (nom, sha256, contenu, type_mime, taille, user_id)"
                " VALUES (%s, %s, %s, %s, %s, %s) RETURNING id, date_ajout",
                (nom, empreinte, contenu, type_mime, len(contenu), user_id),
            )
            photo_id, date_ajout = cur.fetchone()

    return {
        "id": str(photo_id),
        "nom": nom,
        "sha256": empreinte,
        "type_mime": type_mime,
        "taille": len(contenu),
        "date_ajout": date_ajout.isoformat(),
        "user_id": str(user_id),
        "shard": shard,
        "doublons": doublons,
    }


def list_photos(user_id):
    """Liste les photos DE user_id (sans leur contenu), les plus récentes d'abord."""
    resultat = []
    # On ne sait pas où sont les photos : on interroge les deux shards.
    for shard in range(N_SHARDS):
        with connect(shard) as conn:
            with conn.cursor() as cur:
                # WHERE user_id = ... : seulement les photos de l'utilisateur.
                # Les anciennes photos (user_id NULL) n'apparaissent donc chez personne.
                cur.execute(
                    f"SELECT {_COLONNES_INFO} FROM photos WHERE user_id = %s",
                    (user_id,),
                )
                for ligne in cur.fetchall():
                    resultat.append(_ligne_vers_info(ligne, shard))
    resultat.sort(key=lambda photo: photo["date_ajout"], reverse=True)
    return resultat


def list_photos_by_ids(photo_ids):
    """Informations (sans contenu) des photos dont l'id est dans photo_ids, tous propriétaires confondus.

    Sert à afficher le contenu d'un album. AUCUN contrôle de droits ici :
    l'appelant doit avoir vérifié l'accès à l'album avant.
    """
    if not photo_ids:
        return []
    # Conversion en objets UUID : PostgreSQL compare alors des uuid avec des uuid.
    ids = [uuid.UUID(str(i)) for i in photo_ids]
    resultat = []
    for shard in range(N_SHARDS):
        with connect(shard) as conn:
            with conn.cursor() as cur:
                # id = ANY(liste) : vrai si l'id est dans la liste.
                cur.execute(
                    f"SELECT {_COLONNES_INFO} FROM photos WHERE id = ANY(%s)",
                    (ids,),
                )
                for ligne in cur.fetchall():
                    resultat.append(_ligne_vers_info(ligne, shard))
    resultat.sort(key=lambda photo: photo["date_ajout"], reverse=True)
    return resultat


def get_photo(photo_id):
    """Renvoie (nom, type_mime, contenu) d'une photo, ou None si elle n'existe pas.

    AUCUN contrôle de droits ici : app.py appelle d'abord get_info() pour vérifier
    que l'utilisateur a le droit de voir la photo, puis cette fonction.
    """
    for shard in range(N_SHARDS):
        with connect(shard) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT nom, type_mime, contenu FROM photos WHERE id = %s",
                    (photo_id,),
                )
                ligne = cur.fetchone()
                if ligne is not None:
                    return ligne[0], ligne[1], ligne[2]
    return None


def get_info(photo_id):
    """Renvoie les informations d'une photo (sans le contenu, avec user_id), ou None."""
    for shard in range(N_SHARDS):
        with connect(shard) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT {_COLONNES_INFO} FROM photos WHERE id = %s",
                    (photo_id,),
                )
                ligne = cur.fetchone()
                if ligne is not None:
                    return _ligne_vers_info(ligne, shard)
    return None


def delete_photo(photo_id, user_id):
    """Supprime une photo si elle appartient à user_id. Renvoie True si supprimée."""
    for shard in range(N_SHARDS):
        with connect(shard) as conn:
            with conn.cursor() as cur:
                # AND user_id = ... : on ne peut supprimer que ses propres photos.
                cur.execute(
                    "DELETE FROM photos WHERE id = %s AND user_id = %s",
                    (photo_id, user_id),
                )
                if cur.rowcount > 0:
                    return True
    return False


def find_duplicates(user_id):
    """Groupes de photos DE user_id ayant exactement le même contenu.

    Deux fichiers identiques ont la même empreinte, donc le même shard :
    il suffit de chercher les doublons à l'intérieur de chaque shard.
    """
    groupes = []
    for shard in range(N_SHARDS):
        with connect(shard) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT sha256, array_agg(id ORDER BY date_ajout, id),"
                    "       array_agg(nom ORDER BY date_ajout, id), max(taille)"
                    " FROM photos WHERE user_id = %s"
                    " GROUP BY sha256 HAVING count(*) > 1",
                    (user_id,),
                )
                for empreinte, ids, noms, taille in cur.fetchall():
                    groupes.append(
                        {
                            "sha256": empreinte,
                            "taille": taille,
                            "photos": [
                                {"id": str(i), "nom": n} for i, n in zip(ids, noms)
                            ],
                        }
                    )
    return groupes
