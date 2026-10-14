/* V25.6 - Sci-Pal 综述预览页交互逻辑（独立模块）
 *
 * 功能：
 * 1. 综述 Markdown 渲染（句子级可点击）
 * 2. 点击句子溯源到原文证据
 * 3. PDF.js 联动定位到证据所在页码
 * 4. 证据卡片详情展示（原文引用 + 实验条件）
 */

(function() {
  'use strict';

  // ── 全局状态 ──
  let reviewData = null;       // 综述完整数据
  let currentSentenceId = null; // 当前选中的句子 ID

  // ── DOM 元素 ──
  const els = {};

  // ── 初始化 ──
  document.addEventListener('DOMContentLoaded', init);

  function init() {
    // 缓存 DOM 元素
    els.reviewPanel = document.getElementById('reviewPanel');
    els.pdfContainer = document.getElementById('pdfContainer');
    els.evidencePanel = document.getElementById('evidencePanel');
    els.topicDisplay = document.getElementById('topicDisplay');
    els.statsDisplay = document.getElementById('statsDisplay');
    els.pdfTitle = document.getElementById('pdfTitle');

    // 解析 URL 参数
    const params = new URLSearchParams(window.location.search);
    const reviewId = params.get('review_id');
    const topic = params.get('topic');
    const maxPapers = params.get('max_papers') || 10;

    // V25.9: 如果有 review_id，显示综述预览，隐藏大纲编辑器
    const outlineEditor = document.getElementById('outlineEditor');
    const reviewContainer = document.getElementById('reviewContainer');

    if (reviewId) {
      // 直接加载已有综述
      if (outlineEditor) outlineEditor.style.display = 'none';
      if (reviewContainer) reviewContainer.style.display = 'flex';
      loadReview(reviewId);
    } else if (topic) {
      // V25.9: 有 topic 但无 review_id，预填到大纲编辑器
      if (outlineEditor) {
        const topicInput = document.getElementById('editorTopicInput');
        if (topicInput) topicInput.value = topic;
      }
      // 显示大纲编辑器（默认已显示）
    } else {
      // 显示大纲编辑器（默认）
    }
  }

  // ── 加载已有综述 ──
  async function loadReview(reviewId) {
    showLoading(els.reviewPanel, '加载综述中...');
    try {
      const resp = await fetch(`/api/review/${reviewId}`);
      if (!resp.ok) {
        const err = await resp.json();
        throw new Error(err.error || '加载失败');
      }
      reviewData = await resp.json();
      renderReview();
    } catch (e) {
      showError(els.reviewPanel, `加载综述失败：${e.message}`);
    }
  }

  // ── 生成新综述 ──
  async function generateReview(topic, maxPapers) {
    showLoading(els.reviewPanel, `正在生成综述「${topic}」...\n（约需 1-3 分钟，请耐心等待）`);
    try {
      const resp = await fetch(`/api/review/generate?topic=${encodeURIComponent(topic)}&max_papers=${maxPapers}`, {
        method: 'POST'
      });
      if (!resp.ok) {
        const err = await resp.json();
        throw new Error(err.error || '生成失败');
      }
      const data = await resp.json();
      if (data.review_id) {
        // 生成成功，加载完整数据（含 sentences 和 evidence_cards）
        loadReview(data.review_id);
      } else {
        // 旧版 API 没有 review_id，直接用返回数据渲染（但没有溯源功能）
        reviewData = data;
        reviewData.sentences = [];
        reviewData.evidence_cards = {};
        renderReview();
      }
    } catch (e) {
      showError(els.reviewPanel, `生成综述失败：${e.message}`);
    }
  }

  // ── 渲染综述 ──
  function renderReview() {
    if (!reviewData) return;

    // 更新顶部信息
    els.topicDisplay.textContent = reviewData.topic || '综述';
    if (reviewData.stats) {
      const s = reviewData.stats;
      els.statsDisplay.innerHTML = `
        <span>句子 ${s.total_sentences || 0}</span>
        <span>证据 ${s.total_evidence || 0}</span>
        <span>通过率 ${((s.pass_rate || 0) * 100).toFixed(0)}%</span>
      `;
    }

    // 渲染警告
    let html = '';
    if (reviewData.warnings && reviewData.warnings.length > 0) {
      html += '<div class="warnings"><h4>📋 生成日志</h4><ul>';
      reviewData.warnings.forEach(w => {
        html += `<li>${escapeHtml(w)}</li>`;
      });
      html += '</ul></div>';
    }

    // 渲染 Markdown（句子级拆分）
    html += renderMarkdownWithSentences(reviewData.markdown);

    // 渲染参考文献
    if (reviewData.references && reviewData.references.length > 0) {
      html += '<div class="references"><h2>参考文献</h2><ol>';
      reviewData.references.forEach(ref => {
        const title = ref.title || ref.paper_id || '未知文献';
        html += `<li>${escapeHtml(title)}</li>`;
      });
      html += '</ol></div>';
    }

    els.reviewPanel.innerHTML = html;

    // 绑定句子点击事件
    bindSentenceClicks();

    // 初始化 PDF 面板空状态
    if (!currentSentenceId) {
      showEmptyPdf();
    }
  }

  // ── Markdown 渲染（句子级拆分）──
  function renderMarkdownWithSentences(markdown) {
    if (!markdown) return '';

    const lines = markdown.split('\n');
    let html = '';
    let inList = false;

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];

      // 标题
      if (line.startsWith('# ')) {
        if (inList) { html += '</ol>'; inList = false; }
        html += `<h1>${escapeHtml(line.substring(2))}</h1>`;
        continue;
      }
      if (line.startsWith('## ')) {
        if (inList) { html += '</ol>'; inList = false; }
        html += `<h2>${escapeHtml(line.substring(3))}</h2>`;
        continue;
      }
      if (line.startsWith('### ')) {
        if (inList) { html += '</ol>'; inList = false; }
        html += `<h3>${escapeHtml(line.substring(4))}</h3>`;
        continue;
      }

      // 有序列表
      if (/^\d+\.\s/.test(line)) {
        if (!inList) { html += '<ol>'; inList = true; }
        const content = line.replace(/^\d+\.\s/, '');
        html += `<li>${renderSentences(content)}</li>`;
        continue;
      } else if (inList && line.trim() === '') {
        html += '</ol>';
        inList = false;
        continue;
      }

      // 空行
      if (line.trim() === '') {
        continue;
      }

      // 普通段落
      html += `<p>${renderSentences(line)}</p>`;
    }

    if (inList) html += '</ol>';
    return html;
  }

  // ── 渲染句子（拆分引用标记，绑定 sentence_id）──
  function renderSentences(text) {
    if (!text) return '';

    // 如果有 sentences 数据，尝试匹配 sentence_id
    // 简化处理：把整段文本作为一个可点击区域，data-sentence-index 记录位置
    // 更精确的做法是按句号拆分，但中文句号和英文句号混合，容易出错
    // 这里采用：每个 [ev_xxx] 引用标记可点击，点击时显示该证据的详情
    // 同时整段也可点击，显示该段所有关联证据

    // V25.15: 引用编号优化 — 显示 [1] 而非 [ev_001]，但 data-evidence-id 保持 ev_001 不变（点击溯源依赖）
    // 先处理引用标记 [ev_001] -> <span class="citation" data-evidence-id="ev_001">[1]</span>
    let html = text.replace(/\[ev_(\d+)\]/g, (match, id) => {
      return `<span class="citation" data-evidence-id="ev_${id}" title="点击查看证据详情">[${parseInt(id)}]</span>`;
    });

    // 整段作为可点击句子（如果有 sentences 数据，匹配文本内容）
    if (reviewData && reviewData.sentences && reviewData.sentences.length > 0) {
      // 尝试找到匹配的 sentence
      const plainText = text.replace(/\[ev_\d+\]/g, '').trim();
      const matched = reviewData.sentences.find(s =>
        s.text && plainText.includes(s.text.substring(0, Math.min(20, s.text.length)))
      );
      if (matched) {
        html = `<span class="sentence" data-sentence-id="${matched.sentence_id}">${html}</span>`;
      }
    }

    return html;
  }

  // ── 绑定句子点击事件 ──
  function bindSentenceClicks() {
    // 句子点击
    els.reviewPanel.querySelectorAll('.sentence').forEach(el => {
      el.addEventListener('click', function(e) {
        e.stopPropagation();
        const sentenceId = this.dataset.sentenceId;
        if (sentenceId) {
          selectSentence(sentenceId, this);
        }
      });
    });

    // 引用标记点击
    els.reviewPanel.querySelectorAll('.citation').forEach(el => {
      el.addEventListener('click', function(e) {
        e.stopPropagation();
        const evidenceId = this.dataset.evidenceId;
        if (evidenceId) {
          showEvidenceById(evidenceId);
        }
      });
    });
  }

  // ── 选中句子 ──
  async function selectSentence(sentenceId, element) {
    // 移除之前的高亮
    els.reviewPanel.querySelectorAll('.sentence.active').forEach(el => {
      el.classList.remove('active');
    });
    // 添加新高亮
    if (element) element.classList.add('active');
    currentSentenceId = sentenceId;

    // 获取句子溯源信息
    if (!reviewData || !reviewData.review_id) return;

    try {
      const resp = await fetch(`/api/review/${reviewData.review_id}/sentence/${sentenceId}`);
      if (!resp.ok) return;
      const data = await resp.json();

      // 显示证据详情
      renderEvidencePanel(data.evidences || []);

      // 如果有证据，加载第一个证据对应的 PDF
      if (data.evidences && data.evidences.length > 0) {
        loadEvidencePdf(data.evidences[0]);
      }
    } catch (e) {
      console.error('获取句子溯源失败:', e);
    }
  }

  // ── 按 evidence_id 显示证据 ──
  function showEvidenceById(evidenceId) {
    if (!reviewData || !reviewData.evidence_cards) return;
    const ev = reviewData.evidence_cards[evidenceId];
    if (ev) {
      renderEvidencePanel([ev]);
      loadEvidencePdf(ev);
    }
  }

  // ── 渲染证据详情面板 ──
  function renderEvidencePanel(evidences) {
    if (!evidences || evidences.length === 0) {
      els.evidencePanel.innerHTML = '<div class="empty-state"><div class="icon">📄</div><div>点击综述中的句子或引用标记查看证据</div></div>';
      return;
    }

    let html = `<h4>证据详情 <span class="badge">${evidences.length} 条</span></h4>`;
    evidences.forEach(ev => {
      html += '<div class="evidence-card">';
      html += '<div class="ev-header">';
      html += `<span class="ev-id">${escapeHtml(ev.evidence_id || '')}</span>`;
      // V33.17: 摘要证据标记（该论文无全文，摘要当证据）
      const isAbstractEv = ev.source_type === 'abstract' || ev.source === 'abstract';
      if (isAbstractEv) {
        html += `<span class="ev-type" title="来自摘要库（该论文无全文）" style="background:#fef3c7;color:#92400e;">📄 摘要</span>`;
      }
      html += `<span class="ev-type">${escapeHtml(ev.evidence_type || 'fact')}</span>`;
      html += '</div>';

      if (ev.original_quote) {
        html += `<div class="ev-quote">${escapeHtml(ev.original_quote)}</div>`;
      } else if (ev.content) {
        html += `<div class="ev-quote">${escapeHtml(ev.content)}</div>`;
      }

      // 实验条件标签
      const conditions = [];
      if (ev.mutation_type && ev.mutation_type !== '未知') conditions.push(`突变: ${ev.mutation_type}`);
      if (ev.cell_type && ev.cell_type !== '未知') conditions.push(`细胞: ${ev.cell_type}`);
      if (ev.measurement && ev.measurement !== '未知') conditions.push(`测量: ${ev.measurement}`);
      if (ev.stimulus && ev.stimulus !== '未知') conditions.push(`刺激: ${ev.stimulus}`);
      if (conditions.length > 0) {
        html += '<div class="ev-meta">';
        conditions.forEach(c => { html += `<span>${escapeHtml(c)}</span>`; });
        html += '</div>';
      }

      // 论文信息
      if (ev.paper_title || ev.paper_id) {
        html += `<div class="ev-paper">📄 ${escapeHtml(ev.paper_title || ev.paper_id || '')}`;
        if (ev.section_l1) html += ` · ${escapeHtml(ev.section_l1)}`;
        if (ev.page) html += ` · 第 ${ev.page} 页`;
        html += '</div>';
      }

      html += '</div>';
    });

    els.evidencePanel.innerHTML = html;
  }

  // ── 加载证据对应的 PDF（V25.14: iframe 浏览器原生渲染）──
  function loadEvidencePdf(evidence) {
    if (!evidence || !evidence.paper_id) return;

    const pdfUrl = `/api/papers/${encodeURIComponent(evidence.paper_id)}/pdf`;
    const page = evidence.page || 1;
    const title = evidence.paper_title || evidence.paper_id || '';

    els.pdfTitle.textContent = title;

    // 用 iframe 加载 PDF，浏览器自带 PDFium 矢量渲染
    els.pdfContainer.innerHTML = '';
    const iframe = document.createElement('iframe');
    iframe.className = 'pdf-iframe';
    iframe.src = pdfUrl + '#page=' + page;
    iframe.style.width = '100%';
    iframe.style.height = '100%';
    iframe.style.border = 'none';
    els.pdfContainer.appendChild(iframe);
  }

  // ── 显示生成表单 ──
  function showGenerateForm() {
    els.reviewPanel.innerHTML = `
      <div class="generate-form">
        <h2>📝 生成学术综述</h2>
        <form id="genForm">
          <label for="topicInput">综述主题</label>
          <input type="text" id="topicInput" placeholder="例如：STAT1 信号通路与免疫疾病" required>
          <div class="form-row">
            <div>
              <label for="maxPapersInput">最大论文数</label>
              <input type="number" id="maxPapersInput" value="10" min="1" max="50">
            </div>
          </div>
          <button type="submit" id="genBtn">生成综述</button>
          <p class="hint">生成约需 1-3 分钟（云端模型）或 10-20 分钟（本地模型）</p>
        </form>
      </div>
    `;
    els.pdfContainer.innerHTML = '<div class="empty-state"><div class="icon">📖</div><div>生成综述后，点击句子可查看原文证据</div></div>';
    els.evidencePanel.innerHTML = '<div class="empty-state"><div class="icon">📄</div><div>证据详情将显示在这里</div></div>';

    document.getElementById('genForm').addEventListener('submit', function(e) {
      e.preventDefault();
      const topic = document.getElementById('topicInput').value.trim();
      const maxPapers = document.getElementById('maxPapersInput').value;
      if (topic) {
        // 更新 URL（不刷新页面）
        const url = new URL(window.location);
        url.searchParams.set('topic', topic);
        url.searchParams.set('max_papers', maxPapers);
        window.history.pushState({}, '', url);
        generateReview(topic, maxPapers);
      }
    });
  }

  // ── 空状态 PDF ──
  function showEmptyPdf() {
    els.pdfContainer.innerHTML = '<div class="empty-state"><div class="icon">📖</div><div>点击综述中的句子或引用标记<br>查看原文 PDF 定位</div></div>';
    els.evidencePanel.innerHTML = '<div class="empty-state"><div class="icon">📄</div><div>证据详情将显示在这里</div></div>';
  }

  // ── 工具函数 ──
  function showLoading(container, text) {
    container.innerHTML = `<div class="loading"><div class="spinner"></div><div>${escapeHtml(text).replace(/\n/g, '<br>')}</div></div>`;
  }

  function showError(container, text) {
    container.innerHTML = `<div class="loading" style="color:#e74c3c;"><div class="icon" style="font-size:48px;">❌</div><div>${escapeHtml(text)}</div></div>`;
  }

  function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

})();
