"""Tests des routes de l'API photos, sans base de données.

Les fonctions de db.py sont remplacées par une version en mémoire (FakeDB) :
on teste uniquement la logique des routes (codes HTTP, validations, en-têtes).
"""
import io
import uuid

import psycopg
import pytest

import db
from app import app


class FakeDB:
    """Imite db.py avec un simple dictionnaire en mémoire."""

    def __init__(self):
        self.photos = {}   # id -> dictionnaire d'informations + contenu

    def add_photo(self, nom, type_mime, contenu):
        empreinte = db.sha256_hex(contenu)
        doublons = [
            {"id": p["id"], "nom": p["nom"]}
            for p in self.photos.values()
            if p["sha256"] == empreinte
        ]
        photo_id = str(uuid.uuid4())
        self.photos[photo_id] = {
            "id": photo_id,
            "nom": nom,
            "sha256": empreinte,
            "type_mime": type_mime,
            "taille": len(contenu),
            "date_ajout": "2026-01-01T00:00:00",
            "shard": db.shard_for(empreinte),
            "contenu": contenu,
        }
        return {**self._info(photo_id), "doublons": doublons}

    def _info(self, photo_id):
        return {k: v for k, v in self.photos[photo_id].items() if k != "contenu"}

    def list_photos(self):
        return [self._info(i) for i in self.photos]

    def get_photo(self, photo_id):
        p = self.photos.get(photo_id)
        return None if p is None else (p["nom"], p["type_mime"], p["contenu"])

    def get_info(self, photo_id):
        return self._info(photo_id) if photo_id in self.photos else None

    def delete_photo(self, photo_id):
        return self.photos.pop(photo_id, None) is not None

    def find_duplicates(self):
        groupes = {}
        for p in self.photos.values():
            groupes.setdefault(p["sha256"], []).append(p)
        return [
            {
                "sha256": empreinte,
                "taille": liste[0]["taille"],
                "photos": [{"id": p["id"], "nom": p["nom"]} for p in liste],
            }
            for empreinte, liste in groupes.items()
            if len(liste) > 1
        ]


@pytest.fixture
def client(monkeypatch):
    """Client de test dont les accès aux bases sont remplacés par FakeDB."""
    fake = FakeDB()
    for nom in ("add_photo", "list_photos", "get_photo", "get_info",
                "delete_photo", "find_duplicates"):
        monkeypatch.setattr(db, nom, getattr(fake, nom))
    return app.test_client()


def envoyer(client, contenu=b"contenu", nom="photo.jpg"):
    """Envoie un fichier à POST /photos (formulaire multipart)."""
    return client.post(
        "/photos",
        data={"photo": (io.BytesIO(contenu), nom)},
        content_type="multipart/form-data",
    )


# Envoi

def test_envoi_valide(client):
    reponse = envoyer(client, b"abc", "chat.jpg")
    assert reponse.status_code == 201
    assert reponse.json["nom"] == "chat.jpg"
    assert reponse.json["type_mime"] == "image/jpeg"
    assert reponse.json["taille"] == 3
    assert reponse.json["doublons"] == []


def test_envoi_sans_fichier(client):
    assert client.post("/photos").status_code == 400


def test_envoi_format_interdit(client):
    assert envoyer(client, b"abc", "virus.exe").status_code == 415


def test_envoi_fichier_vide(client):
    assert envoyer(client, b"", "vide.jpg").status_code == 400


def test_envoi_heic_accepte(client):
    reponse = envoyer(client, b"abc", "iphone.HEIC")
    assert reponse.status_code == 201
    assert reponse.json["type_mime"] == "image/heic"


def test_envoi_trop_gros(client, monkeypatch):
    monkeypatch.setitem(app.config, "MAX_CONTENT_LENGTH", 10)
    assert envoyer(client, b"x" * 100, "gros.jpg").status_code == 413


def test_envoi_doublon_signale(client):
    envoyer(client, b"meme contenu", "a.jpg")
    reponse = envoyer(client, b"meme contenu", "b.jpg")
    assert reponse.status_code == 201
    assert len(reponse.json["doublons"]) == 1
    assert "avertissement" in reponse.json


