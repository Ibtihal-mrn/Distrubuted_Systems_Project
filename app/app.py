"""Service de photos : routes HTTP au-dessus de la couche d'accès aux shards (db.py)."""
import mimetypes
import os
import socket
import uuid

import psycopg
from flask import Flask, jsonify, request

import db

app = Flask(__name__)

# Taille maximale d'une requête : au-delà, Flask répond automatiquement 413.
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024   # 10 Mo

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


# Routes

@app.route("/")
def home():
    return jsonify(message="Hello to this photo-storage app",
                   pod=socket.gethostname(),
                   version=os.environ.get("APP_VERSION", "dev"))


@app.route("/health")
def health():
    # Volontairement sans accès aux bases : sert de sonde de disponibilité.
    return "ok"


@app.route("/photos", methods=["POST"])
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

    photo = db.add_photo(fichier.filename, type_mime, contenu)
    if photo["doublons"]:
        photo["avertissement"] = "une photo identique existe déjà"
    return jsonify(photo), 201


@app.route("/photos", methods=["GET"])
def lister_photos():
    return jsonify(db.list_photos())


@app.route("/photos/<photo_id>", methods=["GET"])
def lire_photo(photo_id):
    """Renvoie l'image elle-même, avec son type MIME."""
    if not id_valide(photo_id):
        return erreur("identifiant invalide", 400)
    resultat = db.get_photo(photo_id)
    if resultat is None:
        return erreur("photo introuvable", 404)
    _nom, type_mime, contenu = resultat
    return contenu, 200, {
        "Content-Type": type_mime,
        # Cache court : le contenu d'un identifiant ne change pas, mais une
        # photo supprimée ne doit pas rester servie trop longtemps.
        "Cache-Control": "public, max-age=60",
    }


@app.route("/photos/<photo_id>", methods=["DELETE"])
def supprimer_photo(photo_id):
    if not id_valide(photo_id):
        return erreur("identifiant invalide", 400)
    if not db.delete_photo(photo_id):
        return erreur("photo introuvable", 404)
    return "", 204


@app.route("/duplicates")
def doublons():
    """Groupes de photos au contenu identique."""
    return jsonify(db.find_duplicates())


@app.route("/compare")
def comparer():
    """Compare deux photos : /compare?a=<id>&b=<id>."""
    a = request.args.get("a", "")
    b = request.args.get("b", "")
    if not id_valide(a) or not id_valide(b):
        return erreur("paramètres 'a' et 'b' attendus (identifiants valides)", 400)

    info_a = db.get_info(a)
    info_b = db.get_info(b)
    if info_a is None or info_b is None:
        return erreur("photo introuvable", 404)

    return jsonify(
        identiques=info_a["sha256"] == info_b["sha256"],
        meme_type=info_a["type_mime"] == info_b["type_mime"],
        difference_taille=abs(info_a["taille"] - info_b["taille"]),
        a=info_a,
        b=info_b,
    )
