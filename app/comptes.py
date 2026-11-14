"""Comptes utilisateurs et albums. Toutes ces tables vivent sur le shard 0."""
import psycopg
from psycopg import errors
from psycopg.rows import dict_row
from werkzeug.security import generate_password_hash, check_password_hash

from db import connect  # connexion à un shard, définie dans db.py

SHARD_COMPTES = 0  # users, albums, album_membres, album_photos sont sur le shard 0


# Une connexion par appel, fermée à la fin 

def _une_ligne(sql, params=()):
    """Exécute un SELECT et renvoie la première ligne (dict) ou None."""
    # "with connect(...)" valide et ferme la connexion à la sortie du bloc.
    # row_factory=dict_row : chaque ligne est un dict {colonne: valeur}.
    with connect(SHARD_COMPTES) as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, params)
        return cur.fetchone()


def _toutes(sql, params=()):
    """Exécute un SELECT et renvoie toutes les lignes (liste de dicts)."""
    with connect(SHARD_COMPTES) as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def _ecrire(sql, params=()):
    """Exécute un INSERT/UPDATE/DELETE avec RETURNING éventuel ; renvoie la première ligne ou None."""
    with connect(SHARD_COMPTES) as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, params)
        return cur.fetchone() if cur.description else None


# Condition SQL réutilisée : "l'utilisateur %s a accès à l'album a" =
#   il en est propriétaire, OU l'album est partagé ET il est membre.
# Les trois %s sont dans l'ordre : proprietaire, membre.
_ACCES_ALBUM = """(a.proprietaire_id = %s
    OR (a.partage AND EXISTS (SELECT 1 FROM album_membres m
                              WHERE m.album_id = a.id AND m.user_id = %s)))"""


# Utilisateurs 

def creer_utilisateur(email, mot_de_passe):
    """Crée un compte. Renvoie {id, email} ou None si l'email existe déjà."""
    email = email.strip().lower()  # "A@b.c" et "a@b.c" = même compte
    # On ne stocke JAMAIS le mot de passe : seulement son hash (salé par Werkzeug).
    hash_mdp = generate_password_hash(mot_de_passe)
    try:
        return _ecrire(
            "INSERT INTO users (email, mot_de_passe_hash) VALUES (%s, %s) RETURNING id, email",
            (email, hash_mdp),
        )
    except errors.UniqueViolation:  # contrainte UNIQUE sur email
        return None


def verifier_utilisateur(email, mot_de_passe):
    """Renvoie {id, email} si l'email et le mot de passe sont corrects, sinon None."""
    ligne = _une_ligne(
        "SELECT id, email, mot_de_passe_hash FROM users WHERE email = %s",
        (email.strip().lower(),),
    )
    # check_password_hash recalcule le hash du mot de passe saisi et le compare.
    if ligne and check_password_hash(ligne["mot_de_passe_hash"], mot_de_passe):
        return {"id": ligne["id"], "email": ligne["email"]}
    return None


def get_utilisateur(user_id):
    """Renvoie {id, email} ou None (utilisé pour savoir qui est connecté à partir du cookie)."""
    return _une_ligne("SELECT id, email FROM users WHERE id = %s", (user_id,))


# Albums 

def creer_album(user_id, nom, partage=False):
    """Crée un album dont user_id est propriétaire."""
    return _ecrire(
        "INSERT INTO albums (nom, proprietaire_id, partage) VALUES (%s, %s, %s) "
        "RETURNING id, nom, partage, date_creation",
        (nom.strip(), user_id, partage),
    )


def lister_albums(user_id):
    """Albums accessibles : ceux dont je suis propriétaire + les albums partagés dont je suis membre."""
    return _toutes(
        "SELECT a.id, a.nom, a.partage, a.date_creation, "
        "       (a.proprietaire_id = %s) AS est_proprietaire "
        "FROM albums a WHERE " + _ACCES_ALBUM + " ORDER BY a.date_creation DESC",
        (user_id, user_id, user_id),
    )


def get_album(album_id, user_id):
    """Renvoie l'album si user_id y a accès, sinon None (même réponse si l'album n'existe pas)."""
    return _une_ligne(
        "SELECT a.id, a.nom, a.partage, a.date_creation, "
        "       (a.proprietaire_id = %s) AS est_proprietaire "
        "FROM albums a WHERE a.id = %s AND " + _ACCES_ALBUM,
        (user_id, album_id, user_id, user_id),
    )


