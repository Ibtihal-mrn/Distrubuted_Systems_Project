"""Tests des routes photos (connexion obligatoire, chaque photo appartient à un utilisateur).

Les bases sont remplacées par des versions en mémoire (voir conftest.py).
"""
import uuid

import psycopg

import db


# Connexion obligatoire

def test_routes_protegees_sans_connexion(anonyme):
    assert anonyme.get("/photos").status_code == 401
    assert anonyme.post("/photos").status_code == 401
    assert anonyme.get(f"/photos/{uuid.uuid4()}").status_code == 401
    assert anonyme.delete(f"/photos/{uuid.uuid4()}").status_code == 401
    assert anonyme.get("/duplicates").status_code == 401
    assert anonyme.get("/compare").status_code == 401


# Envoi

def test_envoi_valide(client, envoyer):
    reponse = envoyer(client, b"abc", "chat.jpg")
    assert reponse.status_code == 201
    assert reponse.json["nom"] == "chat.jpg"
    assert reponse.json["type_mime"] == "image/jpeg"
    assert reponse.json["taille"] == 3
    assert reponse.json["doublons"] == []


def test_envoi_sans_fichier(client):
    assert client.post("/photos").status_code == 400


def test_envoi_format_interdit(client, envoyer):
    assert envoyer(client, b"abc", "virus.exe").status_code == 415


def test_envoi_fichier_vide(client, envoyer):
    assert envoyer(client, b"", "vide.jpg").status_code == 400


def test_envoi_heic_accepte(client, envoyer):
    reponse = envoyer(client, b"abc", "iphone.HEIC")
    assert reponse.status_code == 201
    assert reponse.json["type_mime"] == "image/heic"


def test_envoi_trop_gros(client, envoyer, monkeypatch):
    from app import app
    monkeypatch.setitem(app.config, "MAX_CONTENT_LENGTH", 10)
    assert envoyer(client, b"x" * 100, "gros.jpg").status_code == 413


def test_envoi_doublon_signale(client, envoyer):
    envoyer(client, b"meme contenu", "a.jpg")
    reponse = envoyer(client, b"meme contenu", "b.jpg")
    assert reponse.status_code == 201
    assert len(reponse.json["doublons"]) == 1
    assert "avertissement" in reponse.json


def test_meme_contenu_chez_deux_utilisateurs_pas_un_doublon(client, autre, envoyer):
    envoyer(client, b"meme contenu", "a.jpg")
    reponse = envoyer(autre, b"meme contenu", "b.jpg")
    assert reponse.json["doublons"] == []


# Lecture et liste

def test_liste_ne_montre_que_mes_photos(client, autre, envoyer):
    envoyer(client, b"un", "un.jpg")
    envoyer(client, b"deux", "deux.png")
    envoyer(autre, b"trois", "trois.jpg")
    reponse = client.get("/photos")
    assert reponse.status_code == 200
    assert sorted(p["nom"] for p in reponse.json) == ["deux.png", "un.jpg"]
    assert "contenu" not in reponse.json[0]


def test_lecture_photo(client, envoyer):
    photo_id = envoyer(client, b"octets-image", "x.png").json["id"]
    reponse = client.get(f"/photos/{photo_id}")
    assert reponse.status_code == 200
    assert reponse.data == b"octets-image"
    assert reponse.headers["Content-Type"] == "image/png"
    # "private" : un cache partagé (Varnish) ne doit pas la garder, elle dépend de l'utilisateur
    assert reponse.headers["Cache-Control"] == "private, max-age=60"


def test_lecture_photo_privee_d_un_autre_est_introuvable(client, autre, envoyer):
    photo_id = envoyer(client, b"secret", "prive.jpg").json["id"]
    # 404 (et non 403) : on ne révèle pas que la photo existe
    assert autre.get(f"/photos/{photo_id}").status_code == 404


def test_lecture_id_invalide(client):
    assert client.get("/photos/pas-un-uuid").status_code == 400


def test_lecture_id_inconnu(client):
    assert client.get(f"/photos/{uuid.uuid4()}").status_code == 404


# Suppression

def test_suppression(client, envoyer):
    photo_id = envoyer(client).json["id"]
    assert client.delete(f"/photos/{photo_id}").status_code == 204
    assert client.get(f"/photos/{photo_id}").status_code == 404
    assert client.delete(f"/photos/{photo_id}").status_code == 404


def test_suppression_de_la_photo_d_un_autre_refusee(client, autre, envoyer):
    photo_id = envoyer(client).json["id"]
    assert autre.delete(f"/photos/{photo_id}").status_code == 404
    assert client.get(f"/photos/{photo_id}").status_code == 200   # toujours là


def test_suppression_id_invalide(client):
    assert client.delete("/photos/xyz").status_code == 400


# Doublons et comparaison

def test_doublons(client, envoyer):
    envoyer(client, b"identique", "a.jpg")
    envoyer(client, b"identique", "b.jpg")
    envoyer(client, b"unique", "c.jpg")
    reponse = client.get("/duplicates")
    assert reponse.status_code == 200
    assert len(reponse.json) == 1
    assert sorted(p["nom"] for p in reponse.json[0]["photos"]) == ["a.jpg", "b.jpg"]


def test_pas_de_doublons(client, envoyer):
    envoyer(client, b"un", "a.jpg")
    assert client.get("/duplicates").json == []


def test_doublons_seulement_parmi_mes_photos(client, autre, envoyer):
    envoyer(client, b"identique", "a.jpg")
    envoyer(autre, b"identique", "b.jpg")   # même contenu mais autre utilisateur
    assert client.get("/duplicates").json == []


def test_comparaison_identiques(client, envoyer):
    a = envoyer(client, b"meme", "a.jpg").json["id"]
    b = envoyer(client, b"meme", "b.jpg").json["id"]
    reponse = client.get(f"/compare?a={a}&b={b}")
    assert reponse.status_code == 200
    assert reponse.json["identiques"] is True
    assert reponse.json["difference_taille"] == 0


def test_comparaison_differentes(client, envoyer):
    a = envoyer(client, b"court", "a.jpg").json["id"]
    b = envoyer(client, b"beaucoup plus long", "b.png").json["id"]
    reponse = client.get(f"/compare?a={a}&b={b}")
    assert reponse.json["identiques"] is False
    assert reponse.json["meme_type"] is False
    assert reponse.json["difference_taille"] == len(b"beaucoup plus long") - len(b"court")


def test_comparaison_parametres_invalides(client):
    assert client.get("/compare").status_code == 400
    assert client.get("/compare?a=1&b=2").status_code == 400


def test_comparaison_photo_inconnue(client, envoyer):
    a = envoyer(client).json["id"]
    assert client.get(f"/compare?a={a}&b={uuid.uuid4()}").status_code == 404


def test_comparaison_photo_d_un_autre_refusee(client, autre, envoyer):
    a = envoyer(client, b"un", "a.jpg").json["id"]
    b = envoyer(autre, b"deux", "b.jpg").json["id"]
    assert client.get(f"/compare?a={a}&b={b}").status_code == 404


# Cache et pannes

def test_pas_de_cache_par_defaut(client):
    assert client.get("/photos").headers["Cache-Control"] == "no-store"
    assert client.get("/version").headers["Cache-Control"] == "no-store"


def test_base_indisponible(client, monkeypatch):
    def en_panne(user_id):
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
