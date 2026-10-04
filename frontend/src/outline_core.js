/* V25.10 - Sci-Pal 大纲核心模块（独立）
 *
 * 职责：
 * 1. 大纲数据状态管理（sections → paragraphs）
 * 2. 渲染大纲结构（章节/段落/操作按钮）
 * 3. 增删改：添加/删除章节、添加/删除段落、编辑标题/主题/描述
 * 4. 段落排序（上移/下移）
 * 5. 段落选中
 * 6. 统计信息更新
 *
 * 不负责：论文列表、PDF 渲染、标注、后端通信
 */

(function() {
  'use strict';

  /**
   * 创建大纲核心管理器
   * @param {Object} config
   * @param {HTMLElement} config.container - 大纲内容容器
   * @param {HTMLElement} config.statsEl - 统计信息元素
   * @param {Function} config.onParagraphSelect - 段落选中回调 (paragraphId)
   * @param {Function} config.onOutlineChanged - 大纲变更回调（增删改后通知其他模块刷新）
   * @param {Function} config.escapeHtml - HTML 转义函数
   */
  function createOutlineCore(config) {
    const state = {
      data: null,           // {sections: [...]}
      selectedId: null,     // 当前选中段落 ID
      paraIdCounter: 0,     // 新段落 ID 计数器
    };

    // ── 设置大纲数据 ──
    function setData(outlineData) {
      state.data = outlineData || { sections: [] };
      state.selectedId = null;
      state.paraIdCounter = 0;
      render();
      updateStats();
    }

    function getData() { return state.data; }
    function getSelectedId() { return state.selectedId; }

    // ── 生成唯一段落 ID ──
    function generateParagraphId() {
      state.paraIdCounter++;
      return 'para_custom_' + Date.now() + '_' + state.paraIdCounter;
    }

    // ── 渲染大纲 ──
    function render() {
      if (!state.data || !state.data.sections || state.data.sections.length === 0) {
        config.container.innerHTML =
          '<div class="outline-empty">' +
          '<div class="icon">📝</div>' +
          '<div>输入综述主题，点击"生成大纲"<br>系统将自动生成段落级大纲供你编辑</div>' +
          '<div class="hint">你可以：编辑标题/主题 · 增删章节段落 · 调整顺序 · 分配论文 · 保存/加载</div>' +
          '</div>';
        return;
      }

      let html = '<div class="outline-toolbar">' +
        '<button class="btn-small btn-add-section" title="添加新章节">＋ 添加章节</button>' +
        '</div>';

      state.data.sections.forEach(function(section, secIdx) {
        html += '<div class="outline-section" data-sec-idx="' + secIdx + '">';

        // 章节 header
        html += '<div class="outline-section-header">' +
          '<span class="section-number">' + (secIdx + 1) + '</span>' +
          '<span class="section-title" contenteditable="true" data-sec-idx="' + secIdx + '"' +
          ' title="点击编辑章节标题">' + config.escapeHtml(section.title) + '</span>';
        if (section.description) {
          html += '<span class="section-desc">' + config.escapeHtml(section.description) + '</span>';
        }
        html += '<div class="section-actions">' +
          '<button class="section-btn del" data-sec-idx="' + secIdx + '" title="删除此章节">✕</button>' +
          '</div></div>';

        // V32.1: 章节关键词编辑字段
        const sectionKeywords = (section.keywords || []).join(', ');
        html += '<div class="section-keywords-row">' +
          '<span class="keywords-label">🔑 关键词:</span>' +
          '<input type="text" class="section-keywords-input" data-sec-idx="' + secIdx + '"' +
          ' value="' + config.escapeHtml(sectionKeywords) + '"' +
          ' placeholder="用逗号分隔，用于搜索文献" title="编辑章节关键词，用于搜索文献">' +
          '</div>';

        // 段落列表
        html += '<div class="outline-paragraphs">';
        (section.paragraphs || []).forEach(function(para, paraIdx) {
          const isSelected = para.paragraph_id === state.selectedId;
          const assignedCount = (para.assigned_paper_ids || []).length;
          html +=
            '<div class="outline-paragraph' + (isSelected ? ' selected' : '') + '"' +
            ' data-sec-idx="' + secIdx + '" data-para-idx="' + paraIdx + '"' +
            ' data-paragraph-id="' + para.paragraph_id + '">' +
            '<div class="para-drag-handle" title="拖拽排序">⋮⋮</div>' +
            '<div class="para-content">' +
            '<div class="para-topic" contenteditable="true" data-sec-idx="' + secIdx + '" data-para-idx="' + paraIdx + '"' +
            ' title="点击编辑段落主题">' + config.escapeHtml(para.topic) + '</div>' +
            '<div class="para-desc" contenteditable="true" data-sec-idx="' + secIdx + '" data-para-idx="' + paraIdx + '"' +
            ' title="点击编辑段落描述（可选）">' + config.escapeHtml(para.description || '点击添加段落描述...') + '</div>' +
            // V32.1: 段落关键词编辑字段
            '<div class="para-keywords-row">' +
            '<span class="keywords-label">🔑</span>' +
            '<input type="text" class="para-keywords-input" data-sec-idx="' + secIdx + '" data-para-idx="' + paraIdx + '"' +
            ' value="' + config.escapeHtml((para.keywords || []).join(', ')) + '"' +
            ' placeholder="关键词，用逗号分隔" title="编辑段落关键词，用于搜索文献">' +
            '</div>' +
            '<div class="para-meta">' +
            '<span class="para-badge">段落 ' + (paraIdx + 1) + '</span>' +
            (assignedCount > 0
              ? '<span class="para-badge assigned">已分配 ' + assignedCount + ' 篇论文</span>'
              : '<span class="para-badge unassigned">未分配论文</span>') +
            '</div></div>' +
            '<div class="para-actions">' +
            '<button class="para-btn up" data-sec-idx="' + secIdx + '" data-para-idx="' + paraIdx + '"' +
            ' title="上移"' + (paraIdx === 0 ? ' disabled' : '') + '>↑</button>' +
            '<button class="para-btn down" data-sec-idx="' + secIdx + '" data-para-idx="' + paraIdx + '"' +
            ' title="下移"' + (paraIdx === section.paragraphs.length - 1 ? ' disabled' : '') + '>↓</button>' +
            '<button class="para-btn del" data-sec-idx="' + secIdx + '" data-para-idx="' + paraIdx + '"' +
            ' title="删除此段落">✕</button>' +
            '</div></div>';
        });

        // 添加段落按钮
        html += '<div class="add-paragraph-row">' +
          '<button class="btn-small btn-add-paragraph" data-sec-idx="' + secIdx + '">＋ 添加段落</button>' +
          '</div></div></div>';
      });

      config.container.innerHTML = html;
      bindEvents();
      if (config.onOutlineChanged) config.onOutlineChanged();
    }

    // ── 绑定事件 ──
    function bindEvents() {
      // 添加章节
      const addSecBtn = config.container.querySelector('.btn-add-section');
      if (addSecBtn) {
        addSecBtn.addEventListener('click', function(e) {
          e.stopPropagation();
          addSection();
        });
      }

      // 章节标题编辑
      config.container.querySelectorAll('.section-title').forEach(function(el) {
        el.addEventListener('blur', function() {
          const secIdx = parseInt(this.dataset.secIdx);
          const newTitle = this.textContent.trim();
          if (newTitle && state.data.sections[secIdx]) {
            state.data.sections[secIdx].title = newTitle;
          } else if (!newTitle && state.data.sections[secIdx]) {
            this.textContent = state.data.sections[secIdx].title;
          }
        });
        el.addEventListener('keydown', function(e) {
          if (e.key === 'Enter') { e.preventDefault(); this.blur(); }
        });
      });

      // V32.1: 章节关键词编辑
      config.container.querySelectorAll('.section-keywords-input').forEach(function(el) {
        el.addEventListener('blur', function() {
          const secIdx = parseInt(this.dataset.secIdx);
          const value = this.value.trim();
          if (state.data.sections[secIdx]) {
            if (value) {
              state.data.sections[secIdx].keywords = value.split(',').map(function(k) { return k.trim(); }).filter(function(k) { return k; });
            } else {
              state.data.sections[secIdx].keywords = [];
            }
            if (config.onOutlineChanged) config.onOutlineChanged();
          }
        });
        el.addEventListener('keydown', function(e) {
          if (e.key === 'Enter') { e.preventDefault(); this.blur(); }
        });
      });

      // 删除章节
      config.container.querySelectorAll('.section-btn.del').forEach(function(btn) {
        btn.addEventListener('click', function(e) {
          e.stopPropagation();
          deleteSection(parseInt(this.dataset.secIdx));
        });
      });

      // 段落点击选中
      config.container.querySelectorAll('.outline-paragraph').forEach(function(el) {
        el.addEventListener('click', function(e) {
          if (e.target.isContentEditable || e.target.classList.contains('para-btn') || e.target.classList.contains('section-btn')) return;
          selectParagraph(this.dataset.paragraphId);
        });
      });

      // 段落主题编辑
      config.container.querySelectorAll('.para-topic').forEach(function(el) {
        el.addEventListener('blur', function() {
          const secIdx = parseInt(this.dataset.secIdx);
          const paraIdx = parseInt(this.dataset.paraIdx);
          const newTopic = this.textContent.trim();
          if (newTopic && state.data.sections[secIdx].paragraphs[paraIdx]) {
            state.data.sections[secIdx].paragraphs[paraIdx].topic = newTopic;
          } else if (!newTopic && state.data.sections[secIdx].paragraphs[paraIdx]) {
            this.textContent = state.data.sections[secIdx].paragraphs[paraIdx].topic;
          }
        });
        el.addEventListener('keydown', function(e) {
          if (e.key === 'Enter') { e.preventDefault(); this.blur(); }
        });
      });

      // 段落描述编辑
      config.container.querySelectorAll('.para-desc').forEach(function(el) {
        el.addEventListener('blur', function() {
          const secIdx = parseInt(this.dataset.secIdx);
          const paraIdx = parseInt(this.dataset.paraIdx);
          let newDesc = this.textContent.trim();
          if (newDesc === '点击添加段落描述...') newDesc = '';
          if (state.data.sections[secIdx].paragraphs[paraIdx]) {
            state.data.sections[secIdx].paragraphs[paraIdx].description = newDesc;
          }
          if (!newDesc) this.textContent = '点击添加段落描述...';
        });
        el.addEventListener('focus', function() {
          if (this.textContent.trim() === '点击添加段落描述...') this.textContent = '';
        });
        el.addEventListener('keydown', function(e) {
          if (e.key === 'Enter') { e.preventDefault(); this.blur(); }
        });
      });

      // V32.1: 段落关键词编辑
      config.container.querySelectorAll('.para-keywords-input').forEach(function(el) {
        el.addEventListener('blur', function() {
          const secIdx = parseInt(this.dataset.secIdx);
          const paraIdx = parseInt(this.dataset.paraIdx);
          const value = this.value.trim();
          if (state.data.sections[secIdx] && state.data.sections[secIdx].paragraphs[paraIdx]) {
            if (value) {
              state.data.sections[secIdx].paragraphs[paraIdx].keywords = value.split(',').map(function(k) { return k.trim(); }).filter(function(k) { return k; });
            } else {
              state.data.sections[secIdx].paragraphs[paraIdx].keywords = [];
            }
            if (config.onOutlineChanged) config.onOutlineChanged();
          }
        });
        el.addEventListener('keydown', function(e) {
          if (e.key === 'Enter') { e.preventDefault(); this.blur(); }
        });
      });

      // 上移/下移
      config.container.querySelectorAll('.para-btn.up').forEach(function(btn) {
        btn.addEventListener('click', function(e) {
          e.stopPropagation();
          moveParagraph(parseInt(this.dataset.secIdx), parseInt(this.dataset.paraIdx), -1);
        });
      });
      config.container.querySelectorAll('.para-btn.down').forEach(function(btn) {
        btn.addEventListener('click', function(e) {
          e.stopPropagation();
          moveParagraph(parseInt(this.dataset.secIdx), parseInt(this.dataset.paraIdx), 1);
        });
      });

      // 删除段落
      config.container.querySelectorAll('.para-btn.del').forEach(function(btn) {
        btn.addEventListener('click', function(e) {
          e.stopPropagation();
          deleteParagraph(parseInt(this.dataset.secIdx), parseInt(this.dataset.paraIdx));
        });
      });

      // 添加段落
      config.container.querySelectorAll('.btn-add-paragraph').forEach(function(btn) {
        btn.addEventListener('click', function(e) {
          e.stopPropagation();
          addParagraph(parseInt(this.dataset.secIdx));
        });
      });
    }

    // ── 增删改操作 ──
    function addSection() {
      if (!state.data) return;
      const secNum = state.data.sections.length + 1;
      state.data.sections.push({
        section_id: 'sec_custom_' + Date.now(),
        title: 'New Section ' + secNum,
        description: '',
        assigned_paper_ids: [],
        paragraphs: [{
          paragraph_id: generateParagraphId(),
          topic: 'New paragraph topic',
          description: '',
          order: 0,
          assigned_paper_ids: [],
          assigned_evidence_ids: [],
        }],
      });
      render();
      updateStats();
    }

    function deleteSection(secIdx) {
      if (!state.data || !state.data.sections[secIdx]) return;
      const title = state.data.sections[secIdx].title;
      if (!confirm('确定删除章节「' + title + '」及其所有段落吗？')) return;
      state.data.sections.splice(secIdx, 1);
      // 检查选中段落是否还在
      if (state.selectedId) {
        let stillExists = false;
        for (const sec of state.data.sections) {
          for (const p of sec.paragraphs || []) {
            if (p.paragraph_id === state.selectedId) stillExists = true;
          }
        }
        if (!stillExists) state.selectedId = null;
      }
      render();
      updateStats();
      if (config.onParagraphSelect) config.onParagraphSelect(state.selectedId);
    }

    function addParagraph(secIdx) {
      if (!state.data || !state.data.sections[secIdx]) return;
      const section = state.data.sections[secIdx];
      if (!section.paragraphs) section.paragraphs = [];
      section.paragraphs.push({
        paragraph_id: generateParagraphId(),
        topic: 'New paragraph topic',
        description: '',
        order: section.paragraphs.length,
        assigned_paper_ids: [],
        assigned_evidence_ids: [],
      });
      render();
      updateStats();
    }

    function deleteParagraph(secIdx, paraIdx) {
      if (!state.data || !state.data.sections[secIdx]) return;
      const para = state.data.sections[secIdx].paragraphs[paraIdx];
      if (!para) return;
      if (!confirm('确定删除段落「' + para.topic + '」吗？')) return;
      state.data.sections[secIdx].paragraphs.splice(paraIdx, 1);
      state.data.sections[secIdx].paragraphs.forEach(function(p, i) { p.order = i; });
      if (para.paragraph_id === state.selectedId) state.selectedId = null;
      render();
      updateStats();
      if (config.onParagraphSelect) config.onParagraphSelect(state.selectedId);
    }

    function moveParagraph(secIdx, paraIdx, direction) {
      const section = state.data.sections[secIdx];
      const paragraphs = section.paragraphs;
      const newIdx = paraIdx + direction;
      if (newIdx < 0 || newIdx >= paragraphs.length) return;
      var tmp = paragraphs[paraIdx];
      paragraphs[paraIdx] = paragraphs[newIdx];
      paragraphs[newIdx] = tmp;
      paragraphs.forEach(function(p, i) { p.order = i; });
      render();
    }

    function selectParagraph(paragraphId) {
      state.selectedId = paragraphId;
      render();
      if (config.onParagraphSelect) config.onParagraphSelect(paragraphId);
    }

    // ── 统计 ──
    function updateStats() {
      if (!config.statsEl || !state.data || !state.data.sections) {
        if (config.statsEl) config.statsEl.textContent = '';
        return;
      }
      const secCount = state.data.sections.length;
      const paraCount = state.data.sections.reduce(function(sum, s) {
        return sum + (s.paragraphs || []).length;
      }, 0);
      const assignedCount = state.data.sections.reduce(function(sum, s) {
        return sum + (s.paragraphs || []).reduce(function(ps, p) {
          return ps + (p.assigned_paper_ids || []).length;
        }, 0);
      }, 0);
      config.statsEl.textContent = secCount + ' 章节 · ' + paraCount + ' 段落 · 已分配 ' + assignedCount + ' 篇次';
    }

    return {
      setData: setData,
      getData: getData,
      getSelectedId: getSelectedId,
      render: render,
      updateStats: updateStats,
      selectParagraph: selectParagraph,
      addSection: addSection,
      deleteSection: deleteSection,
      addParagraph: addParagraph,
      deleteParagraph: deleteParagraph,
      moveParagraph: moveParagraph,
    };
  }

  window.SciPal = window.SciPal || {};
  window.SciPal.createOutlineCore = createOutlineCore;

})();
