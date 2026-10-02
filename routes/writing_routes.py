"""
Writing Routes
==============
学术写作服务路由
"""
from flask import Blueprint, jsonify, request
from services.writing.writing_service import WritingService

writing_bp = Blueprint("writing", __name__)
writing_service = WritingService()


@writing_bp.route("/write_paper", methods=["POST"])
def write_paper():
    """写论文"""
    data = request.get_json()

    if not data or "topic" not in data:
        return jsonify({"error": "Topic is required"}), 400

    topic = data["topic"]
    evidence = data.get("evidence", "")
    paper_type = data.get("paper_type", "journal")

    if not topic.strip():
        return jsonify({"error": "Topic cannot be empty"}), 400

    try:
        result = writing_service.write_paper(topic, evidence=evidence, paper_type=paper_type)
        return jsonify({"result": result})
    except Exception as e:
        return jsonify({"error": f"Writing service error: {str(e)}"}), 500


@writing_bp.route("/write_abstract", methods=["POST"])
def write_abstract():
    """写摘要"""
    data = request.get_json()

    if not data or "title" not in data or "content" not in data:
        return jsonify({"error": "Title and content are required"}), 400

    title = data["title"]
    content = data["content"]
    language = data.get("language", "english")

    if not title.strip() or not content.strip():
        return jsonify({"error": "Title and content cannot be empty"}), 400

    try:
        result = writing_service.write_abstract(title, content, language=language)
        return jsonify({"result": result})
    except Exception as e:
        return jsonify({"error": f"Writing service error: {str(e)}"}), 500


@writing_bp.route("/write_literature_review", methods=["POST"])
def write_literature_review():
    """写文献综述"""
    data = request.get_json()

    if not data or "topic" not in data:
        return jsonify({"error": "Topic is required"}), 400

    topic = data["topic"]
    papers = data.get("papers", [])

    if not topic.strip():
        return jsonify({"error": "Topic cannot be empty"}), 400

    try:
        result = writing_service.write_literature_review(topic, papers)
        return jsonify({"result": result})
    except Exception as e:
        return jsonify({"error": f"Writing service error: {str(e)}"}), 500


@writing_bp.route("/polish_text", methods=["POST"])
def polish_text():
    """润色文本"""
    data = request.get_json()

    if not data or "text" not in data:
        return jsonify({"error": "Text is required"}), 400

    text = data["text"]

    if not text.strip():
        return jsonify({"error": "Text cannot be empty"}), 400

    try:
        result = writing_service.polish_text(text)
        return jsonify({"result": result})
    except Exception as e:
        return jsonify({"error": f"Writing service error: {str(e)}"}), 500


@writing_bp.route("/status", methods=["GET"])
def writing_status():
    """获取写作服务状态"""
    return jsonify({
        "status": "ready",
        "model": writing_service.model,
        "prompts_loaded": [
            "academic_writing_style.md",
            "imrad_paper_structure.md",
            "abstract_writing_template.md",
            "literature_review_template.md"
        ]
    })
