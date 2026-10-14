"""
AI Q&A Routes
"""
from flask import Blueprint, jsonify, request
from services.ai.ai_service import AIService

ai_bp = Blueprint("ai", __name__)
ai_service = AIService()

@ai_bp.route("/ask", methods=["POST"])
def ask_question():
    """Ask a question to the research assistant"""
    data = request.get_json()
    
    if not data or "question" not in data:
        return jsonify({"error": "Question is required"}), 400
    
    question = data["question"]
    paper_id = data.get("paper_id", None)
    
    if not question.strip():
        return jsonify({"error": "Question cannot be empty"}), 400
    
    try:
        result = ai_service.ask(question, paper_id=paper_id)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": f"AI service error: {str(e)}"}), 500

@ai_bp.route("/status", methods=["GET"])
def ai_status():
    """Get AI service status"""
    return jsonify({
        "status": "ready",
        "model": ai_service.model,
        "max_retries": ai_service.max_retries,
        "coverage_threshold": ai_service.validator.coverage_threshold
    })
