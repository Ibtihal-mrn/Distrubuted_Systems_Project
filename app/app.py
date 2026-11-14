"""Service de photos : routes HTTP au-dessus de la couche d'accès aux shards (db.py)
et de la couche comptes/albums (comptes.py)."""
import functools
import mimetypes
import os
import socket
import uuid

import psycopg
from flask import Flask, jsonify, request, session

import comptes
import db

app = Flask(__name__)

# Taille maximale d'une requête : au-delà, Flask répond automatiquement 413.
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024   # 10 Mo

#  Sessions 
# SECRET_KEY signe le cookie de session. Elle doit être IDENTIQUE sur tous les pods
# (elle vient d'un Secret Kubernetes). Si elle manque, on en génère une aléatoire :
# l'app démarre, mais les connexions ne tiennent pas d'un pod à l'autre. C'est un
# échec visible, alors qu'une clé par défaut connue permettrait de forger un cookie.
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or os.urandom(32).hex()
app.config["SESSION_COOKIE_HTTPONLY"] = True    # le JavaScript de la page ne peut pas lire le cookie
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"   # le cookie n'est pas envoyé par les requêtes POST d'un autre site
# SESSION_COOKIE_SECURE resterait à False : on est en HTTP (http://*.localhost).
# Derrière HTTPS, il faudrait le passer à True.
app.config["PERMANENT_SESSION_LIFETIME"] = 7 * 24 * 3600   # le cookie dure 7 jours (en secondes)

# Formats acceptés, déterminés à partir de l'extension du fichier.
FORMATS = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".heic": "image/heic",
    ".heif": "image/heif",
}


def erreur(message, code):
    """Réponse JSON d'erreur : {"erreur": "..."} avec le code HTTP donné."""
    return jsonify(erreur=message), code


def id_valide(texte):
    """True si le texte est un identifiant UUID valide."""
    try:
        uuid.UUID(texte)
        return True
    except (ValueError, AttributeError):
        return False


def corps_json():
    """Corps JSON de la requête, sous forme de dict (dict vide si absent ou invalide)."""
    donnees = request.get_json(silent=True)
    return donnees if isinstance(donnees, dict) else {}


def texte(donnees, cle):
    """Valeur textuelle d'une clé du corps JSON, ou chaîne vide si absente ou pas du texte."""
    valeur = donnees.get(cle)
    return valeur if isinstance(valeur, str) else ""


#  Authentification 

def utilisateur_courant():
    """Identifiant (texte) de l'utilisateur connecté, ou None.

    Le cookie est signé avec SECRET_KEY : si quelqu'un le modifie, Flask le rejette
    et session est vide.
    """
    return session.get("user_id")


def connexion_requise(vue):
    """Décorateur : répond 401 si personne n'est connecté, sinon exécute la route."""
    @functools.wraps(vue)
    def enveloppe(*args, **kwargs):
        if utilisateur_courant() is None:
            return erreur("connexion requise", 401)
        return vue(*args, **kwargs)
    return enveloppe


def ouvrir_session(utilisateur):
    """Connecte l'utilisateur : on repart d'une session vide, puis on y met son identifiant."""
    session.clear()
    session["user_id"] = str(utilisateur["id"])
    session.permanent = True   # le cookie survit à la fermeture du navigateur (7 jours)


def peut_voir_photo(info, user_id):
    """Une photo est visible par son propriétaire, ou par un membre d'un album qui la contient."""
    return info["user_id"] == user_id or comptes.photo_visible_via_album(info["id"], user_id)


def album_vers_json(album):
    """Album (ligne SQL) -> dict JSON : identifiants en texte, date au format ISO."""
    return {
        "id": str(album["id"]),
        "nom": album["nom"],
        "partage": album["partage"],
        "date_creation": album["date_creation"].isoformat(),
        # La ligne renvoyée à la création n'a pas ce champ : le créateur est propriétaire.
        "est_proprietaire": album.get("est_proprietaire", True),
    }


@app.after_request
def entetes_cache(reponse):
    """Par défaut, rien ne doit être mis en cache (Varnish ou navigateur).

    Les routes qui peuvent l'être (le contenu d'une photo) définissent
    leur propre en-tête, que setdefault ne remplace pas.
    """
    reponse.headers.setdefault("Cache-Control", "no-store")
    return reponse


