"""Tests des albums : création, réglages (PATCH), membres, droits d'accès, photos rangées."""
import uuid


def creer(client, nom="Vacances", partage=False):
    """Crée un album et renvoie son identifiant."""
    reponse = client.post("/albums", json={"nom": nom, "partage": partage})
    assert reponse.status_code == 201
    return reponse.json["id"]


def id_de(client, email_attendu):
    """Identifiant d'un utilisateur, lu via /me."""
    reponse = client.get("/me")
    assert reponse.json["email"] == email_attendu
    return reponse.json["id"]


# Création et liste

def test_albums_proteges_sans_connexion(anonyme):
    assert anonyme.get("/albums").status_code == 401
    assert anonyme.post("/albums", json={"nom": "x"}).status_code == 401
    assert anonyme.patch(f"/albums/{uuid.uuid4()}", json={"nom": "x"}).status_code == 401
    assert anonyme.delete(f"/albums/{uuid.uuid4()}/membres/{uuid.uuid4()}").status_code == 401


def test_creation_et_liste(client):
    creer(client, "Vacances")
    albums = client.get("/albums").json
    assert [a["nom"] for a in albums] == ["Vacances"]
    assert albums[0]["partage"] is False
    assert albums[0]["est_proprietaire"] is True


def test_creation_nom_invalide(client):
    assert client.post("/albums", json={"nom": "  "}).status_code == 400
    assert client.post("/albums", json={"nom": "x" * 101}).status_code == 400


# Réglages d'un album (PATCH)

def test_renommer(client):
    album_id = creer(client, "Ancien")
    assert client.patch(f"/albums/{album_id}", json={"nom": "Nouveau"}).status_code == 204
    assert client.get(f"/albums/{album_id}").json["album"]["nom"] == "Nouveau"


def test_changer_le_partage_sans_toucher_au_nom(client):
    album_id = creer(client, "Garde-moi")
    assert client.patch(f"/albums/{album_id}", json={"partage": True}).status_code == 204
    album = client.get(f"/albums/{album_id}").json["album"]
    assert album["partage"] is True
    assert album["nom"] == "Garde-moi"


def test_modifier_refuse_au_non_proprietaire(client, autre):
    album_id = creer(client, "A moi", partage=True)
    client.post(f"/albums/{album_id}/membres", json={"email": "bob@example.com"})
    # Même membre de l'album, bob ne peut pas le modifier : 404 comme si l'album n'existait pas
    assert autre.patch(f"/albums/{album_id}", json={"nom": "Pirate"}).status_code == 404
    assert client.get(f"/albums/{album_id}").json["album"]["nom"] == "A moi"


def test_modifier_valeurs_invalides(client):
    album_id = creer(client)
    assert client.patch(f"/albums/{album_id}", json={"partage": "oui"}).status_code == 400
    assert client.patch(f"/albums/{album_id}", json={"nom": "x" * 101}).status_code == 400
    assert client.patch("/albums/pas-un-uuid", json={"nom": "x"}).status_code == 400
    assert client.patch(f"/albums/{uuid.uuid4()}", json={"nom": "x"}).status_code == 404


def test_passer_en_prive_retire_les_membres(client, autre):
    album_id = creer(client, partage=True)
    client.post(f"/albums/{album_id}/membres", json={"email": "bob@example.com"})
    assert len(client.get(f"/albums/{album_id}").json["membres"]) == 1
    client.patch(f"/albums/{album_id}", json={"partage": False})
    assert client.get(f"/albums/{album_id}").json["membres"] == []
    assert autre.get(f"/albums/{album_id}").status_code == 404   # bob a perdu l'accès


# Membres

def test_ajouter_un_membre(client, autre):
    album_id = creer(client, partage=True)
    assert client.post(f"/albums/{album_id}/membres", json={"email": "bob@example.com"}).status_code == 204
    membres = client.get(f"/albums/{album_id}").json["membres"]
    assert [m["email"] for m in membres] == ["bob@example.com"]


def test_ajouter_membre_album_prive_refuse(client, autre):
    album_id = creer(client, partage=False)
    assert client.post(f"/albums/{album_id}/membres", json={"email": "bob@example.com"}).status_code == 403


def test_ajouter_membre_email_inconnu(client):
    album_id = creer(client, partage=True)
    assert client.post(f"/albums/{album_id}/membres", json={"email": "personne@example.com"}).status_code == 404


def test_retirer_un_membre(client, autre):
    album_id = creer(client, partage=True)
    client.post(f"/albums/{album_id}/membres", json={"email": "bob@example.com"})
    bob_id = id_de(autre, "bob@example.com")
    assert client.delete(f"/albums/{album_id}/membres/{bob_id}").status_code == 204
    assert client.get(f"/albums/{album_id}").json["membres"] == []
    assert autre.get(f"/albums/{album_id}").status_code == 404


