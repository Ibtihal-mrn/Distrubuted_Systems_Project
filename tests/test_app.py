import socket

from app import app


def test_health():
    client = app.test_client()
    response = client.get("/health")
    assert response.status_code == 200
    assert response.data == b"ok"


def test_version(monkeypatch):
    """/version renvoie pod et version (utilisé par watch.sh) ; "/" sert maintenant la page de connexion."""
    monkeypatch.setenv("APP_VERSION", "test-1")
    client = app.test_client()
    response = client.get("/version")
    assert response.status_code == 200
    assert response.json == {
        "message": "Hello to this photo-storage app",
        "pod": socket.gethostname(),
        "version": "test-1",
    }


def test_pages_html():
    """Chaque page est servie sans connexion (c'est le JavaScript qui redirige si besoin)."""
    client = app.test_client()
    for chemin in ("/", "/galerie", "/mes-albums", "/album"):
        reponse = client.get(chemin)
        assert reponse.status_code == 200, chemin
        assert reponse.mimetype == "text/html", chemin
        reponse.close()   # libère le fichier ouvert par send_static_file


def test_failure():
    client = app.test_client()
    response = client.get("/none")
    assert response.status_code == 404
