/* V25.10 - Sci-Pal 大纲编辑器主入口（协调各独立模块）
 *
 * 职责：
 * 1. DOM 缓存与初始化
 * 2. 后端通信（生成大纲、生成综述、保存/加载大纲）
 * 3. 协调各模块：OutlineCore / PaperList / PdfViewer / PdfAnnotator
 * 4. "分配到段落"下拉菜单更新
 * 5. 工具函数（escapeHtml / showMessage）
 *
 * 模块拆分：
 * - outline_core.js   大纲渲染/增删改/排序
 * - paper_list.js     论文列表渲染/分配
 * - pdf_viewer.js     PDF 加载（iframe 浏览器原生渲染，V25.14）
 */

(function() {
  'use strict';

  // ── 共享状态 ──
  let papers = [];
  let localPapers = [];
  let abstractPapers = [];  // V26.5: 摘要库论文列表
  let currentTab = 'related';
  let currentTopic = '';
  let currentReviewType = 'narrative';
  let savedOutlines = [];

  // ── 模块实例 ──
  let outlineCore = null;
  let paperList = null;
  let pdfViewer = null;
  let supplementaryManager = null;  // V25.17
  let paperImporter = null;          // V25.17

  // ── DOM 缓存 ──
  const els = {};

  document.addEventListener('DOMContentLoaded', init);

  function init() {
    // V25.17 修复：把模态框移到 body 下面，避免被 #reviewContainer 的 transform 影响导致大小为0
    ['supplementary-modal', 'import-modal'].forEach(function(id) {
      var el = document.getElementById(id);
      if (el && el.parentElement !== document.body) {
        document.body.appendChild(el);
      }
    });

    els.outlineEditor = document.getElementById('outlineEditor');
    els.outlineContent = document.getElementById('outlineContent');
    els.paperList = document.getElementById('paperList');
    els.topicInput = document.getElementById('editorTopicInput');
    els.reviewTypeSelect = document.getElementById('editorReviewType');
    els.maxPapersInput = document.getElementById('editorMaxPapers');
    els.generateOutlineBtn = document.getElementById('generateOutlineBtn');
    els.assignPapersBtn = document.getElementById('assignPapersBtn');  // V26.1
    els.searchAndAssignBtn = document.getElementById('searchAndAssignBtn');  // V31.75
    els.confirmAssignBtn = document.getElementById('confirmAssignBtn');  // V26.1
    els.generateReviewBtn = document.getElementById('generateReviewBtn');
    els.saveOutlineBtn = document.getElementById('saveOutlineBtn');
    els.loadOutlineSelect = document.getElementById('loadOutlineSelect');
    els.loadOutlineBtn = document.getElementById('loadOutlineBtn');
    els.swapLayoutBtn = document.getElementById('swapLayoutBtn');
    els.outlineStats = document.getElementById('outlineStats');
    els.editorMessage = document.getElementById('editorMessage');
    els.assignParaSelect = document.getElementById('oeAssignParaSelect');

    els.oePdfContainer = document.getElementById('oePdfContainer');
    // V25.17: 补充材料管理面板
    els.supplementaryPanel = document.getElementById('supplementary-panel');
    // V25.17: 文献导入
    els.importPanel = document.getElementById('import-panel');
    els.importPaperBtn = document.getElementById('importPaperBtn');
    els.oePdfTitle = document.getElementById('oePdfTitle');
    els.oePdfPageInfo = document.getElementById('oePdfPageInfo');
    els.oePdfPageInput = document.getElementById('oePdfPageInput');
    els.oePdfZoomLabel = document.getElementById('oePdfZoomLabel');

    // V25.11: tab 切换按钮
    els.tabButtons = document.querySelectorAll('.panel-tab');

    if (!els.outlineEditor) return;

    initModules();

    els.generateOutlineBtn.addEventListener('click', handleGenerateOutline);
    if (els.assignPapersBtn) els.assignPapersBtn.addEventListener('click', handleAssignPapers);  // V26.1
    if (els.searchAndAssignBtn) els.searchAndAssignBtn.addEventListener('click', handleSearchAndAssign);  // V31.75
    if (els.confirmAssignBtn) els.confirmAssignBtn.addEventListener('click', handleConfirmAssign);  // V26.1
    els.generateReviewBtn.addEventListener('click', handleGenerateReview);
    els.saveOutlineBtn.addEventListener('click', handleSaveOutline);
    els.loadOutlineBtn.addEventListener('click', handleLoadOutline);
    if (els.swapLayoutBtn) els.swapLayoutBtn.addEventListener('click', swapLayout);

    els.topicInput.addEventListener('keydown', function(e) {
      if (e.key === 'Enter') handleGenerateOutline();
    });

    // V25.11: tab 切换
    els.tabButtons.forEach(function(btn) {
      btn.addEventListener('click', function() {
        switchTab(this.dataset.tab);
      });
    });

    // V25.14: 移除翻页/缩放全局函数（浏览器自带 PDF 工具栏替代）
    window.oeAssignToParagraph = oeAssignToParagraph;

    applySavedLayout();
    loadSavedOutlines();
    restoreRunningTask();  // V26.5: 刷新页面后恢复任务
  }

  // V26.5: 刷新页面后恢复任务
  async function restoreRunningTask() {
    try {
      const resp = await fetch('/api/review/running_task');
      if (!resp.ok) return;
      const data = await resp.json();
      
      if (data.running && data.task) {
        // 有运行中的任务，恢复轮询
        currentTaskId = data.task.task_id;
        taskState = 'running';
        els.generateOutlineBtn.textContent = '取消';
        els.generateOutlineBtn.classList.add('cancel-mode');
        els.generateOutlineBtn.disabled = false;
        
        showMessage('检测到正在运行的任务，已恢复监控...', 'info');
        pollTaskStatus(currentTaskId);
      }
    } catch (e) {
      console.error('恢复任务失败:', e);
    }
  }

  // ── 初始化各独立模块 ──
  function initModules() {
    outlineCore = window.SciPal.createOutlineCore({
      container: els.outlineContent,
      statsEl: els.outlineStats,
      escapeHtml: escapeHtml,
      onParagraphSelect: function() {
        refreshPaperList();
        updateAssignSelect();
      },
      onOutlineChanged: function() {
        updateAssignSelect();
      },
    });

    paperList = window.SciPal.createPaperList({
      container: els.paperList,
      escapeHtml: escapeHtml,
      onPaperClick: function(paperId, paperTitle) {
        // V26.4: 根据 paperId 找到对应的 paper 对象，获取 source 参数
        const paper = papers.find(p => p.paper_id === paperId);
        const source = paper ? (paper.source || 'full_text') : 'full_text';
        pdfViewer.load(paperId, paperTitle, source);  // 传递 source 参数
        const selectedId = outlineCore.getSelectedId();
        if (selectedId) {
          paperList.toggleAssignment(outlineCore.getData(), selectedId, paperId);
          outlineCore.render();
          outlineCore.updateStats();
        }
      },
      // V26.1: 查看按钮回调 - 区分摘要和全文
      onViewClick: function(paperId, source) {
        if (source === 'abstract') {
          // 摘要库的论文：加载摘要
          pdfViewer.loadAbstract(paperId);
        } else {
          // 全文库的论文：加载 PDF
          const paper = papers.find(p => p.paper_id === paperId);
          const title = paper ? paper.title : paperId;
          pdfViewer.load(paperId, title);
        }
      },
      onLocalPaperClick: function(paperId, paperTitle, filename, parsed) {
        // V25.14: 未解析文献点击后触发解析，解析完成后自动打开 PDF
        if (parsed && paperId) {
          // 已解析：直接打开 PDF
          pdfViewer.load(paperId, paperTitle);
          showMessage('已打开：' + paperTitle, 'info');
        } else {
          // 未解析：触发解析
          parseAndOpenPaper(filename, paperTitle);
        }
      },
      // V25.17: 补充材料管理按钮
      onSupplementaryClick: function(paperId, paperTitle) {
        if (supplementaryManager) {
          supplementaryManager.open(paperId, paperTitle);
        }
      },
    });

    // V25.17: 初始化补充材料管理器
    if (els.supplementaryPanel && window.SciPal.createSupplementaryManager) {
      supplementaryManager = window.SciPal.createSupplementaryManager({
        container: els.supplementaryPanel,
        escapeHtml: escapeHtml,
        onFileAdded: function(paperId, count) {
          // 补充材料变化后刷新文献列表（更新徽标数量）
          refreshPaperList();
        },
      });
    }

    // V25.17: 初始化文献导入器
    console.log('[V25.17调试] importPanel元素:', els.importPanel);
    console.log('[V25.17调试] importPaperBtn元素:', els.importPaperBtn);
    console.log('[V25.17调试] createPaperImporter函数:', window.SciPal.createPaperImporter);
    if (els.importPanel && window.SciPal.createPaperImporter) {
      paperImporter = window.SciPal.createPaperImporter({
        container: els.importPanel,
        escapeHtml: escapeHtml,
        onRefreshList: function() {
          refreshPaperList();
        },
        onImportComplete: function(paperId, paperTitle, filename) {
          // 导入完成后自动打开 PDF
          if (pdfViewer && paperId) {
            pdfViewer.load(paperId, paperTitle);
          }
        },
      });
      console.log('[V25.17调试] ✅ paperImporter 初始化成功');
    } else {
      console.log('[V25.17调试] ❌ paperImporter 初始化失败:',
        'importPanel=' + !!els.importPanel,
        'createPaperImporter=' + !!window.SciPal.createPaperImporter);
    }

    // V25.17: 绑定导入文献按钮
    console.log('[V25.17调试] 绑定按钮前: importPaperBtn=' + !!els.importPaperBtn + ', paperImporter=' + !!paperImporter);
    if (els.importPaperBtn && paperImporter) {
      els.importPaperBtn.addEventListener('click', function() {
        console.log('[V25.17调试] 📥 导入文献按钮被点击');
        paperImporter.open();
      });
      console.log('[V25.17调试] ✅ 导入文献按钮事件绑定成功');
    } else {
      console.log('[V25.17调试] ❌ 导入文献按钮事件绑定失败');
    }

    // V25.14: PDF 阅读器改为 iframe 浏览器原生渲染，移除标注/翻页/缩放控制
    pdfViewer = window.SciPal.createPdfViewer({
      container: els.oePdfContainer,
      titleEl: els.oePdfTitle,
      onPaperLoaded: function() {
        refreshPaperList();
        updateAssignSelect();
      },
    });
  }

  // ── V25.14: 解析未解析文献并打开 PDF ──
  let isParsing = false;  // 防止重复点击

  function parseAndOpenPaper(filename, paperTitle) {
    if (isParsing) {
      showMessage('正在解析中，请稍候...', 'warning');
      return;
    }

    isParsing = true;
    showMessage('正在解析：' + (paperTitle || filename) + '（可能需要 30-60 秒）...', 'info');

    fetch('/api/papers/parse', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ filename: filename }),
    })
    .then(function(res) { return res.json(); })
    .then(function(data) {
      isParsing = false;
      if (data.error) {
        showMessage('解析失败：' + data.error, 'error');
        return;
      }
      // 解析成功，刷新本地文献列表并打开 PDF
      showMessage('解析完成：' + data.title + '（' + data.paragraph_count + ' 段），正在打开 PDF...', 'success');
      if (data.paper_id) {
        pdfViewer.load(data.paper_id, data.title);
      }
      // 强制刷新本地文献列表状态（清空缓存，重新从服务器获取最新解析状态）
      localPapers = [];
      loadLocalPapers();
    })
    .catch(function(err) {
      isParsing = false;
      showMessage('解析请求失败：' + err.message, 'error');
    });
  }

  function refreshPaperList() {
    if (!paperList) return;
    if (currentTab === 'local') {
      paperList.renderLocal(localPapers, pdfViewer ? pdfViewer.getState().paperId : null);
    } else if (currentTab === 'abstracts') {
      // V26.5: 摘要库
      paperList.render(
        abstractPapers,
        outlineCore ? outlineCore.getData() : null,
        outlineCore ? outlineCore.getSelectedId() : null,
        pdfViewer ? pdfViewer.getState().paperId : null
      );
    } else {
      paperList.render(
        papers,
        outlineCore ? outlineCore.getData() : null,
        outlineCore ? outlineCore.getSelectedId() : null,
        pdfViewer ? pdfViewer.getState().paperId : null
      );
    }
  }

  // ── V25.11: tab 切换 ──
  function switchTab(tab) {
    currentTab = tab;
    els.tabButtons.forEach(function(btn) {
      btn.classList.toggle('active', btn.dataset.tab === tab);
    });
    if (tab === 'local') {
      loadLocalPapers();
    } else if (tab === 'abstracts') {
      loadAbstracts();  // V26.5: 摘要库
    } else {
      refreshPaperList();
    }
  }

  // ── V25.13: 左右栏互换布局 ──
  let layoutSwapped = false; // 当前布局状态

  // 直接设置布局（不翻转状态，供初始化用）
  function setLayout(swapped) {
    if (swapped === layoutSwapped) return;
    const main = document.querySelector('.editor-main');
    if (!main) return;
    const left = main.querySelector('.editor-left');
    const pdf = main.querySelector('.editor-pdf');
    if (!left || !pdf) return;

    // 占位符法交换（可靠）
    const leftPh = document.createTextNode('');
    const pdfPh = document.createTextNode('');
    left.replaceWith(leftPh);
    pdf.replaceWith(pdfPh);
    leftPh.replaceWith(pdf);
    pdfPh.replaceWith(left);

    layoutSwapped = swapped;
  }

  // 点击按钮：翻转布局
  function swapLayout() {
    setLayout(!layoutSwapped);
    try {
      localStorage.setItem('scipal_layout_swapped', layoutSwapped.toString());
    } catch (e) {}
    if (els.swapLayoutBtn) {
      els.swapLayoutBtn.textContent = layoutSwapped ? '↔ 恢复布局' : '↔ 互换布局';
    }
  }

  // 初始化：从 localStorage 恢复布局
  function applySavedLayout() {
    try {
      const swapped = localStorage.getItem('scipal_layout_swapped') === 'true';
      setLayout(swapped);
      if (els.swapLayoutBtn) {
        els.swapLayoutBtn.textContent = swapped ? '↔ 恢复布局' : '↔ 互换布局';
      }
    } catch (e) {}
  }

  // ── V25.11: 加载本地文献库 ──
  async function loadLocalPapers() {
    if (localPapers.length > 0) {
      refreshPaperList();
      return;
    }
    try {
      const resp = await fetch('/api/papers/local');
      if (!resp.ok) throw new Error('加载失败');
      const data = await resp.json();
      localPapers = data.papers || [];
      refreshPaperList();
    } catch (e) {
      showMessage('加载本地文献库失败：' + e.message, 'error');
    }
  }

  // ── V26.5: 加载摘要库 ──
  async function loadAbstracts() {
    if (abstractPapers.length > 0) {
      refreshPaperList();
      return;
    }
    try {
      showMessage('正在加载摘要库...', 'info');
      const resp = await fetch('/api/abstracts/list?page=1&page_size=50');
      if (!resp.ok) throw new Error('加载失败');
      const data = await resp.json();
      abstractPapers = data.papers || [];
      refreshPaperList();
      showMessage('摘要库加载完成，共 ' + data.total + ' 篇摘要', 'success');
    } catch (e) {
      showMessage('加载摘要库失败：' + e.message, 'error');
    }
  }

  function updateAssignSelect() {
    if (!els.assignParaSelect || !outlineCore) return;
    const data = outlineCore.getData();
    const currentPaperId = pdfViewer ? pdfViewer.getState().paperId : null;

    if (!data || !data.sections || data.sections.length === 0) {
      els.assignParaSelect.innerHTML = '<option value="">分配到段落…</option>';
      return;
    }

    let html = '<option value="">分配到段落…</option>';
    data.sections.forEach(function(sec, secIdx) {
      (sec.paragraphs || []).forEach(function(para, paraIdx) {
        const isAssigned = currentPaperId && (para.assigned_paper_ids || []).indexOf(currentPaperId) >= 0;
        const label = (secIdx + 1) + '.' + (paraIdx + 1) + ' ' + para.topic + (isAssigned ? ' ✓' : '');
        html += '<option value="' + para.paragraph_id + '"' + (isAssigned ? ' selected' : '') + '>' +
          escapeHtml(label) + '</option>';
      });
    });
    els.assignParaSelect.innerHTML = html;
  }

  function oeAssignToParagraph(paragraphId) {
    const currentPaperId = pdfViewer ? pdfViewer.getState().paperId : null;
    if (!currentPaperId || !paragraphId || !outlineCore) return;

    const data = outlineCore.getData();
    for (const sec of data.sections || []) {
      for (const para of sec.paragraphs || []) {
        if (para.paragraph_id === paragraphId) {
          if (!para.assigned_paper_ids) para.assigned_paper_ids = [];
          const idx = para.assigned_paper_ids.indexOf(currentPaperId);
          if (idx >= 0) {
            para.assigned_paper_ids.splice(idx, 1);
            showMessage('已从段落移除该论文', 'info');
          } else {
            para.assigned_paper_ids.push(currentPaperId);
            showMessage('论文已分配到段落', 'success');
          }
        }
      }
    }

    outlineCore.render();
    refreshPaperList();
    updateAssignSelect();
  }

  // ── 后端通信 ──
  let currentTaskId = null;  // V26.3: 当前任务的 task_id
  let taskPollTimer = null;  // V26.3: 轮询定时器
  let taskState = 'idle';    // V26.4: 任务状态：idle / running / cancelling

  async function handleGenerateOutline() {
    const topic = els.topicInput.value.trim();
    if (!topic) {
      showMessage('请输入综述主题', 'error');
      return;
    }

    // V26.4: 如果是取消中状态，什么也不做（按钮已经禁用了）
    if (taskState === 'cancelling') {
      return;
    }

    // V26.4: 如果是运行中状态，点击按钮就是取消
    if (taskState === 'running' && currentTaskId) {
      // 取消操作必须幂等：只调用一次取消接口
      try {
        await fetch('/api/review/cancel/' + currentTaskId, { method: 'POST' });
      } catch (e) {
        console.error('取消任务失败:', e);
      }

      // 进入取消中状态
      taskState = 'cancelling';
      showMessage('正在停止上一个任务...', 'info');
      els.generateOutlineBtn.textContent = '正在停止...';
      els.generateOutlineBtn.classList.remove('cancel-mode');
      els.generateOutlineBtn.disabled = true;

      // 继续轮询旧任务，等它真正退出
      // （不停止轮询，继续轮询直到旧任务状态变成 cancelled / failed / completed）
      return;
    }

    // V26.4: 如果是空闲状态，启动新任务
    currentTopic = topic;
    currentReviewType = els.reviewTypeSelect.value;
    const maxPapers = parseInt(els.maxPapersInput.value) || 20;

    showMessage('正在生成大纲...（约需 30-60 秒）', 'info');
    els.generateOutlineBtn.textContent = '取消';  // 按钮变成"取消"
    els.generateOutlineBtn.classList.add('cancel-mode');
    els.generateOutlineBtn.disabled = false;
    taskState = 'running';

    try {
      // V26.3: 第一步：发送请求，拿到 task_id
      const resp = await fetch(
        '/api/review/outline?topic=' + encodeURIComponent(topic) +
        '&max_papers=' + maxPapers + '&review_type=' + currentReviewType + '&language=en',
        { method: 'POST' }
      );
      if (!resp.ok) {
        const err = await resp.json();
        throw new Error(err.error || '生成大纲失败');
      }
      const data = await resp.json();
      currentTaskId = data.task_id;

      // V26.3: 第二步：轮询任务状态
      await pollTaskStatus(currentTaskId);
    } catch (e) {
      showMessage('生成大纲失败：' + e.message, 'error');
      // 清理状态
      if (taskPollTimer) {
        clearInterval(taskPollTimer);
        taskPollTimer = null;
      }
      currentTaskId = null;
      taskState = 'idle';
      els.generateOutlineBtn.textContent = '生成大纲';
      els.generateOutlineBtn.classList.remove('cancel-mode');
      els.generateOutlineBtn.disabled = false;
    }
  }

  // V26.3: 轮询任务状态
  function pollTaskStatus(taskId) {
    return new Promise((resolve, reject) => {
      let pollCount = 0;  // V26.3: 记录轮询次数
      const maxPollCount = 1800;  // V31.19: 最多轮询 1800 次（1800 秒 = 30 分钟）

      taskPollTimer = setInterval(async () => {
        pollCount++;
        // V26.3: 超时检查
        if (pollCount > maxPollCount) {
          clearInterval(taskPollTimer);
          taskPollTimer = null;
          currentTaskId = null;
          showMessage('生成大纲超时，请稍后重试', 'error');
          els.generateOutlineBtn.textContent = '生成大纲';
          els.generateOutlineBtn.classList.remove('cancel-mode');
          reject(new Error('生成超时'));
          return;
        }

        try {
          const resp = await fetch('/api/review/task/' + taskId);
          if (!resp.ok) {
            throw new Error('查询任务状态失败');
          }
          const task = await resp.json();

          if (task.status === 'completed') {
            // 任务完成
            clearInterval(taskPollTimer);
            taskPollTimer = null;
            currentTaskId = null;
            taskState = 'idle';

            const result = task.result;
            papers = result.papers || [];
            outlineCore.setData(result.outline || { sections: [] });
            refreshPaperList();
            showMessage('大纲生成成功！可以编辑标题/主题、增删章节段落、分配论文。', 'success');

            // 显示"确定大纲，自动发配"按钮
            if (els.assignPapersBtn) els.assignPapersBtn.style.display = '';

            els.generateOutlineBtn.textContent = '生成大纲';
            els.generateOutlineBtn.classList.remove('cancel-mode');
            els.generateOutlineBtn.disabled = false;
            resolve(result);
          } else if (task.status === 'failed') {
            // 任务失败
            clearInterval(taskPollTimer);
            taskPollTimer = null;
            currentTaskId = null;
            taskState = 'idle';

            // V26.4: 如果是取消中状态，显示"已停止"，而不是"失败"
            if (taskState === 'cancelling') {
              showMessage('已停止上一个任务', 'info');
            } else {
              showMessage('生成大纲失败：' + (task.error || '未知错误'), 'error');
            }

            els.generateOutlineBtn.textContent = '生成大纲';
            els.generateOutlineBtn.classList.remove('cancel-mode');
            els.generateOutlineBtn.disabled = false;
            reject(new Error(task.error || '任务失败'));
          } else if (task.status === 'cancelled') {
            // 任务被取消
            clearInterval(taskPollTimer);
            taskPollTimer = null;
            currentTaskId = null;

            // V26.4: 根据当前状态显示不同的提示
            if (taskState === 'cancelling') {
              showMessage('已停止上一个任务', 'info');
            } else {
              showMessage('已取消生成大纲', 'info');
            }

            taskState = 'idle';
            els.generateOutlineBtn.textContent = '生成大纲';
            els.generateOutlineBtn.classList.remove('cancel-mode');
            els.generateOutlineBtn.disabled = false;
            resolve(null);
          } else if (task.status === 'running') {
            // V26.5: 显示当前进度
            if (task.progress) {
              showMessage(task.progress + '...', 'info');
            }
          }
          // 如果是 running，继续轮询
        } catch (e) {
          console.error('轮询任务状态失败:', e);
        }
      }, 1000);  // 每隔 1 秒查询一次
    });
  }

  // ── V26.1: 自动发配论文到章节 ──
  async function handleAssignPapers() {
    const data = outlineCore ? outlineCore.getData() : null;
    if (!data || !data.sections || data.sections.length === 0) {
      showMessage('请先生成或加载大纲', 'error');
      return;
    }
    if (!papers || papers.length === 0) {
      showMessage('没有可分配的论文', 'error');
      return;
    }

    showMessage('正在自动发配论文到章节...', 'info');
    if (els.assignPapersBtn) els.assignPapersBtn.disabled = true;

    try {
      const resp = await fetch('/api/review/assign_papers', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          outline: data,
          papers: papers,
        }),
      });
      if (!resp.ok) {
        const err = await resp.json();
        throw new Error(err.error || '自动发配失败');
      }
      const result = await resp.json();
      outlineCore.setData(result.outline);
      showMessage('自动发配完成！请检查发配结果，不对的可以删掉，然后按"最终确定"。', 'success');

      // V26.1: 显示"最终确定"按钮
      if (els.confirmAssignBtn) els.confirmAssignBtn.style.display = '';
    } catch (e) {
      showMessage('自动发配失败：' + e.message, 'error');
    } finally {
      if (els.assignPapersBtn) els.assignPapersBtn.disabled = false;
    }
  }

  // ── V31.75: 按大纲搜索并分配论文 ──
  async function handleSearchAndAssign() {
    const data = outlineCore ? outlineCore.getData() : null;
    if (!data || !data.sections || data.sections.length === 0) {
      showMessage('请先生成或加载大纲', 'error');
      return;
    }

    const topic = els.topicInput ? els.topicInput.value : '';
    if (!topic.trim()) {
      showMessage('请输入综述主题', 'error');
      return;
    }

    const maxPapers = els.maxPapersInput ? parseInt(els.maxPapersInput.value) || 100 : 100;

    showMessage('正在按大纲内容搜索文献并分配...（可能需要几分钟）', 'info');
    if (els.searchAndAssignBtn) els.searchAndAssignBtn.disabled = true;

    try {
      const resp = await fetch('/api/review/search_and_assign', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          outline: data,
          topic: topic,
          max_papers: maxPapers,
        }),
      });
      if (!resp.ok) {
        const err = await resp.json();
        throw new Error(err.error || '搜索并分配失败');
      }
      const result = await resp.json();
      outlineCore.setData(result.outline);
      // 更新论文列表
      if (result.papers && result.papers.length > 0) {
        papers = result.papers;
        refreshPaperList();
      }
      showMessage('搜索并分配完成！共找到 ' + (result.papers ? result.papers.length : 0) + ' 篇论文，请检查分配结果。', 'success');

      // 显示"最终确定"按钮
      if (els.confirmAssignBtn) els.confirmAssignBtn.style.display = '';
    } catch (e) {
      showMessage('搜索并分配失败：' + e.message, 'error');
    } finally {
      if (els.searchAndAssignBtn) els.searchAndAssignBtn.disabled = false;
    }
  }

  // ── V26.1: 最终确定文献分配 ──
  function handleConfirmAssign() {
    showMessage('文献分配已确定！现在可以点击"生成综述"开始写作了。', 'success');
    // V26.1: 隐藏这两个按钮
    if (els.assignPapersBtn) els.assignPapersBtn.style.display = 'none';
    if (els.confirmAssignBtn) els.confirmAssignBtn.style.display = 'none';
    // V30.3: 启用"生成综述"按钮
    if (els.generateReviewBtn) els.generateReviewBtn.disabled = false;
  }

  // ── 自动解析未解析文献（V25.14: 生成综述前自动解析）──
  async function autoParseUnparsedPapers() {
    const unparsed = (localPapers || []).filter(function(p) { return !p.parsed; });
    if (unparsed.length === 0) return { total: 0, success: 0, failed: 0 };

    showMessage('检测到 ' + unparsed.length + ' 篇未解析文献，正在自动解析（每篇约 30-60 秒）...', 'info');

    let success = 0;
    let failed = 0;

    for (let i = 0; i < unparsed.length; i++) {
      const paper = unparsed[i];
      const idx = i + 1;
      showMessage('正在解析（' + idx + '/' + unparsed.length + '）：' + (paper.title || paper.filename) + '...', 'info');

      try {
        const resp = await fetch('/api/papers/parse', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ filename: paper.filename }),
        });
        const data = await resp.json();
        if (data.error) {
          failed++;
          console.warn('解析失败:', paper.filename, data.error);
        } else {
          success++;
        }
      } catch (e) {
        failed++;
        console.warn('解析异常:', paper.filename, e.message);
      }
    }

    // 解析完成后刷新列表
    localPapers = [];
    await loadLocalPapers();

    return { total: unparsed.length, success: success, failed: failed };
  }

  async function handleGenerateReview() {
    const data = outlineCore ? outlineCore.getData() : null;
    if (!data || !data.sections || data.sections.length === 0) {
      showMessage('请先生成或加载大纲', 'error');
      return;
    }

    const topic = els.topicInput.value.trim() || currentTopic;
    if (!topic) {
      showMessage('请输入综述主题', 'error');
      return;
    }

    // V25.14: 生成综述前自动解析未解析文献
    const parseResult = await autoParseUnparsedPapers();
    if (parseResult.failed > 0) {
      showMessage('有 ' + parseResult.failed + ' 篇文献解析失败，将继续生成综述（可能缺少这些文献的内容）', 'warning');
    } else if (parseResult.total > 0) {
      showMessage('自动解析完成：' + parseResult.success + ' 篇全部成功，开始生成综述...', 'success');
    }

    // V31.83: 构造 customOutline，包含 evidence_cards 和 assigned_evidence_ids
    const customOutline = {
      sections: data.sections.map(function(sec) {
        return {
          title: sec.title,
          description: sec.description || '',
          assigned_paper_ids: sec.assigned_paper_ids || [],
          assigned_evidence_ids: sec.assigned_evidence_ids || [],  // V31.83: 章节级证据ID
          paragraphs: (sec.paragraphs || []).map(function(para) {
            return {
              topic: para.topic,
              description: para.description || '',
              assigned_paper_ids: para.assigned_paper_ids || [],
              assigned_evidence_ids: para.assigned_evidence_ids || [],  // V31.83: 段落级证据ID
            };
          }),
        };
      }),
    };

    // V31.83: 如果 data 里有 evidence_cards（按大纲搜索并分配时保存的），就一起传过去
    if (data.evidence_cards && Array.isArray(data.evidence_cards) && data.evidence_cards.length > 0) {
      customOutline.evidence_cards = data.evidence_cards;
      console.log('V31.83: 传递 evidence_cards，共 ' + data.evidence_cards.length + ' 条');
    }

    showMessage('正在生成综述...（约需 1-3 分钟，请耐心等待）', 'info');
    els.generateReviewBtn.disabled = true;

    try {
      const resp = await fetch('/api/review/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          topic: topic,
          max_papers: parseInt(els.maxPapersInput.value) || 20,
          review_type: currentReviewType,
          citation_style: 'apa',
          language: 'en',
          custom_outline: customOutline,
        }),
      });

      if (!resp.ok) {
        const err = await resp.json();
        throw new Error(err.error || '生成综述失败');
      }

      const result = await resp.json();
      if (result.review_id) {
        window.location.href = '/review.html?review_id=' + result.review_id;
      } else {
        showMessage('综述生成完成，但未返回 review_id', 'error');
      }
    } catch (e) {
      showMessage('生成综述失败：' + e.message, 'error');
    } finally {
      els.generateReviewBtn.disabled = false;
    }
  }

  async function handleSaveOutline() {
    const data = outlineCore ? outlineCore.getData() : null;
    if (!data || !data.sections || data.sections.length === 0) {
      showMessage('没有可保存的大纲', 'error');
      return;
    }

    const name = prompt('请输入大纲名称：', currentTopic || 'my_outline');
    if (!name || !name.trim()) return;

    try {
      const resp = await fetch('/api/review/outline/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: name.trim(),
          topic: currentTopic,
          review_type: currentReviewType,
          outline: data,
          paper_count: papers.length,
        }),
      });

      if (!resp.ok) {
        const err = await resp.json();
        throw new Error(err.error || '保存失败');
      }

      showMessage('大纲已保存为「' + name.trim() + '」', 'success');
      loadSavedOutlines();
    } catch (e) {
      showMessage('保存失败：' + e.message, 'error');
    }
  }

  async function loadSavedOutlines() {
    try {
      const resp = await fetch('/api/review/outline/saved');
      if (!resp.ok) return;
      const data = await resp.json();
      savedOutlines = data.outlines || [];

      els.loadOutlineSelect.innerHTML = '<option value="">-- 选择已保存的大纲 --</option>';
      savedOutlines.forEach(function(o) {
        const option = document.createElement('option');
        option.value = o.name;
        option.textContent = (o.display_name || o.name) + ' (' + o.section_count + '章 ' + o.paragraph_count + '段) - ' + (o.updated_at || '');
        els.loadOutlineSelect.appendChild(option);
      });
    } catch (e) {
      // 静默失败
    }
  }

  async function handleLoadOutline() {
    const name = els.loadOutlineSelect.value;
    if (!name) {
      showMessage('请选择要加载的大纲', 'error');
      return;
    }

    try {
      const resp = await fetch('/api/review/outline/saved/' + encodeURIComponent(name));
      if (!resp.ok) {
        const err = await resp.json();
        throw new Error(err.error || '加载失败');
      }
      const data = await resp.json();
      outlineCore.setData(data.outline || { sections: [] });
      currentTopic = data.topic || '';
      currentReviewType = data.review_type || 'narrative';

      if (currentTopic) els.topicInput.value = currentTopic;
      els.reviewTypeSelect.value = currentReviewType;

      papers = [];
      refreshPaperList();
      showMessage('大纲「' + (data.display_name || name) + '」已加载。注意：论文列表需要重新生成大纲才能获取。', 'success');

      // V26.1: 加载已保存的大纲时，隐藏这两个按钮
      if (els.assignPapersBtn) els.assignPapersBtn.style.display = 'none';
      if (els.confirmAssignBtn) els.confirmAssignBtn.style.display = 'none';
    } catch (e) {
      showMessage('加载失败：' + e.message, 'error');
    }
  }

  // ── 工具函数 ──
  function showMessage(text, type) {
    if (!els.editorMessage) return;
    els.editorMessage.textContent = text;
    els.editorMessage.className = 'editor-message ' + (type || 'info');
    els.editorMessage.style.display = 'block';
  }

  function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

})();