@app.errorhandler(psycopg.OperationalError)
def base_indisponible(_erreur):
    """Si une base ne répond pas : 503 (service indisponible), pas un plantage."""
    return erreur("base de données indisponible", 503)


@app.errorhandler(413)
def fichier_trop_gros(_erreur):
    return erreur("fichier trop volumineux (maximum 10 Mo)", 413)


#  Pages et sondes 

@app.route("/")
@app.route("/")
def page_connexion():
    """Première page de l'application : connexion et création de compte."""
    return app.send_static_file("connexion.html")


@app.route("/galerie")
def page_galerie():
    """Mes photos : envoi, comparaison, doublons, rangement dans les albums."""
    return app.send_static_file("galerie.html")


@app.route("/mes-albums")
def page_albums():
    """Liste de mes albums et création d'un album."""
    return app.send_static_file("albums.html")


@app.route("/album")
def page_album():
    """Détail d'un album (l'identifiant est dans l'adresse : /album?id=...)."""
    return app.send_static_file("album.html")


@app.route("/version")
def version():
    """Ancien contenu de "/" : pod et version, utilisé par watch.sh pendant un déploiement."""
    return jsonify(message="Hello to this photo-storage app",
                   pod=socket.gethostname(),
                   version=os.environ.get("APP_VERSION", "dev"))


@app.route("/health")
def health():
    # Volontairement sans accès aux bases : sert de sonde de disponibilité.
    return "ok"


#  Comptes 

@app.route("/register", methods=["POST"])
def inscription():
    """Crée un compte et connecte l'utilisateur. Corps JSON : {"email", "mot_de_passe"}."""
    donnees = corps_json()
    email = texte(donnees, "email").strip().lower()
    mot_de_passe = texte(donnees, "mot_de_passe")
    if "@" not in email or len(email) > 254:
        return erreur("email invalide", 400)
    if len(mot_de_passe) < 8:
        return erreur("mot de passe trop court (8 caractères minimum)", 400)

    utilisateur = comptes.creer_utilisateur(email, mot_de_passe)
    if utilisateur is None:
        return erreur("un compte existe déjà avec cet email", 409)
    ouvrir_session(utilisateur)
    return jsonify(id=str(utilisateur["id"]), email=utilisateur["email"]), 201


@app.route("/login", methods=["POST"])
def connexion():
    """Connecte l'utilisateur. Corps JSON : {"email", "mot_de_passe"}."""
    donnees = corps_json()
    utilisateur = comptes.verifier_utilisateur(texte(donnees, "email"), texte(donnees, "mot_de_passe"))
    if utilisateur is None:
        # Même message si l'email n'existe pas ou si le mot de passe est faux :
        # on ne révèle pas quels emails ont un compte.
        return erreur("email ou mot de passe incorrect", 401)
    ouvrir_session(utilisateur)
    return jsonify(id=str(utilisateur["id"]), email=utilisateur["email"])


@app.route("/logout", methods=["POST"])
def deconnexion():
    session.clear()
    return "", 204


@app.route("/me")
@connexion_requise
def moi():
    """Utilisateur connecté. La page l'appelle au chargement pour choisir connexion ou galerie."""
    utilisateur = comptes.get_utilisateur(utilisateur_courant())
    if utilisateur is None:   # cookie valide mais compte disparu
        session.clear()
        return erreur("connexion requise", 401)
    return jsonify(id=str(utilisateur["id"]), email=utilisateur["email"])


#  Photos (connexion obligatoire) 

@app.route("/photos", methods=["POST"])
@connexion_requise
def envoyer_photo():
    """Reçoit une photo (formulaire multipart, champ "photo") et l'enregistre."""
    fichier = request.files.get("photo")
    if fichier is None or fichier.filename == "":
        return erreur("aucun fichier reçu (champ 'photo' attendu)", 400)

    # Le type est déduit de l'extension ; à défaut, on regarde ce que le client annonce.
    extension = os.path.splitext(fichier.filename)[1].lower()
    type_mime = FORMATS.get(extension) or mimetypes.guess_type(fichier.filename)[0]
    if type_mime not in FORMATS.values():
        return erreur("format non accepté (jpg, png, webp, gif, heic)", 415)

    contenu = fichier.read()   # les octets du fichier
    if len(contenu) == 0:
        return erreur("fichier vide", 400)

    photo = db.add_photo(fichier.filename, type_mime, contenu, utilisateur_courant())
    if photo["doublons"]:
        photo["avertissement"] = "une photo identique existe déjà"
    return jsonify(photo), 201


