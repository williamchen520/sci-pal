"""Sci-Pal Research Assistant —— 旧版入口（已废弃，勿运行）。

🔴 不要把它当服务入口：
    1. 端口冲突：config/settings.py 的 PORT = 5000，与 api_server.py 抢同一端口，
       两者不可能同时运行。
    2. 路由残缺：这里只注册了 3 个 blueprint（papers / search / ai）；
       /api/review/*、/api/tasks/*、/api/abstracts/*、/api/graph/*、/api/qa/* 等
       在 api_server.py 上存在的路由，这里一个都没有 → 用它会大面积 404。
    3. routes/ 这套 blueprint 体系整体已被 api_server.py 取代
       （writing_bp 甚至没有任何入口注册，是孤儿）。

主入口：python api_server.py
处置结论：C-1 结论 A「确认废弃」；文件删除需用户点头（见 docs/工单-C-app-py入口.md）。
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