def supprimer_album(album_id, user_id):
    """Supprime l'album (propriétaire seulement). Renvoie True si supprimé."""
    ligne = _ecrire(
        "DELETE FROM albums WHERE id = %s AND proprietaire_id = %s RETURNING id",
        (album_id, user_id),
    )
    return ligne is not None  # les liens album_photos/album_membres partent avec (ON DELETE CASCADE)


def ajouter_membre(album_id, proprietaire_id, email_membre):
    """Ajoute un membre à un album partagé. Renvoie 'ok', 'interdit' ou 'inconnu'."""
    album = _une_ligne(
        "SELECT id FROM albums WHERE id = %s AND proprietaire_id = %s AND partage",
        (album_id, proprietaire_id),
    )
    if album is None:
        return "interdit"  # pas propriétaire, ou album privé
    membre = _une_ligne("SELECT id FROM users WHERE email = %s", (email_membre.strip().lower(),))
    if membre is None:
        return "inconnu"
    _ecrire(
        "INSERT INTO album_membres (album_id, user_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
        (album_id, membre["id"]),
    )
    return "ok"


# Photos dans les albums

def ajouter_photo_a_album(album_id, user_id, photo_id):
    """Range une photo dans un album auquel user_id a accès. Renvoie True si fait.
    NB : vérifier que la photo appartient à user_id est fait par l'appelant (la photo est sur un autre shard)."""
    if get_album(album_id, user_id) is None:
        return False
    _ecrire(
        "INSERT INTO album_photos (album_id, photo_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
        (album_id, photo_id),
    )
    return True


def retirer_photo_de_album(album_id, user_id, photo_id):
    """Retire une photo d'un album (propriétaire de l'album seulement). Renvoie True si retirée."""
    ligne = _ecrire(
        "DELETE FROM album_photos ap USING albums a "
        "WHERE ap.album_id = a.id AND a.id = %s AND a.proprietaire_id = %s AND ap.photo_id = %s "
        "RETURNING ap.photo_id",
        (album_id, user_id, photo_id),
    )
    return ligne is not None


def ids_photos_album(album_id):
    """Identifiants des photos d'un album. L'accès à l'album doit avoir été vérifié avant."""
    return [l["photo_id"] for l in _toutes(
        "SELECT photo_id FROM album_photos WHERE album_id = %s", (album_id,))]


def photo_visible_via_album(photo_id, user_id):
    """Vrai si la photo est dans au moins un album auquel user_id a accès (propriétaire ou membre)."""
    ligne = _une_ligne(
        "SELECT 1 AS ok FROM album_photos ap JOIN albums a ON a.id = ap.album_id "
        "WHERE ap.photo_id = %s AND " + _ACCES_ALBUM + " LIMIT 1",
        (photo_id, user_id, user_id),
    )
    return ligne is not None

def oublier_photo(photo_id):
    """Supprime tous les liens album <-> photo d'une photo supprimée (pas de clé étrangère entre shards)."""
    _ecrire("DELETE FROM album_photos WHERE photo_id = %s", (photo_id,))


def modifier_album(album_id, user_id, nom, partage):
    """Renomme / change le partage. Seul le propriétaire peut. Renvoie False sinon."""
    with connect(SHARD_COMPTES) as conn:
        with conn.cursor() as cur:
            # COALESCE : si on passe None, on garde la valeur actuelle
            cur.execute(
                "UPDATE albums SET nom = COALESCE(%s, nom), partage = COALESCE(%s, partage)"
                " WHERE id = %s AND proprietaire_id = %s",
                (nom, partage, album_id, user_id),
            )
            if cur.rowcount == 0:
                return False
            if partage is False:   # album redevenu privé : plus de membres
                cur.execute("DELETE FROM album_membres WHERE album_id = %s", (album_id,))
            return True


def lister_membres(album_id):
    with connect(SHARD_COMPTES) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT u.id, u.email FROM album_membres m JOIN users u ON u.id = m.user_id"
                " WHERE m.album_id = %s ORDER BY u.email",
                (album_id,),
            )
            return [{"id": str(i), "email": e} for i, e in cur.fetchall()]


def retirer_membre(album_id, user_id, membre_id):
    """Seul le propriétaire de l'album peut retirer un membre."""
    with connect(SHARD_COMPTES) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM album_membres WHERE album_id = %s AND user_id = %s"
                " AND EXISTS (SELECT 1 FROM albums WHERE id = %s AND proprietaire_id = %s)",
                (album_id, membre_id, album_id, user_id),
            )
            return cur.rowcount > 0