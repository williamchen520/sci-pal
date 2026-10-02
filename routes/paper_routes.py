"""
Paper Management Routes
"""
import os
from flask import Blueprint, jsonify, request, current_app
from werkzeug.utils import secure_filename

paper_bp = Blueprint("papers", __name__)

@paper_bp.route("/", methods=["GET"])
def list_papers():
    """Get paper list"""
    import sqlite3
    from config.settings import DATABASE_PATH
    
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("SELECT paper_id, title, authors, journal, year, created_at FROM papers ORDER BY created_at DESC")
    papers = [dict(row) for row in cursor.fetchall()]
    total = len(papers)
    
    conn.close()
    
    return jsonify({
        "papers": papers,
        "total": total
    })

@paper_bp.route("/<paper_id>", methods=["GET"])
def get_paper(paper_id):
    """Get paper details"""
    from services.query.search_service import SearchService
    
    search_service = SearchService()
    paper = search_service.get_paper_details(paper_id)
    
    if not paper:
        return jsonify({"error": "Paper not found"}), 404
    
    return jsonify(paper)

@paper_bp.route("/upload", methods=["POST"])
def upload_paper():
    """Upload PDF paper and run parsing pipeline"""
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400

    if not file.filename.lower().endswith(".pdf"):
        return jsonify({"error": "Only PDF files are allowed"}), 400

    # Save the file
    filename = secure_filename(file.filename)
    upload_folder = current_app.config["UPLOAD_FOLDER"]
    os.makedirs(upload_folder, exist_ok=True)
    file_path = os.path.join(upload_folder, filename)
    file.save(file_path)

    print(f"📁 File saved to: {file_path}")

    # Run parsing pipeline
    try:
        from build_db.parsers.parser_orchestrator import ParserOrchestrator
        from build_db.db_writer import DatabaseWriter

        orchestrator = ParserOrchestrator()
        db_writer = DatabaseWriter()

        # Parse the paper
        parsed_result = orchestrator.parse_paper(file_path)

        # Insert into database
        success = db_writer.insert_paper(parsed_result)

        if success:
            return jsonify({
                "message": "Upload and parse successful",
                "paper_id": parsed_result["paper_id"],
                "filename": filename,
                "stats": {
                    "paragraphs": len(parsed_result["paragraphs"]),
                    "figures": len(parsed_result["figures"]),
                    "citations": len(parsed_result["citations"])
                }
            })
        else:
            return jsonify({"error": "Database insertion failed"}), 500

    except Exception as e:
        return jsonify({"error": f"Parse failed: {str(e)}"}), 500

# V26.0: 获取摘要详细内容
@paper_bp.route("/abstracts/<paper_id>", methods=["GET"])
def get_abstract(paper_id):
    """Get abstract details"""
    import sqlite3
    from config.settings import ABSTRACTS_DATABASE_PATH

    try:
        conn = sqlite3.connect(ABSTRACTS_DATABASE_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM abstracts WHERE paper_id = ?", (paper_id,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            return jsonify({"error": "Abstract not found"}), 404

        return jsonify(dict(row))
    except Exception as e:
        return jsonify({"error": f"Get abstract failed: {str(e)}"}), 500

# V26.0: 获取全文详细内容
@paper_bp.route("/<paper_id>/fulltext", methods=["GET"])
def get_fulltext(paper_id):
    """Get full text details"""
    import sqlite3
    from config.settings import DATABASE_PATH

    try:
        conn = sqlite3.connect(DATABASE_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # 获取论文基本信息
        cursor.execute("SELECT * FROM papers WHERE paper_id = ?", (paper_id,))
        paper = cursor.fetchone()
        if not paper:
            conn.close()
            return jsonify({"error": "Paper not found"}), 404

        # 获取论文段落
        cursor.execute("SELECT * FROM paragraphs WHERE paper_id = ? ORDER BY para_id", (paper_id,))
        paragraphs = [dict(row) for row in cursor.fetchall()]

        conn.close()

        return jsonify({
            "paper_id": paper["paper_id"],
            "title": paper["title"],
            "paragraphs": paragraphs
        })
    except Exception as e:
        return jsonify({"error": f"Get fulltext failed: {str(e)}"}), 500
