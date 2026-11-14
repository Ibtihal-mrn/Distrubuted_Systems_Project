"""Éléments partagés par tous les tests : fausses bases en mémoire et clients de test.

Les fonctions de db.py (photos) et comptes.py (comptes, albums) sont remplacées par des
versions en mémoire : on teste uniquement la logique des routes (codes HTTP, droits d'accès,
validations, en-têtes), sans PostgreSQL.
"""
import io
import uuid
from datetime import datetime

import pytest

import comptes
import db
from app import app


class FakeDB:
    """Imite db.py avec un dictionnaire en mémoire. Chaque photo a un propriétaire (user_id)."""

    def __init__(self):
        self.photos = {}   # id -> informations + contenu

    def _info(self, photo_id):
        return {k: v for k, v in self.photos[photo_id].items() if k != "contenu"}

    def add_photo(self, nom, type_mime, contenu, user_id):
        empreinte = db.sha256_hex(contenu)
        # Doublon = même contenu chez LE MÊME utilisateur
        doublons = [{"id": p["id"], "nom": p["nom"]} for p in self.photos.values()
                    if p["sha256"] == empreinte and p["user_id"] == user_id]
        photo_id = str(uuid.uuid4())
        self.photos[photo_id] = {
            "id": photo_id, "nom": nom, "sha256": empreinte, "type_mime": type_mime,
            "taille": len(contenu), "date_ajout": "2026-01-01T00:00:00",
            "shard": db.shard_for(empreinte), "user_id": user_id, "contenu": contenu,
        }
        return {**self._info(photo_id), "doublons": doublons}

    def list_photos(self, user_id):
        return [self._info(i) for i, p in self.photos.items() if p["user_id"] == user_id]

    def list_photos_by_ids(self, photo_ids):
        return [self._info(str(i)) for i in photo_ids if str(i) in self.photos]

    def get_photo(self, photo_id):
        p = self.photos.get(photo_id)
        return None if p is None else (p["nom"], p["type_mime"], p["contenu"])

    def get_info(self, photo_id):
        return self._info(photo_id) if photo_id in self.photos else None

    def delete_photo(self, photo_id, user_id):
        p = self.photos.get(photo_id)
        if p is None or p["user_id"] != user_id:
            return False
        del self.photos[photo_id]
        return True

    def find_duplicates(self, user_id):
        groupes = {}
        for p in self.photos.values():
            if p["user_id"] == user_id:
                groupes.setdefault(p["sha256"], []).append(p)
        return [{"sha256": e, "taille": liste[0]["taille"],
                 "photos": [{"id": p["id"], "nom": p["nom"]} for p in liste]}
                for e, liste in groupes.items() if len(liste) > 1]


