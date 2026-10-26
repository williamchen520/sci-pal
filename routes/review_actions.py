"""Review action routes: outline / saved outlines / assign / generate.

Moved out of ``api_server.py``; every dependency (task manager, LLM, generator,
store, retriever, db path) is injected so the blueprint stays testable.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Callable

from flask import Blueprint, jsonify, request


def build_review_actions_blueprint(
    *,
    get_task_manager: Callable[[], Any],
    get_llm_client: Callable[[], Any],
    get_review_generator: Callable[[], Any],
    get_review_store: Callable[[], Any],
    get_outline_store: Callable[[], Any],
    get_retriever: Callable[[], Any],
    db_path: Path,
    log: Any,
) -> Blueprint:
    bp = Blueprint("review_actions", __name__)
    _lock = threading.Lock()

    @bp.route("/api/review/outline", methods=["GET", "POST"])
    def generate_outline():
        """
        V26.3: 异步生成段落级大纲（支持取消）

        参数:
          topic: 综述主题（必填）
          max_papers: 最多检索的论文数，默认 20
          review_type: 综述模板类型（narrative/comparative/systematic），默认 narrative

        返回:
          - task_id: 任务ID（前端用这个ID查询任务状态）
        """
        # 支持 JSON body 和 query/form 参数
        json_body = request.get_json(silent=True) or {}
        def get_param(name, default=None):
            if name in json_body:
                return json_body[name]
            return request.values.get(name, default)

        topic = str(get_param("topic", "")).strip()
        if not topic:
            return jsonify({"error": "topic is required"}), 400

        max_papers = int(get_param("max_papers", 20))
        review_type = str(get_param("review_type", "narrative")).strip() or "narrative"
        language = str(get_param("language", "en")).strip().lower() or "en"
        valid_review_types = {"narrative", "comparative", "systematic"}
        if review_type.lower() not in valid_review_types:
            review_type = "narrative"

        # V26.3: 创建任务
        task_id = get_task_manager().create_task("generate_outline")

        # V26.3: 在后台线程里运行生成大纲的任务
        def run_task():
            try:
                llm = get_llm_client()
                if not llm.is_available():
                    get_task_manager().fail_task(task_id, "LLM not available")
                    return

                generator = get_review_generator()
                result = generator.generate_outline(
                    topic=topic,
                    max_papers=max_papers,
                    review_type=review_type,
                    language=language,
                    task_id=task_id,  # V26.3: 传入 task_id，让生成函数可以检查是否被取消
                )
                get_task_manager().complete_task(task_id, result)
            except Exception as e:
                # V26.3: 如果是用户主动取消，不要显示错误信息
                if "Task cancelled by user" in str(e):
                    print(f"[INFO] Task cancelled by user")
                    # V26.4: 立即把任务状态改成 cancelled，这样前端就能看到了
                    get_task_manager().cancel_task(task_id)
                else:
                    print(f"[ERROR] Outline generation failed: {e}")
                    import traceback
                    traceback.print_exc()
                    get_task_manager().fail_task(task_id, str(e))

        # 启动后台线程
        thread = threading.Thread(target=run_task, daemon=True)
        thread.start()

        # V26.3: 立即返回 task_id
        return jsonify({"task_id": task_id})


    # ── V26.1: 自动发配论文到章节 ──

    @bp.route("/api/review/assign_papers", methods=["POST"])
    def assign_papers_to_outline_route():
        """V26.1: 自动计算每篇论文与各章节的相似度，把论文发配到相关章节。

        Body:
          outline: 大纲 JSON {"sections": [...]}（必填）
          papers: 论文列表 [{"paper_id": ..., "title": ..., ...}]（必填）
          evidence_cards: 证据卡片列表（可选）

        Returns:
          更新后的大纲（每章节包含 assigned_paper_ids）
        """
        data = request.get_json(silent=True) or {}
        outline = data.get("outline")
        papers = data.get("papers")
        evidence_cards = data.get("evidence_cards", [])

        if not outline or not outline.get("sections"):
            return jsonify({"error": "outline is required"}), 400
        if not papers:
            return jsonify({"error": "papers is required"}), 400

        try:
            from services.review.review_generator import assign_papers_to_outline
            updated_outline = assign_papers_to_outline(outline, papers, evidence_cards)
            return jsonify({"outline": updated_outline})
        except Exception as e:
            print(f"[ERROR] Assign papers failed: {e}")
            import traceback
            traceback.print_exc()
            return jsonify({"error": f"Assign papers failed: {str(e)}"}), 500


    # ── V31.75: 按大纲搜索并分配论文 ──

    @bp.route("/api/review/search_and_assign", methods=["POST"])
    def search_and_assign_route():
        """V31.75: 按大纲内容搜索论文，然后自动分配给对应的章节和段落。

        Body:
          outline: 大纲 JSON {"sections": [...]}（必填）
          topic: 综述主题（必填）
          max_papers: 最大论文数（可选，默认 100）

        Returns:
          outline: 更新后的大纲（每章节包含 assigned_paper_ids）
          papers: 搜索到的论文列表
        """
        data = request.get_json(silent=True) or {}
        outline = data.get("outline")
        topic = data.get("topic", "")
        max_papers = int(data.get("max_papers", 100))

        if not outline or not outline.get("sections"):
            return jsonify({"error": "outline is required"}), 400
        if not topic:
            return jsonify({"error": "topic is required"}), 400

        try:
            from services.review.review_generator import search_and_assign_papers
            retriever = get_retriever()
            updated_outline, papers = search_and_assign_papers(
                outline=outline,
                topic=topic,
                max_papers=max_papers,
                retriever=retriever,
            )
            return jsonify({"outline": updated_outline, "papers": papers})
        except Exception as e:
            print(f"[ERROR] Search and assign failed: {e}")
            import traceback
            traceback.print_exc()
            return jsonify({"error": f"Search and assign failed: {str(e)}"}), 500


    # ── V25.9: 大纲保存/加载路由 ──

    @bp.route("/api/review/outline/saved", methods=["GET"])
    def list_saved_outlines():
        """V25.9: 列出所有已保存的大纲（按更新时间倒序）。"""
        try:
            store = get_outline_store()
            outlines = store.list()
            return jsonify({"count": len(outlines), "outlines": outlines})
        except Exception as e:
            return jsonify({"error": f"Failed to list outlines: {str(e)}"}), 500


    @bp.route("/api/review/outline/saved/<name>", methods=["GET"])
    def load_saved_outline(name):
        """V25.9: 加载指定名称的已保存大纲。"""
        try:
            store = get_outline_store()
            record = store.load(name)
            if record is None:
                return jsonify({"error": f"Outline '{name}' not found"}), 404
            return jsonify(record)
        except Exception as e:
            return jsonify({"error": f"Failed to load outline: {str(e)}"}), 500


    @bp.route("/api/review/outline/save", methods=["POST"])
    def save_outline():
        """
        V25.9: 保存大纲（JSON body）。

        Body:
          name: 大纲名称（必填）
          topic: 综述主题
          review_type: 综述模板类型
          outline: 段落级大纲 JSON {"sections": [...]}（必填）
          paper_count: 涉及的论文数（可选）
        """
        data = request.get_json(silent=True) or {}
        name = str(data.get("name", "")).strip()
        if not name:
            return jsonify({"error": "name is required"}), 400

        outline_data = data.get("outline")
        if not isinstance(outline_data, dict) or "sections" not in outline_data:
            return jsonify({"error": "outline must be a JSON object with 'sections' field"}), 400

        topic = str(data.get("topic", "")).strip()
        review_type = str(data.get("review_type", "narrative")).strip() or "narrative"
        paper_count = int(data.get("paper_count", 0))

        try:
            store = get_outline_store()
            record = store.save(name=name, topic=topic, outline_data=outline_data,
                                review_type=review_type, paper_count=paper_count)
            return jsonify({"status": "saved", "name": record["name"], "updated_at": record["updated_at"]})
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        except Exception as e:
            return jsonify({"error": f"Failed to save outline: {str(e)}"}), 500


    @bp.route("/api/review/outline/saved/<name>", methods=["DELETE"])
    def delete_saved_outline(name):
        """V25.9: 删除指定名称的已保存大纲。"""
        try:
            store = get_outline_store()
            deleted = store.delete(name)
            if not deleted:
                return jsonify({"error": f"Outline '{name}' not found"}), 404
            return jsonify({"status": "deleted", "name": name})
        except Exception as e:
            return jsonify({"error": f"Failed to delete outline: {str(e)}"}), 500


    @bp.route("/api/review/generate", methods=["GET", "POST"])
    def generate_review():
        """
        生成综述初稿（V25.0）。

        完整流水线：检索 → 证据抽取 → 大纲生成 → 撰写 → 引用校验 → Markdown 输出。
        核心铁律：每句话必须绑定证据卡片，无证据的句子被校验系统剔除。

        参数:
          topic: 综述主题（必填）
          max_papers: 最多检索的论文数，默认 20
          use_llm_verify: 是否启用 LLM 深度校验，默认 false（确定性校验更快）
          citation_style: 参考文献格式（apa / nature / vancouver），默认 apa
          review_type: 综述模板类型（V25.7）：narrative（叙事型，默认）/ comparative（实验对比型）/ systematic（系统综述型）

        前置条件: Ollama 服务运行，且已拉取模型（默认 qwen2.5:14b）。
        可用环境变量 SCIPAL_LLM_MODEL 覆盖模型名。
        """
        # V25.8: 支持 JSON body 传参（用于 custom_outline 等复杂参数）
        json_body = request.get_json(silent=True) or {}

        # 参数获取优先级：JSON body > query/form
        def get_param(name, default=None):
            if name in json_body:
                return json_body[name]
            return request.values.get(name, default)

        topic = str(get_param("topic", "")).strip()
        if not topic:
            return jsonify({"error": "topic is required"}), 400

        max_papers = int(get_param("max_papers", 20))
        use_llm_verify = str(get_param("use_llm_verify", "false")).lower() in ("true", "1", "yes")
        citation_style = str(get_param("citation_style", "apa")).strip() or "apa"
        # V25.7: 综述模板类型
        review_type = str(get_param("review_type", "narrative")).strip() or "narrative"
        # V25.9: 综述生成语言，默认英文（en），可选中文（zh）
        language = str(get_param("language", "en")).strip().lower() or "en"
        # 校验 review_type 合法性
        valid_review_types = {"narrative", "comparative", "systematic", "story", "experiment", "experimental", "compare", "meta", "meta-analysis"}
        if review_type.lower() not in valid_review_types:
            review_type = "narrative"
        # V25.8: 用户自定义段落级大纲（从 JSON body 读取）
        custom_outline = json_body.get("custom_outline") if isinstance(json_body, dict) else None
        if custom_outline is not None and not isinstance(custom_outline, dict):
            return jsonify({"error": "custom_outline must be a JSON object"}), 400

        try:
            llm = get_llm_client()
            if not llm.is_available():
                if llm.provider == "openai":
                    return jsonify({
                        "error": "Cloud API not available",
                        "hint": "Set API key: export SCIPAL_LLM_API_KEY=sk-你的key",
                        "configured_model": llm.model,
                    }), 503
                else:
                    return jsonify({
                        "error": "Ollama service not available",
                        "hint": "Start Ollama and pull the model: ollama serve && ollama pull qwen2.5:14b",
                        "configured_model": llm.model,
                    }), 503

            # V33.17 C-2: 共享单例 + threaded=True → 必须串行，否则 use_llm_verification
            # 与 _last_draft/_last_evidence_cards 会被并发任务互相覆盖。
            with _lock:
                generator = get_review_generator()
                generator.use_llm_verification = use_llm_verify

                output = generator.generate(
                    topic=topic,
                    max_papers=max_papers,
                    citation_style=citation_style,
                    review_type=review_type,
                    custom_outline=custom_outline,
                    language=language,
                )

                # V25.6: 暂存综述结果（含 sentences 和 evidence_cards，用于前端点击溯源）
                review_id = None
                try:
                    store = get_review_store()
                    review_id = store.store(
                        review_output=output,
                        draft=generator._last_draft,
                        evidence_cards=generator._last_evidence_cards,
                    )
                except Exception as store_err:
                    # 暂存失败不影响综述返回
                    print(f"[WARN] Review store failed: {store_err}")

            return jsonify({
                "topic": output.topic,
                "markdown": output.markdown,
                "references": output.references,
                "stats": output.stats,
                "warnings": output.warnings,
                "relations": output.relations,
                "conflicts": output.conflicts,
                "review_id": review_id,  # V25.6: 用于前端预览页点击溯源
            })
        except Exception as e:
            return jsonify({"error": f"Review generation failed: {str(e)}"}), 500


    @bp.route("/api/review/generate_async", methods=["POST"])
    def generate_review_async():
        """V33.17 C-2: 异步生成综述初稿（立即返回 task_id）。

        参数与同步版 `/api/review/generate` **完全一致**：
          topic(必填) / max_papers=20 / use_llm_verify=false / citation_style="apa" /
          review_type="narrative" / language="en" / custom_outline(JSON object, 可选)

        返回：{"task_id": "..."}（立即，不等结果）

        轮询：GET /api/review/task/<task_id>（status=running/completed/failed/cancelled）
        取消：POST /api/review/cancel/<task_id>

        ⚠️ 取消语义（如实说明）：
          只在**阶段之间**生效 —— 检索前 / 证据抽取前 / 大纲前 / 撰写前 / 校验前，共 5 个点。
          各阶段内部是原子的：**正在撰写正文时不可中断**，取消要等这一段 LLM 撰写跑完，
          才会在「校验前」被观察到。所以取消粒度是「阶段级」，不是「句子级」。

        并发隔离：每个任务 new 一个私有 ReviewGenerator（注入的 llm_client / retriever
          仍是全局单例，模型不重复加载），因此两个任务的 use_llm_verification 不会串台。
        """
        json_body = request.get_json(silent=True) or {}

        def get_param(name, default=None):
            if name in json_body:
                return json_body[name]
            return request.values.get(name, default)

        topic = str(get_param("topic", "")).strip()
        if not topic:
            return jsonify({"error": "topic is required"}), 400

        max_papers = int(get_param("max_papers", 20))
        use_llm_verify = str(get_param("use_llm_verify", "false")).lower() in ("true", "1", "yes")
        citation_style = str(get_param("citation_style", "apa")).strip() or "apa"
        review_type = str(get_param("review_type", "narrative")).strip() or "narrative"
        language = str(get_param("language", "en")).strip().lower() or "en"
        valid_review_types = {
            "narrative", "comparative", "systematic",
            "story", "experiment", "experimental", "compare", "meta", "meta-analysis",
        }
        if review_type.lower() not in valid_review_types:
            review_type = "narrative"
        custom_outline = json_body.get("custom_outline") if isinstance(json_body, dict) else None
        if custom_outline is not None and not isinstance(custom_outline, dict):
            return jsonify({"error": "custom_outline must be a JSON object"}), 400

        task_id = get_task_manager().create_task("generate_review")

        def run_task():
            try:
                llm = get_llm_client()
                if not llm.is_available():
                    get_task_manager().fail_task(task_id, "LLM not available")
                    return

                # V33.17 C-2: **每个任务 new 私有实例**，绝不复用 get_review_generator() 单例 —— 
                # 单例的 use_llm_verification 与 _last_draft/_last_evidence_cards 会被并发任务覆盖。
                # 注入的 llm_client / retriever 本身是全局单例，模型不会重复加载。
                from services.review.review_generator import ReviewGenerator

                generator = ReviewGenerator(
                    llm_client=get_llm_client(),
                    retriever=get_retriever(),
                    use_llm_verification=use_llm_verify,
                    db_path=str(db_path),
                )

                output = generator.generate(
                    topic=topic,
                    max_papers=max_papers,
                    citation_style=citation_style,
                    review_type=review_type,
                    custom_outline=custom_outline,
                    language=language,
                    task_id=task_id,  # C-2: 阶段间取消检查 + 进度上报
                )

                review_id = None
                try:
                    store = get_review_store()
                    review_id = store.store(
                        review_output=output,
                        draft=generator._last_draft,
                        evidence_cards=generator._last_evidence_cards,
                    )
                except Exception as store_err:
                    print(f"[WARN] Review store failed: {store_err}")

                get_task_manager().complete_task(task_id, {
                    "topic": output.topic,
                    "markdown": output.markdown,
                    "references": output.references,
                    "stats": output.stats,
                    "warnings": output.warnings,
                    "relations": output.relations,
                    "conflicts": output.conflicts,
                    "review_id": review_id,
                    # C-2: 回显本次任务实际使用的参数，便于验证并发任务没有串台
                    "use_llm_verify": use_llm_verify,
                    "max_papers": max_papers,
                    "review_type": review_type,
                    "language": language,
                })
            except Exception as e:
                if "Task cancelled by user" in str(e):
                    print("[INFO] Async review generation cancelled by user")
                    get_task_manager().cancel_task(task_id)
                else:
                    print(f"[ERROR] Async review generation failed: {e}")
                    import traceback
                    traceback.print_exc()
                    get_task_manager().fail_task(task_id, str(e))

        thread = threading.Thread(target=run_task, daemon=True)
        thread.start()

        return jsonify({"task_id": task_id})


    # ---------------------------------------------------------------------------
    # V33.17-6B补丁: 「哪条记录才算数」的唯一口径
    #
    # papers.filename **没有**唯一约束（索引只有 idx_papers_doi / idx_papers_title），
    # 同一份 PDF 可能同时存在 `paper_X_<hash>`（正常，如 224 段）与
    # `paper_X_<hash>_mineru`（空壳，0 段）两行。裸 `fetchone()` 取到哪条取决于物理
    # 行序 → 同步路由 / 异步快路径 / `/api/papers/local` 会给出互相矛盾的答案
    # （实测同一文件：快路径 224、papers/local 0）。
    #
    # 口径：**段落数多者优先；并列时取创建更早的**（原始入库那条）。
    # ⚠️ 只统一「读取口径」，**不删** `_mineru` 空壳行 —— 那是数据清理，另议。
    # ---------------------------------------------------------------------------
    _PARSED_PAPER_ORDER = "ORDER BY total_paragraphs DESC, created_at ASC LIMIT 1"


    def _find_parsed_paper(filename: str, conn=None):
        """按 filename 取「最有效」的一条已解析记录（`sqlite3.Row`）；没有返回 None。

        这是**唯一口径**，三处调用点都走它：
          · 同步 `POST /api/papers/parse`
          · 异步 `POST /api/papers/parse_async` 的快路径
          · `GET /api/papers/local` 的 parsed_map

        Args:
            filename: `papers.filename`（磁盘上的 PDF 文件名）
            conn: 可选，复用调用方已打开的连接（`/api/papers/local` 要扫 77 个文件，
                  避免 77 次开关连接）。为 None 时自己开关。
        """
        import sqlite3

        own_conn = conn is None
        if own_conn:
            conn = sqlite3.connect(str(db_path), timeout=5)
            conn.row_factory = sqlite3.Row
        try:
            return conn.execute(
                "SELECT paper_id, filename, title, authors, year, total_paragraphs "
                f"FROM papers WHERE filename = ? {_PARSED_PAPER_ORDER}",
                (filename,),
            ).fetchone()
        finally:
            if own_conn:
                conn.close()

    return bp
