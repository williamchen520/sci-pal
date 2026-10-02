"""
Search Routes
"""
from flask import Blueprint, jsonify, request
from services.query.search_service import SearchService

search_bp = Blueprint("search", __name__)
search_service = SearchService()

@search_bp.route("/text", methods=["GET"])
def text_search():
    """Text search across paragraphs"""
    query = request.args.get("q", "")
    top_k = int(request.args.get("top_k", 10))
    paper_id = request.args.get("paper_id", None)
    
    if not query:
        return jsonify({"error": "Query parameter 'q' is required"}), 400
    
    results = search_service.text_search(query, top_k=top_k, paper_id=paper_id)
    
    return jsonify({
        "query": query,
        "results": results,
        "total": len(results)
    })

@search_bp.route("/figure", methods=["GET"])
def figure_search():
    """Figure/caption search"""
    query = request.args.get("q", "")
    top_k = int(request.args.get("top_k", 10))
    paper_id = request.args.get("paper_id", None)
    
    if not query:
        return jsonify({"error": "Query parameter 'q' is required"}), 400
    
    results = search_service.figure_search(query, top_k=top_k, paper_id=paper_id)
    
    return jsonify({
        "query": query,
        "results": results,
        "total": len(results)
    })

@search_bp.route("/citation", methods=["GET"])
def citation_search():
    """Citation search"""
    query = request.args.get("q", "")
    top_k = int(request.args.get("top_k", 10))
    paper_id = request.args.get("paper_id", None)
    
    if not query:
        return jsonify({"error": "Query parameter 'q' is required"}), 400
    
    results = search_service.citation_search(query, top_k=top_k, paper_id=paper_id)
    
    return jsonify({
        "query": query,
        "results": results,
        "total": len(results)
    })

@search_bp.route("/paper", methods=["GET"])
def paper_search():
    """Paper metadata search"""
    query = request.args.get("q", "")
    top_k = int(request.args.get("top_k", 20))
    
    if not query:
        return jsonify({"error": "Query parameter 'q' is required"}), 400
    
    results = search_service.paper_search(query, top_k=top_k)
    
    return jsonify({
        "query": query,
        "results": results,
        "total": len(results)
    })

@search_bp.route("/unified", methods=["GET"])
def unified_search():
    """
    Unified search across all types
    This is what the AI RAG will use
    """
    query = request.args.get("q", "")
    top_k = int(request.args.get("top_k", 10))
    
    if not query:
        return jsonify({"error": "Query parameter 'q' is required"}), 400
    
    results = search_service.unified_search(query, top_k=top_k)
    
    return jsonify({
        "query": query,
        "results": results,
        "counts": {
            "papers": len(results["papers"]),
            "text": len(results["text"]),
            "figures": len(results["figures"]),
            "citations": len(results["citations"]),
        }
    })