class FakeComptes:
    """Imite comptes.py : utilisateurs, albums, membres, photos rangées dans les albums."""

    def __init__(self):
        self.users = {}        # id -> {"id", "email", "mdp"}
        self.albums = {}       # id -> {"id", "nom", "proprietaire_id", "partage", "date_creation"}
        self.membres = set()   # {(album_id, user_id)}
        self.liens = set()     # {(album_id, photo_id)}

    # Utilisateurs
    def creer_utilisateur(self, email, mot_de_passe):
        email = email.strip().lower()
        if any(u["email"] == email for u in self.users.values()):
            return None
        uid = str(uuid.uuid4())
        self.users[uid] = {"id": uid, "email": email, "mdp": mot_de_passe}
        return {"id": uid, "email": email}

    def verifier_utilisateur(self, email, mot_de_passe):
        for u in self.users.values():
            if u["email"] == email.strip().lower() and u["mdp"] == mot_de_passe:
                return {"id": u["id"], "email": u["email"]}
        return None

    def get_utilisateur(self, user_id):
        u = self.users.get(user_id)
        return None if u is None else {"id": u["id"], "email": u["email"]}

    # Albums
    def _acces(self, album, user_id):
        return album["proprietaire_id"] == user_id or (
            album["partage"] and (album["id"], user_id) in self.membres)

    def _vue(self, album, user_id):
        return {k: album[k] for k in ("id", "nom", "partage", "date_creation")} | {
            "est_proprietaire": album["proprietaire_id"] == user_id}

    def creer_album(self, user_id, nom, partage=False):
        aid = str(uuid.uuid4())
        self.albums[aid] = {"id": aid, "nom": nom.strip(), "proprietaire_id": user_id,
                            "partage": partage, "date_creation": datetime(2026, 1, 1)}
        return {k: self.albums[aid][k] for k in ("id", "nom", "partage", "date_creation")}

    def lister_albums(self, user_id):
        return [self._vue(a, user_id) for a in self.albums.values() if self._acces(a, user_id)]

    def get_album(self, album_id, user_id):
        a = self.albums.get(album_id)
        return self._vue(a, user_id) if a and self._acces(a, user_id) else None

    def supprimer_album(self, album_id, user_id):
        a = self.albums.get(album_id)
        if a is None or a["proprietaire_id"] != user_id:
            return False
        del self.albums[album_id]
        self.membres = {m for m in self.membres if m[0] != album_id}
        self.liens = {l for l in self.liens if l[0] != album_id}
        return True

    def modifier_album(self, album_id, user_id, nom, partage):
        a = self.albums.get(album_id)
        if a is None or a["proprietaire_id"] != user_id:
            return False
        if nom is not None:
            a["nom"] = nom
        if partage is not None:
            a["partage"] = partage
        if partage is False:
            self.membres = {m for m in self.membres if m[0] != album_id}
        return True

    # Membres
    def ajouter_membre(self, album_id, proprietaire_id, email):
        a = self.albums.get(album_id)
        if a is None or a["proprietaire_id"] != proprietaire_id or not a["partage"]:
            return "interdit"
        for u in self.users.values():
            if u["email"] == email.strip().lower():
                self.membres.add((album_id, u["id"]))
                return "ok"
        return "inconnu"

    def lister_membres(self, album_id):
        return sorted(({"id": uid, "email": self.users[uid]["email"]}
                       for (aid, uid) in self.membres if aid == album_id),
                      key=lambda m: m["email"])

    def retirer_membre(self, album_id, user_id, membre_id):
        a = self.albums.get(album_id)
        if a is None or a["proprietaire_id"] != user_id or (album_id, membre_id) not in self.membres:
            return False
        self.membres.discard((album_id, membre_id))
        return True

    # Photos dans les albums
    def ajouter_photo_a_album(self, album_id, user_id, photo_id):
        if self.get_album(album_id, user_id) is None:
            return False
        self.liens.add((album_id, photo_id))
        return True

    def retirer_photo_de_album(self, album_id, user_id, photo_id):
        a = self.albums.get(album_id)
        if a is None or a["proprietaire_id"] != user_id or (album_id, photo_id) not in self.liens:
            return False
        self.liens.discard((album_id, photo_id))
        return True

    def ids_photos_album(self, album_id):
        return [p for (a, p) in self.liens if a == album_id]

    def photo_visible_via_album(self, photo_id, user_id):
        return any(p == photo_id and a in self.albums and self._acces(self.albums[a], user_id)
                   for (a, p) in self.liens)

    def oublier_photo(self, photo_id):
        self.liens = {l for l in self.liens if l[1] != photo_id}


@pytest.fixture
def monde(monkeypatch):
    """Remplace db.py et comptes.py par les versions en mémoire."""
    fake_db, fake_comptes = FakeDB(), FakeComptes()
    for nom in ("add_photo", "list_photos", "list_photos_by_ids", "get_photo", "get_info",
                "delete_photo", "find_duplicates"):
        monkeypatch.setattr(db, nom, getattr(fake_db, nom))
    for nom in ("creer_utilisateur", "verifier_utilisateur", "get_utilisateur", "creer_album",
                "lister_albums", "get_album", "supprimer_album", "modifier_album",
                "ajouter_membre", "lister_membres", "retirer_membre", "ajouter_photo_a_album",
                "retirer_photo_de_album", "ids_photos_album", "photo_visible_via_album",
                "oublier_photo"):
        monkeypatch.setattr(comptes, nom, getattr(fake_comptes, nom))
    return fake_db, fake_comptes


def _client_connecte(email):
    """Nouveau client de test (son propre cookie) dont le compte vient d'être créé."""
    client = app.test_client()
    reponse = client.post("/register", json={"email": email, "mot_de_passe": "motdepasse1"})
    assert reponse.status_code == 201
    return client


@pytest.fixture
def anonyme(monde):
    """Client sans connexion."""
    return app.test_client()


@pytest.fixture
def client(monde):
    """Client connecté en tant qu'alice (le propriétaire dans la plupart des tests)."""
    return _client_connecte("alice@example.com")


@pytest.fixture
def autre(monde, client):
    """Deuxième client, connecté en tant que bob."""
    return _client_connecte("bob@example.com")


@pytest.fixture
def envoyer():
    """Fonction qui envoie un fichier à POST /photos (formulaire multipart) pour un client donné."""
    def _envoyer(client, contenu=b"contenu", nom="photo.jpg"):
        return client.post("/photos", data={"photo": (io.BytesIO(contenu), nom)},
                           content_type="multipart/form-data")
    return _envoyer
