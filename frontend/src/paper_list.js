/* V25.10 - Sci-Pal 论文列表模块（独立）
 *
 * 职责：
 * 1. 渲染相关论文列表
 * 2. 点击论文：打开 PDF + 若有选中段落则切换分配
 * 3. 显示已分配/当前打开状态
 *
 * 不负责：大纲状态管理、PDF 渲染、标注
 */

(function() {
  'use strict';

  /**
   * 创建论文列表管理器
   * @param {Object} config
   * @param {HTMLElement} config.container - 论文列表容器
   * @param {Function} config.onPaperClick - 论文点击回调 (paperId, paperTitle)
   * @param {Function} config.onLocalPaperClick - 本地文献点击回调 (paperId, paperTitle, filename, parsed)
   * @param {Function} config.escapeHtml - HTML 转义函数
   */
  function createPaperList(config) {

    // ── 渲染论文列表 ──
    function render(papers, outlineData, selectedParagraphId, currentPaperId) {
      if (!papers || papers.length === 0) {
        config.container.innerHTML =
          '<div class="paper-empty">' +
          '<div class="icon">📄</div>' +
          '<div>生成大纲后，相关论文将显示在这里<br>点击论文在右侧打开 PDF</div>' +
          '</div>';
        return;
      }

      // 获取当前选中段落已分配的论文
      let assignedPapers = new Set();
      if (selectedParagraphId && outlineData) {
        for (const sec of outlineData.sections || []) {
          for (const para of sec.paragraphs || []) {
            if (para.paragraph_id === selectedParagraphId) {
              assignedPapers = new Set(para.assigned_paper_ids || []);
            }
          }
        }
      }

      let html = '';
      if (selectedParagraphId) {
        html += '<div class="paper-list-hint">点击论文分配到当前选中段落并打开 PDF，再次点击取消分配</div>';
      } else {
        html += '<div class="paper-list-hint">点击论文在右侧打开 PDF；先选中段落再点击可分配论文</div>';
      }

      papers.forEach(function(paper) {
        const isAssigned = assignedPapers.has(paper.paper_id);
        const isCurrent = paper.paper_id === currentPaperId;
        const source = paper.source || 'full_text';
        const sourceBadge = source === 'abstract'
          ? '<span class="source-badge abstract" title="摘要库">摘要</span>'
          : '<span class="source-badge fulltext" title="全文库">全文</span>';
        // V33.17: 证据数区分全文/摘要
        const fulltextEv = paper.fulltext_evidence_count || 0;
        const abstractEv = paper.abstract_evidence_count || 0;
        let evText = (paper.evidence_count || 0) + ' 条证据';
        if (fulltextEv > 0 && abstractEv > 0) {
          evText += '（全文' + fulltextEv + '+摘要' + abstractEv + '）';
        } else if (abstractEv > 0 && !fulltextEv) {
          evText += '（摘要）';
        }
        html +=
          '<div class="paper-item' +
          (isAssigned ? ' assigned' : '') +
          (isCurrent ? ' current' : '') +
          ' clickable" data-paper-id="' + config.escapeHtml(paper.paper_id) + '"' +
          ' data-paper-title="' + config.escapeHtml(paper.title || paper.paper_id) + '"' +
          ' data-source="' + config.escapeHtml(source) + '">' +
          '<div class="paper-check">' + (isAssigned ? '✓' : '') + '</div>' +
          '<div class="paper-info">' +
          '<div class="paper-title">' + config.escapeHtml(paper.title || paper.paper_id) + ' ' + sourceBadge + '</div>' +
          '<div class="paper-meta">' + evText + ' · ' + config.escapeHtml(paper.paper_id) + '</div>' +
          '</div>' +
          '<button class="view-btn" data-paper-id="' + config.escapeHtml(paper.paper_id) + '" data-source="' + config.escapeHtml(source) + '" title="查看详细内容">👁️</button>' +
          '</div>';
      });

      config.container.innerHTML = html;

      // 绑定点击事件
      config.container.querySelectorAll('.paper-item.clickable').forEach(function(el) {
        el.addEventListener('click', function() {
          if (config.onPaperClick) {
            config.onPaperClick(this.dataset.paperId, this.dataset.paperTitle);
          }
        });
      });

      // 绑定查看按钮点击事件
      if (config.onViewClick) {
        config.container.querySelectorAll('.view-btn').forEach(function(btn) {
          btn.addEventListener('click', function(e) {
            e.stopPropagation();
            config.onViewClick(this.dataset.paperId, this.dataset.source);
          });
        });
      }
    }

    // ── 切换论文分配（返回是否已分配） ──
    function toggleAssignment(outlineData, selectedParagraphId, paperId) {
      if (!selectedParagraphId || !outlineData) return false;

      let assigned = false;
      for (const sec of outlineData.sections || []) {
        for (const para of sec.paragraphs || []) {
          if (para.paragraph_id === selectedParagraphId) {
            if (!para.assigned_paper_ids) para.assigned_paper_ids = [];
            const idx = para.assigned_paper_ids.indexOf(paperId);
            if (idx >= 0) {
              para.assigned_paper_ids.splice(idx, 1);
              assigned = false;
            } else {
              para.assigned_paper_ids.push(paperId);
              assigned = true;
            }
          }
        }
      }
      return assigned;
    }

    // ── 渲染本地文献库 ──
    function renderLocal(localPapers, currentPaperId) {
      if (!localPapers || localPapers.length === 0) {
        config.container.innerHTML =
          '<div class="paper-empty">' +
          '<div class="icon">📁</div>' +
          '<div>documents 目录下没有 PDF 文件</div>' +
          '</div>';
        return;
      }

      const parsedCount = localPapers.filter(function(p) { return p.parsed; }).length;
      // V25.14: 未解析文献也可点击，点击后触发解析
      let html = '<div class="paper-list-hint">共 ' + localPapers.length + ' 篇，已解析 ' + parsedCount + ' 篇 · 点击已解析文献打开 PDF，点击未解析文献开始解析</div>';

      localPapers.forEach(function(paper) {
        const isCurrent = paper.paper_id === currentPaperId;
        const statusClass = paper.parsed ? 'parsed' : 'unparsed';
        const statusText = paper.parsed
          ? (paper.paragraph_count > 0 ? paper.paragraph_count + ' 段解析' : '已解析')
          : '未解析 · 点击解析';
        // V25.17: 补充材料数量
        const suppCount = paper.supp_count || 0;
        const suppBadge = suppCount > 0
          ? '<span class="supp-badge" title="' + suppCount + ' 个补充材料">📎' + suppCount + '</span>'
          : '';
        // V25.14: 所有文献都可点击（未解析的点击后触发解析）
        html +=
          '<div class="paper-item local ' + statusClass +
          (isCurrent ? ' current' : '') +
          ' clickable"' +
          ' data-paper-id="' + (paper.paper_id ? config.escapeHtml(paper.paper_id) : '') + '"' +
          ' data-paper-title="' + config.escapeHtml(paper.title) + '"' +
          ' data-filename="' + config.escapeHtml(paper.filename) + '"' +
          ' data-parsed="' + (paper.parsed ? '1' : '0') + '"' +
          '>' +
          '<div class="paper-check">' + (paper.parsed ? '✓' : '○') + '</div>' +
          '<div class="paper-info">' +
          '<div class="paper-title">' + config.escapeHtml(paper.title) + suppBadge + '</div>' +
          '<div class="paper-meta">' +
          (paper.authors ? config.escapeHtml(paper.authors.substring(0, 40)) + ' · ' : '') +
          (paper.year ? paper.year + ' · ' : '') +
          paper.file_size_mb + ' MB · ' + statusText +
          '</div>' +
          '<div class="paper-filename">' + config.escapeHtml(paper.filename) + '</div>' +
          '</div>' +
          // V25.17: 补充材料管理按钮（仅已解析论文显示）
          (paper.parsed && paper.paper_id
            ? '<button class="supp-manage-btn" data-paper-id="' + config.escapeHtml(paper.paper_id) + '" data-paper-title="' + config.escapeHtml(paper.title) + '" title="管理补充材料">📎</button>'
            : '') +
          '</div>';
      });

      config.container.innerHTML = html;

      if (config.onLocalPaperClick) {
        config.container.querySelectorAll('.paper-item.local.clickable').forEach(function(el) {
          el.addEventListener('click', function() {
            // V25.14: 传递 parsed 状态，未解析的点击后触发解析
            config.onLocalPaperClick(
              this.dataset.paperId,
              this.dataset.paperTitle,
              this.dataset.filename,
              this.dataset.parsed === '1'
            );
          });
        });
      }

      // V25.17: 绑定补充材料管理按钮（阻止冒泡）
      if (config.onSupplementaryClick) {
        config.container.querySelectorAll('.supp-manage-btn').forEach(function(btn) {
          btn.addEventListener('click', function(e) {
            e.stopPropagation();
            config.onSupplementaryClick(this.dataset.paperId, this.dataset.paperTitle);
          });
        });
      }
    }

    // ── 渲染摘要库 ──
    function renderAbstracts(abstracts, currentPaperId) {
      if (!abstracts || abstracts.length === 0) {
        config.container.innerHTML =
          '<div class="paper-empty">' +
          '<div class="icon">📄</div>' +
          '<div>摘要库中没有相关文献</div>' +
          '</div>';
        return;
      }

      let html = '<div class="paper-list-hint">共 ' + abstracts.length + ' 篇摘要 · 点击论文在右侧打开摘要</div>';

      abstracts.forEach(function(paper) {
        const isCurrent = paper.paper_id === currentPaperId;
        html +=
          '<div class="paper-item abstract' +
          (isCurrent ? ' current' : '') +
          ' clickable" data-paper-id="' + config.escapeHtml(paper.paper_id) + '"' +
          ' data-paper-title="' + config.escapeHtml(paper.title || paper.paper_id) + '"' +
          ' data-source="abstract">' +
          '<div class="paper-check"></div>' +
          '<div class="paper-info">' +
          '<div class="paper-title">' + config.escapeHtml(paper.title || paper.paper_id) + ' <span class="source-badge abstract" title="摘要库">摘要</span></div>' +
          '<div class="paper-meta">' + config.escapeHtml(paper.journal || '') + ' · ' + config.escapeHtml(paper.year || '') + '</div>' +
          '</div>' +
          '<button class="view-btn" data-paper-id="' + config.escapeHtml(paper.paper_id) + '" data-source="abstract" title="查看详细内容">👁️</button>' +
          '</div>';
      });

      config.container.innerHTML = html;

      // 绑定点击事件
      config.container.querySelectorAll('.paper-item.clickable').forEach(function(el) {
        el.addEventListener('click', function() {
          if (config.onPaperClick) {
            config.onPaperClick(this.dataset.paperId, this.dataset.paperTitle);
          }
        });
      });

      // 绑定查看按钮点击事件
      if (config.onViewClick) {
        config.container.querySelectorAll('.view-btn').forEach(function(btn) {
          btn.addEventListener('click', function(e) {
            e.stopPropagation();
            config.onViewClick(this.dataset.paperId, this.dataset.source);
          });
        });
      }
    }

    return {
      render: render,
      renderLocal: renderLocal,
      renderAbstracts: renderAbstracts,
      toggleAssignment: toggleAssignment,
    };
  }

  window.SciPal = window.SciPal || {};
  window.SciPal.createPaperList = createPaperList;

})();