@app.route("/photos", methods=["GET"])
@connexion_requise
def lister_photos():
    """Mes photos (celles dont je suis propriétaire)."""
    return jsonify(db.list_photos(utilisateur_courant()))


@app.route("/photos/<photo_id>", methods=["GET"])
@connexion_requise
def lire_photo(photo_id):
    """Renvoie l'image elle-même, avec son type MIME."""
    if not id_valide(photo_id):
        return erreur("identifiant invalide", 400)
    info = db.get_info(photo_id)
    # Même réponse 404 si la photo n'existe pas ou si elle n'est pas visible par cet
    # utilisateur : on ne révèle pas l'existence d'une photo privée.
    if info is None or not peut_voir_photo(info, utilisateur_courant()):
        return erreur("photo introuvable", 404)
    _nom, type_mime, contenu = db.get_photo(photo_id)
    return contenu, 200, {
        "Content-Type": type_mime,
        # "private" : seul le navigateur de l'utilisateur peut garder cette réponse, pas
        # un cache partagé comme Varnish. Elle dépend de qui est connecté.
        "Cache-Control": "private, max-age=60",
    }


@app.route("/photos/<photo_id>", methods=["DELETE"])
@connexion_requise
def supprimer_photo(photo_id):
    """Supprime une de MES photos."""
    if not id_valide(photo_id):
        return erreur("identifiant invalide", 400)
    if not db.delete_photo(photo_id, utilisateur_courant()):
        return erreur("photo introuvable", 404)
    comptes.oublier_photo(photo_id)   # retire aussi la photo de tous les albums
    return "", 204


@app.route("/duplicates")
@connexion_requise
def doublons():
    """Groupes de MES photos au contenu identique."""
    return jsonify(db.find_duplicates(utilisateur_courant()))


@app.route("/compare")
@connexion_requise
def comparer():
    """Compare deux photos : /compare?a=<id>&b=<id>."""
    a = request.args.get("a", "")
    b = request.args.get("b", "")
    if not id_valide(a) or not id_valide(b):
        return erreur("paramètres 'a' et 'b' attendus (identifiants valides)", 400)

    info_a = db.get_info(a)
    info_b = db.get_info(b)
    moi_id = utilisateur_courant()
    if (info_a is None or info_b is None
            or not peut_voir_photo(info_a, moi_id) or not peut_voir_photo(info_b, moi_id)):
        return erreur("photo introuvable", 404)

    return jsonify(
        identiques=info_a["sha256"] == info_b["sha256"],
        meme_type=info_a["type_mime"] == info_b["type_mime"],
        difference_taille=abs(info_a["taille"] - info_b["taille"]),
        a=info_a,
        b=info_b,
    )


#  Albums (connexion obligatoire) 

@app.route("/albums", methods=["POST"])
@connexion_requise
def creer_album():
    """Crée un album. Corps JSON : {"nom": "...", "partage": true|false}."""
    donnees = corps_json()
    nom = texte(donnees, "nom").strip()
    if not nom or len(nom) > 100:
        return erreur("nom d'album invalide (1 à 100 caractères)", 400)
    partage = donnees.get("partage") is True   # seul le booléen true partage l'album
    album = comptes.creer_album(utilisateur_courant(), nom, partage)
    return jsonify(album_vers_json(album)), 201


@app.route("/albums", methods=["GET"])
@connexion_requise
def lister_albums():
    """Mes albums, plus les albums partagés dont je suis membre."""
    return jsonify([album_vers_json(a) for a in comptes.lister_albums(utilisateur_courant())])


