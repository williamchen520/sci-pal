"""
Sci-Pal Research Assistant - Main Entry
"""
from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
import os
from config.settings import HOST, PORT, DEBUG, UPLOAD_FOLDER, BASE_DIR

def create_app():
    app = Flask(__name__, static_folder='frontend', static_url_path='')
    CORS(app)
    
    # App config
    app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
    app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024  # 100MB
    
    # Ensure upload directory exists
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    
    # Initialize database
    from database.init_db import init_database
    init_database()
    
    # Register blueprints
    from routes.paper_routes import paper_bp
    from routes.search_routes import search_bp
    from routes.ai_routes import ai_bp
    
    app.register_blueprint(paper_bp, url_prefix="/api/papers")
    app.register_blueprint(search_bp, url_prefix="/api/search")
    app.register_blueprint(ai_bp, url_prefix="/api/ai")
    
    # Serve frontend
    @app.route("/")
    def index():
        return send_from_directory('frontend', 'index.html')
    
    @app.route("/api/health")
    def health_check():
        return jsonify({
            "status": "ok",
            "service": "sci-pal",
            "version": "v0.6.0"
        })
    
    return app

if __name__ == "__main__":
    app = create_app()
    app.run(host=HOST, port=PORT, debug=DEBUG)
