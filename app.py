import os
import uuid
import time
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

VALID_KEYS = {
    "citadel_test_key_001": "pro",
    "citadel_free_key_001": "free",
}

@app.route('/v1/health', methods=['GET'])
def health():
    return jsonify({
        "status": "healthy",
        "version": "v1",
        "timestamp": time.time()
    })

@app.route('/v1/infer', methods=['POST'])
def infer():
    auth = request.headers.get('Authorization', '')
    if not auth.startswith('Bearer '):
        return jsonify({"error": "Missing Authorization header"}), 401
    
    key = auth[7:]
    if key not in VALID_KEYS:
        return jsonify({"error": "Invalid API key"}), 401
    
    if not request.is_json:
        return jsonify({"error": "Content-Type must be application/json"}), 415
    
    data = request.get_json()
    events = data.get('events', [])
    
    if not events:
        return jsonify({"error": "events array required"}), 400
    
    mean = sum(events) / len(events)
    
    return jsonify({
        "request_id": str(uuid.uuid4()),
        "status": "success",
        "tier": VALID_KEYS[key],
        "result": {"mean": round(mean, 3), "count": len(events)}
    })

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port)