@app.route("/albums/<album_id>", methods=["GET"])
@connexion_requise
def lire_album(album_id):
    """Un album et ses photos."""
    if not id_valide(album_id):
        return erreur("identifiant invalide", 400)
    album = comptes.get_album(album_id, utilisateur_courant())
    if album is None:   # n'existe pas OU pas d'accès : même réponse
        return erreur("album introuvable", 404)
    photos = db.list_photos_by_ids(comptes.ids_photos_album(album_id))
    # Seul le propriétaire voit la liste des membres ; les autres reçoivent une liste vide.
    membres = comptes.lister_membres(album_id) if album["est_proprietaire"] else []
    return jsonify(album=album_vers_json(album), photos=photos, membres=membres)

@app.route("/albums/<album_id>", methods=["DELETE"])
@connexion_requise
def supprimer_album(album_id):
    """Supprime un de MES albums (les photos elles-mêmes ne sont pas supprimées)."""
    if not id_valide(album_id):
        return erreur("identifiant invalide", 400)
    if not comptes.supprimer_album(album_id, utilisateur_courant()):
        return erreur("album introuvable", 404)
    return "", 204


@app.route("/albums/<album_id>/membres", methods=["POST"])
@connexion_requise
def ajouter_membre(album_id):
    """Ajoute un membre à un de mes albums partagés. Corps JSON : {"email": "..."}."""
    if not id_valide(album_id):
        return erreur("identifiant invalide", 400)
    resultat = comptes.ajouter_membre(album_id, utilisateur_courant(), texte(corps_json(), "email"))
    if resultat == "interdit":
        return erreur("album introuvable, privé, ou vous n'en êtes pas propriétaire", 403)
    if resultat == "inconnu":
        return erreur("aucun compte avec cet email", 404)
    return "", 204


@app.route("/albums/<album_id>/photos", methods=["POST"])
@connexion_requise
def ajouter_photo_album(album_id):
    """Range une de MES photos dans un album accessible. Corps JSON : {"photo_id": "..."}."""
    photo_id = texte(corps_json(), "photo_id")
    if not id_valide(album_id) or not id_valide(photo_id):
        return erreur("identifiants invalides", 400)
    info = db.get_info(photo_id)
    # On ne range dans un album que ses propres photos : sinon on pourrait y glisser
    # (et donc rendre visible) la photo privée de quelqu'un d'autre.
    if info is None or info["user_id"] != utilisateur_courant():
        return erreur("photo introuvable", 404)
    if not comptes.ajouter_photo_a_album(album_id, utilisateur_courant(), photo_id):
        return erreur("album introuvable", 404)
    return "", 204


@app.route("/albums/<album_id>/photos/<photo_id>", methods=["DELETE"])
@connexion_requise
def retirer_photo_album(album_id, photo_id):
    """Retire une photo d'un de MES albums (la photo n'est pas supprimée)."""
    if not id_valide(album_id) or not id_valide(photo_id):
        return erreur("identifiants invalides", 400)
    if not comptes.retirer_photo_de_album(album_id, utilisateur_courant(), photo_id):
        return erreur("introuvable", 404)
    return "", 204

@app.route("/albums/<album_id>", methods=["PATCH"])
@connexion_requise
def modifier_album(album_id):
    """Renomme un de MES albums et/ou change son partage. Corps JSON : {"nom": "...", "partage": true|false}."""
    if not id_valide(album_id):
        return erreur("identifiant invalide", 400)
    donnees = corps_json()
    nom = texte(donnees, "nom").strip() or None   # None = on garde le nom actuel
    if nom and len(nom) > 100:
        return erreur("nom d'album invalide (1 à 100 caractères)", 400)
    partage = donnees.get("partage")              # None = on ne change pas le partage
    if partage is not None and not isinstance(partage, bool):
        return erreur("partage doit être vrai ou faux", 400)
    if not comptes.modifier_album(album_id, utilisateur_courant(), nom, partage):
        return erreur("album introuvable", 404)   # n'existe pas OU je n'en suis pas propriétaire
    return "", 204


@app.route("/albums/<album_id>/membres/<membre_id>", methods=["DELETE"])
@connexion_requise
def retirer_membre(album_id, membre_id):
    """Retire un membre d'un de MES albums partagés."""
    if not id_valide(album_id) or not id_valide(membre_id):
        return erreur("identifiants invalides", 400)
    if not comptes.retirer_membre(album_id, utilisateur_courant(), membre_id):
        return erreur("introuvable", 404)
    return "", 204