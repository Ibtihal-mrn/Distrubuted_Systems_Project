import socket
from app import app 

# test cases for the app.py file ttiji 

def test_health():
    client = app.test_client()
    response = client.get("/health")
    assert response.status_code == 200 
    assert response.data == b"ok"

def test_home(monkeypatch):
    monkeypatch.setenv("APP_VERSION", "test-1")
    client = app.test_client()
    response = client.get("/")
    assert response.status_code == 200
    assert response.json == {
        "message": "Hello to this photo-storage app",
        "pod": socket.gethostname(),
        "version": "test-1",
    }

def test_failure():
    client = app.test_client()
    response = client.get("/none")
    assert response.status_code == 404


