import socket
from app import app 

# test cases for the app.py file

def test_health():
    client = app.test_client()
    response = client.get("/health")
    assert response.status_code == 200 
    assert response.data == b"ok"

def test_home():
    client = app.test_client()
    response = client.get("/")
    assert response.status_code == 200 
    assert response.json == {"message" : "Welcome to this photo-storage app", "pod": socket.gethostname()}

def test_failure():
    client = app.test_client()
    response = client.get("/none")
    assert response.status_code == 404


