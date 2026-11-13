from flask import Flask, jsonify
import socket
import os 
import socket 

from flask import Flask, jsonify

app = Flask(__name__)

@app.route('/')
def home():
    return jsonify(message="Hello to this photo-storage app",
                   pod=socket.gethostname(),
                   version=os.environ.get("APP_VERSION", "dev"))


@app.route('/health')
def health():
    return "ok"

