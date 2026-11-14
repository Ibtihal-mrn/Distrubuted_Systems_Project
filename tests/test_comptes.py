"""Tests de l'inscription, de la connexion et de la session."""


def test_inscription_puis_me(anonyme):
    reponse = anonyme.post("/register", json={"email": "Nouveau@Example.com", "mot_de_passe": "motdepasse1"})
    assert reponse.status_code == 201
    assert reponse.json["email"] == "nouveau@example.com"   # email normalisé en minuscules
    # Le cookie de session posé par /register permet d'appeler /me
    assert anonyme.get("/me").json["email"] == "nouveau@example.com"


def test_inscription_email_invalide(anonyme):
    assert anonyme.post("/register", json={"email": "pas-un-email", "mot_de_passe": "motdepasse1"}).status_code == 400


def test_inscription_mot_de_passe_trop_court(anonyme):
    assert anonyme.post("/register", json={"email": "a@b.c", "mot_de_passe": "court"}).status_code == 400


def test_inscription_email_deja_pris(client, anonyme):
    reponse = anonyme.post("/register", json={"email": "alice@example.com", "mot_de_passe": "motdepasse1"})
    assert reponse.status_code == 409


def test_connexion_correcte(client, anonyme):
    reponse = anonyme.post("/login", json={"email": "alice@example.com", "mot_de_passe": "motdepasse1"})
    assert reponse.status_code == 200
    assert anonyme.get("/me").status_code == 200


def test_connexion_message_identique_si_email_inconnu_ou_mot_de_passe_faux(client, anonyme):
    faux_mdp = anonyme.post("/login", json={"email": "alice@example.com", "mot_de_passe": "mauvais-mdp"})
    inconnu = anonyme.post("/login", json={"email": "personne@example.com", "mot_de_passe": "motdepasse1"})
    assert faux_mdp.status_code == inconnu.status_code == 401
    assert faux_mdp.json == inconnu.json   # on ne révèle pas quels emails ont un compte


def test_me_sans_connexion(anonyme):
    assert anonyme.get("/me").status_code == 401


def test_deconnexion(client):
    assert client.get("/me").status_code == 200
    assert client.post("/logout").status_code == 204
    assert client.get("/me").status_code == 401