def test_retirer_membre_refuse_au_non_proprietaire(client, autre):
    album_id = creer(client, partage=True)
    client.post(f"/albums/{album_id}/membres", json={"email": "bob@example.com"})
    bob_id = id_de(autre, "bob@example.com")
    assert autre.delete(f"/albums/{album_id}/membres/{bob_id}").status_code == 404
    assert len(client.get(f"/albums/{album_id}").json["membres"]) == 1


def test_retirer_membre_inconnu_ou_id_invalide(client):
    album_id = creer(client, partage=True)
    assert client.delete(f"/albums/{album_id}/membres/{uuid.uuid4()}").status_code == 404
    assert client.delete(f"/albums/{album_id}/membres/xyz").status_code == 400


# Visibilité

def test_la_liste_des_membres_est_reservee_au_proprietaire(client, autre):
    album_id = creer(client, partage=True)
    client.post(f"/albums/{album_id}/membres", json={"email": "bob@example.com"})
    vue_bob = autre.get(f"/albums/{album_id}")
    assert vue_bob.status_code == 200
    assert vue_bob.json["album"]["est_proprietaire"] is False
    assert vue_bob.json["membres"] == []


def test_album_prive_invisible_pour_les_autres(client, autre):
    album_id = creer(client, partage=False)
    assert autre.get(f"/albums/{album_id}").status_code == 404
    assert autre.get("/albums").json == []


def test_album_partage_visible_dans_la_liste_du_membre(client, autre):
    album_id = creer(client, "Commun", partage=True)
    client.post(f"/albums/{album_id}/membres", json={"email": "bob@example.com"})
    albums = autre.get("/albums").json
    assert [a["nom"] for a in albums] == ["Commun"]
    assert albums[0]["est_proprietaire"] is False


# Photos dans un album

def test_ranger_une_photo_et_la_voir_dans_l_album(client, envoyer):
    photo_id = envoyer(client, b"abc", "a.jpg").json["id"]
    album_id = creer(client)
    assert client.post(f"/albums/{album_id}/photos", json={"photo_id": photo_id}).status_code == 204
    assert [p["id"] for p in client.get(f"/albums/{album_id}").json["photos"]] == [photo_id]


def test_ranger_la_photo_d_un_autre_refuse(client, autre, envoyer):
    photo_bob = envoyer(autre, b"bob", "b.jpg").json["id"]
    album_id = creer(client, partage=True)
    assert client.post(f"/albums/{album_id}/photos", json={"photo_id": photo_bob}).status_code == 404


def test_membre_voit_les_photos_d_un_album_partage(client, autre, envoyer):
    photo_id = envoyer(client, b"abc", "a.jpg").json["id"]
    album_id = creer(client, partage=True)
    client.post(f"/albums/{album_id}/photos", json={"photo_id": photo_id})
    assert autre.get(f"/photos/{photo_id}").status_code == 404     # pas encore membre
    client.post(f"/albums/{album_id}/membres", json={"email": "bob@example.com"})
    assert autre.get(f"/photos/{photo_id}").status_code == 200     # membre : accès via l'album
    assert autre.get("/photos").json == []                          # mais ce n'est pas SA photo


def test_retirer_une_photo_de_l_album_ne_la_supprime_pas(client, envoyer):
    photo_id = envoyer(client, b"abc", "a.jpg").json["id"]
    album_id = creer(client)
    client.post(f"/albums/{album_id}/photos", json={"photo_id": photo_id})
    assert client.delete(f"/albums/{album_id}/photos/{photo_id}").status_code == 204
    assert client.get(f"/albums/{album_id}").json["photos"] == []
    assert client.get(f"/photos/{photo_id}").status_code == 200


def test_supprimer_une_photo_la_retire_des_albums(client, envoyer):
    photo_id = envoyer(client, b"abc", "a.jpg").json["id"]
    album_id = creer(client)
    client.post(f"/albums/{album_id}/photos", json={"photo_id": photo_id})
    client.delete(f"/photos/{photo_id}")
    assert client.get(f"/albums/{album_id}").json["photos"] == []


def test_supprimer_un_album_garde_les_photos(client, envoyer):
    photo_id = envoyer(client, b"abc", "a.jpg").json["id"]
    album_id = creer(client)
    client.post(f"/albums/{album_id}/photos", json={"photo_id": photo_id})
    assert client.delete(f"/albums/{album_id}").status_code == 204
    assert client.get(f"/albums/{album_id}").status_code == 404
    assert client.get(f"/photos/{photo_id}").status_code == 200


def test_supprimer_un_album_refuse_au_non_proprietaire(client, autre):
    album_id = creer(client, partage=True)
    client.post(f"/albums/{album_id}/membres", json={"email": "bob@example.com"})
    assert autre.delete(f"/albums/{album_id}").status_code == 404
    assert client.get(f"/albums/{album_id}").status_code == 200
