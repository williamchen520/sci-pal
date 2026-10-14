/* V25.13 - Sci-Pal PDF 标注模块（独立）— 适配连续滚动多页模式
 *
 * 职责：
 * 1. 监听文本选择，弹出标注工具栏（高亮/下划线/批注）
 * 2. 发送标注到后端写入 PDF 文件
 * 3. 加载已有标注，渲染可点击覆盖层
 * 4. 点击覆盖层删除标注
 *
 * 依赖：SciPal.createPdfViewer 实例
 * 不负责：PDF 渲染、翻页、缩放
 *
 * V25.13 变更：适配连续滚动多页模式
 * - 标注页码从 DOM 元素（.pdf-page-wrapper data-page-num）获取，而非 state.pageNum
 * - loadOverlays 接受 pageNum 参数，每页独立加载覆盖层
 * - 标注增删后重新渲染当前页（触发 onPageRendered → 重新加载覆盖层）
 */

(function() {
  'use strict';

  /**
   * 创建 PDF 标注管理器
   * @param {Object} config
   * @param {Object} config.pdfViewer - SciPal PdfViewer 实例
   * @param {Function} config.showMessage - 消息提示回调 (text, type)
   * @param {Function} config.onAnnotationChanged - 标注变更回调（增删后）
   */
  function createPdfAnnotator(config) {
    const toolbar = { el: null };
    const selection = { data: null };

    // ── 从文本层元素获取所在页码 ──
    function getPageNumFromEl(el) {
      const wrapper = el.closest('.pdf-page-wrapper');
      if (wrapper && wrapper.dataset.pageNum) {
        return parseInt(wrapper.dataset.pageNum);
      }
      // 回退到 state
      return config.pdfViewer.getState().pageNum;
    }

    // ── 绑定文本选择事件（在文本层渲染后调用，每页独立绑定） ──
    function bindTextSelection(wrapper) {
      const textLayer = wrapper.querySelector('.oe-text-layer');
      if (!textLayer) return;

      textLayer.addEventListener('mouseup', function() {
        setTimeout(function() {
          const sel = window.getSelection();
          if (sel && sel.toString().trim() && sel.rangeCount > 0) {
            const range = sel.getRangeAt(0);
            const rect = range.getBoundingClientRect();
            if (rect.width > 2 && rect.height > 2) {
              showToolbar(rect, textLayer, sel.toString().trim());
            }
          }
        }, 10);
      });

      textLayer.addEventListener('mousedown', function(e) {
        if (!e.target.closest('.oe-annot-toolbar')) {
          hideToolbar();
        }
      });
    }

    // ── 显示标注工具栏 ──
    function showToolbar(rect, textLayer, selectedText) {
      hideToolbar();

      const state = config.pdfViewer.getState();
      const doc = config.pdfViewer.getDoc();
      if (!doc) return;

      // V25.13: 从 DOM 获取页码，而非 state（连续滚动模式下 state 可能滞后）
      const pageNum = getPageNumFromEl(textLayer);

      // 计算选区在 textLayer 内的相对坐标 → PDF 标准坐标（左下原点）
      const layerRect = textLayer.getBoundingClientRect();
      const relLeft = rect.left - layerRect.left;
      const relTop = rect.top - layerRect.top;
      const relRight = rect.right - layerRect.left;
      const relBottom = rect.bottom - layerRect.top;
      const scale = state.scale;

      const viewportHeight = textLayer.offsetHeight;

      const pdfRect = [
        relLeft / scale,
        (viewportHeight - relBottom) / scale,
        relRight / scale,
        (viewportHeight - relTop) / scale,
      ];

      selection.data = {
        page: pageNum,
        rect: pdfRect,
        text: selectedText,
      };

      // 创建工具栏
      toolbar.el = document.createElement('div');
      toolbar.el.className = 'oe-annot-toolbar';
      toolbar.el.innerHTML =
        '<button class="hl" title="高亮标记">🖍 高亮</button>' +
        '<button class="ul" title="下划线">📝 下划线</button>' +
        '<button class="note" title="添加批注">💬 批注</button>';

      let left = rect.left + rect.width / 2 - 100;
      let top = rect.top - 40;
      if (top < 10) top = rect.bottom + 8;
      if (left < 10) left = 10;

      toolbar.el.style.left = left + 'px';
      toolbar.el.style.top = top + 'px';

      toolbar.el.querySelector('.hl').addEventListener('click', function(e) {
        e.stopPropagation();
        addAnnotation('highlight', [1.0, 0.9, 0.3]);
      });
      toolbar.el.querySelector('.ul').addEventListener('click', function(e) {
        e.stopPropagation();
        addAnnotation('underline', [0.0, 0.4, 1.0]);
      });
      toolbar.el.querySelector('.note').addEventListener('click', function(e) {
        e.stopPropagation();
        const noteText = prompt('请输入批注内容：', selectedText);
        if (noteText !== null) {
          addAnnotation('text', [1.0, 0.9, 0.3], noteText);
        }
      });

      document.body.appendChild(toolbar.el);
    }

    function hideToolbar() {
      if (toolbar.el) {
        toolbar.el.remove();
        toolbar.el = null;
      }
      selection.data = null;
    }

    // ── 添加标注（发送到后端） ──
    function addAnnotation(annotType, color, text) {
      if (!selection.data || !config.pdfViewer.getState().paperId) {
        hideToolbar();
        return;
      }

      const data = selection.data;
      const paperId = config.pdfViewer.getState().paperId;
      hideToolbar();
      window.getSelection().removeAllRanges();

      config.showMessage('正在添加标注...', 'info');

      fetch('/api/papers/' + encodeURIComponent(paperId) + '/annotate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action: 'add',
          page: data.page,
          type: annotType,
          rect: data.rect,
          color: color,
          text: text || data.text,
        }),
      }).then(function(resp) { return resp.json(); })
        .then(function(result) {
          if (result.success) {
            config.showMessage('标注已添加并保存到 PDF', 'success');
            // V25.13: 重新渲染当前页（触发 onPageRendered → 重新加载覆盖层）
            const currentPage = config.pdfViewer.getState().pageNum;
            config.pdfViewer.renderPage(currentPage);
            if (config.onAnnotationChanged) config.onAnnotationChanged();
          } else {
            config.showMessage('标注失败：' + (result.error || '未知错误'), 'error');
          }
        }).catch(function(err) {
          config.showMessage('标注失败：' + err.message, 'error');
        });
    }

    // ── 加载已有标注覆盖层（页面渲染完成后调用，每页独立） ──
    function loadOverlays(page, viewport, wrapper, pageNum) {
      const paperId = config.pdfViewer.getState().paperId;
      // V25.13: 使用传入的 pageNum，而非 state.pageNum（连续滚动模式下每页独立加载）
      const pNum = pageNum || config.pdfViewer.getState().pageNum;
      if (!paperId) return;

      fetch('/api/papers/' + encodeURIComponent(paperId) + '/annotations?page=' + pNum)
        .then(function(resp) {
          if (!resp.ok) return null;
          return resp.json();
        })
        .then(function(data) {
          if (!data || !data.annotations) return;
          renderOverlays(data.annotations, viewport, wrapper, pNum);
        })
        .catch(function() {});
    }

    // ── 渲染标注覆盖层（可点击删除） ──
    function renderOverlays(annotations, viewport, wrapper, pageNum) {
      wrapper.querySelectorAll('.oe-annot-overlay').forEach(function(el) { el.remove(); });

      const scale = config.pdfViewer.getState().scale;

      annotations.forEach(function(annot) {
        // V25.13: 用传入的 pageNum 过滤，而非 state.pageNum
        if (annot.page !== pageNum) return;

        const overlay = document.createElement('div');
        overlay.className = 'oe-annot-overlay';
        overlay.title = '点击删除此标注' + (annot.content ? '：' + annot.content.substring(0, 30) : '');

        const x0 = annot.rect[0] * scale;
        const y0 = (viewport.height - annot.rect[3]) * scale;
        const x1 = annot.rect[2] * scale;
        const y1 = (viewport.height - annot.rect[1]) * scale;

        overlay.style.left = x0 + 'px';
        overlay.style.top = y0 + 'px';
        overlay.style.width = (x1 - x0) + 'px';
        overlay.style.height = (y1 - y0) + 'px';

        overlay.addEventListener('click', function(e) {
          e.stopPropagation();
          if (confirm('确定删除此标注吗？')) {
            deleteAnnotation(annot);
          }
        });

        wrapper.appendChild(overlay);
      });
    }

    // ── 删除标注 ──
    function deleteAnnotation(annot) {
      const paperId = config.pdfViewer.getState().paperId;
      if (!paperId) return;

      config.showMessage('正在删除标注...', 'info');

      const typeMap = { 8: 'highlight', 9: 'underline', 0: 'text' };

      fetch('/api/papers/' + encodeURIComponent(paperId) + '/annotate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action: 'delete',
          page: annot.page,
          type: typeMap[annot.type_id] || 'highlight',
          rect: annot.rect,
          text: annot.content || '',
        }),
      }).then(function(resp) { return resp.json(); })
        .then(function(result) {
          if (result.success) {
            config.showMessage('标注已删除', 'success');
            // V25.13: 重新渲染标注所在页
            config.pdfViewer.renderPage(annot.page);
            if (config.onAnnotationChanged) config.onAnnotationChanged();
          } else {
            config.showMessage('删除失败：' + (result.error || '未知错误'), 'error');
          }
        }).catch(function(err) {
          config.showMessage('删除失败：' + err.message, 'error');
        });
    }

    // ── 暴露 API ──
    return {
      bindTextSelection: bindTextSelection,
      loadOverlays: loadOverlays,
      hideToolbar: hideToolbar,
    };
  }

  window.SciPal = window.SciPal || {};
  window.SciPal.createPdfAnnotator = createPdfAnnotator;

})();
