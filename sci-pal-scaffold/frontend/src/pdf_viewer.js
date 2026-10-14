/* V25.14 - Sci-Pal PDF 阅读器（浏览器原生 PDFium 矢量渲染版）
 *
 * 职责：
 * 1. 通过 iframe 加载 PDF，使用浏览器自带的 PDF 查看器（Edge/Chrome 的 PDFium，Firefox 的 PDF.js）
 * 2. 矢量渲染，放大不模糊
 * 3. 翻页/缩放/下载等操作由浏览器自带工具栏完成
 *
 * 不负责：
 * - PDF 标注（iframe 内部无法叠加覆盖层，标注功能已移除）
 * - 文本选择监听（iframe 跨域无法监听内部事件）
 *
 * 依赖：无（不需要 PDF.js）
 * 接口保持兼容：loadPaper / getState / getDoc
 */

(function() {
  'use strict';

  /**
   * 创建 PDF 阅读器（iframe 版）
   * @param {Object} config
   * @param {HTMLElement} config.container - PDF 容器元素
   * @param {HTMLElement} config.titleEl - 标题显示元素（可选）
   * @param {Function} config.onPaperLoaded - 论文加载完成回调（可选）
   * @param {Function} config.showMessage - 消息提示回调（可选，兼容旧接口）
   */
  function createPdfViewer(config) {
    const state = {
      paperId: null,
      paperTitle: '',
      iframe: null,
    };

    // ── 加载论文 ──
    function loadPaper(paperId, paperTitle) {
      state.paperId = paperId;
      state.paperTitle = paperTitle || paperId;

      if (config.titleEl) {
        config.titleEl.textContent = state.paperTitle;
      }

      if (config.container) {
        config.container.innerHTML = '';

        state.iframe = document.createElement('iframe');
        state.iframe.className = 'pdf-iframe';
        state.iframe.src = '/api/papers/' + encodeURIComponent(paperId) + '/pdf';
        state.iframe.setAttribute('type', 'application/pdf');
        state.iframe.setAttribute('frameborder', '0');
        state.iframe.setAttribute('allowfullscreen', '');

        // iframe 加载完成后触发回调
        state.iframe.addEventListener('load', function() {
          if (config.onPaperLoaded) config.onPaperLoaded();
        });

        config.container.appendChild(state.iframe);
      } else if (config.onPaperLoaded) {
        config.onPaperLoaded();
      }
    }

    // ── 获取状态（兼容旧接口） ──
    function getState() {
      return state;
    }

    // ── 获取文档对象（兼容旧接口，返回 iframe） ──
    function getDoc() {
      return state.iframe;
    }

    // ── 暴露 API ──
    return {
      loadPaper: loadPaper,
      load: loadPaper,  // 兼容旧接口 outline_editor.js 调用 pdfViewer.load()
      getState: getState,
      getDoc: getDoc,
    };
  }

  window.SciPal = window.SciPal || {};
  window.SciPal.createPdfViewer = createPdfViewer;

})();