# Lecture et liste

def test_liste(client):
    envoyer(client, b"un", "un.jpg")
    envoyer(client, b"deux", "deux.png")
    reponse = client.get("/photos")
    assert reponse.status_code == 200
    assert sorted(p["nom"] for p in reponse.json) == ["deux.png", "un.jpg"]
    assert "contenu" not in reponse.json[0]


def test_lecture_photo(client):
    photo_id = envoyer(client, b"octets-image", "x.png").json["id"]
    reponse = client.get(f"/photos/{photo_id}")
    assert reponse.status_code == 200
    assert reponse.data == b"octets-image"
    assert reponse.headers["Content-Type"] == "image/png"
    assert reponse.headers["Cache-Control"] == "public, max-age=60"


def test_lecture_id_invalide(client):
    assert client.get("/photos/pas-un-uuid").status_code == 400


def test_lecture_id_inconnu(client):
    assert client.get(f"/photos/{uuid.uuid4()}").status_code == 404


# Suppression

def test_suppression(client):
    photo_id = envoyer(client).json["id"]
    assert client.delete(f"/photos/{photo_id}").status_code == 204
    assert client.get(f"/photos/{photo_id}").status_code == 404
    assert client.delete(f"/photos/{photo_id}").status_code == 404


def test_suppression_id_invalide(client):
    assert client.delete("/photos/xyz").status_code == 400


# Doublons et comparaison

def test_doublons(client):
    envoyer(client, b"identique", "a.jpg")
    envoyer(client, b"identique", "b.jpg")
    envoyer(client, b"unique", "c.jpg")
    reponse = client.get("/duplicates")
    assert reponse.status_code == 200
    assert len(reponse.json) == 1
    assert sorted(p["nom"] for p in reponse.json[0]["photos"]) == ["a.jpg", "b.jpg"]


def test_pas_de_doublons(client):
    envoyer(client, b"un", "a.jpg")
    assert client.get("/duplicates").json == []


def test_comparaison_identiques(client):
    a = envoyer(client, b"meme", "a.jpg").json["id"]
    b = envoyer(client, b"meme", "b.jpg").json["id"]
    reponse = client.get(f"/compare?a={a}&b={b}")
    assert reponse.status_code == 200
    assert reponse.json["identiques"] is True
    assert reponse.json["difference_taille"] == 0


def test_comparaison_differentes(client):
    a = envoyer(client, b"court", "a.jpg").json["id"]
    b = envoyer(client, b"beaucoup plus long", "b.png").json["id"]
    reponse = client.get(f"/compare?a={a}&b={b}")
    assert reponse.json["identiques"] is False
    assert reponse.json["meme_type"] is False
    assert reponse.json["difference_taille"] == len(b"beaucoup plus long") - len(b"court")


def test_comparaison_parametres_invalides(client):
    assert client.get("/compare").status_code == 400
    assert client.get("/compare?a=1&b=2").status_code == 400


def test_comparaison_photo_inconnue(client):
    a = envoyer(client).json["id"]
    assert client.get(f"/compare?a={a}&b={uuid.uuid4()}").status_code == 404


# Cache et pannes

def test_pas_de_cache_par_defaut(client):
    assert client.get("/photos").headers["Cache-Control"] == "no-store"
    assert client.get("/").headers["Cache-Control"] == "no-store"


def test_base_indisponible(client, monkeypatch):
    def en_panne():
        raise psycopg.OperationalError("connexion refusée")

    monkeypatch.setattr(db, "list_photos", en_panne)
    assert client.get("/photos").status_code == 503
    assert client.get("/health").status_code == 200


# Routage

def test_routage_deterministe():
    empreinte = db.sha256_hex(b"photo4")
    assert db.shard_for(empreinte) == 0
    assert db.shard_for(db.sha256_hex(b"photo1")) == 1
    assert db.shard_for(empreinte) == db.shard_for(empreinte)
