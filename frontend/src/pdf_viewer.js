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
    function loadPaper(paperId, paperTitle, source) {
      state.paperId = paperId;
      state.paperTitle = paperTitle || paperId;
      source = source || 'full_text';

      if (config.titleEl) {
        config.titleEl.textContent = state.paperTitle;
      }

      if (config.container) {
        config.container.innerHTML = '';

        if (source === 'abstract') {
          // V26.0: 显示摘要
          loadAbstract(paperId);
        } else if (source === 'xml') {
          // V26.0: 显示 XML 全文
          loadXmlFullText(paperId);
        } else {
          // 原来的 PDF 加载方式
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
        }
      } else if (config.onPaperLoaded) {
        config.onPaperLoaded();
      }
    }

    // ── V26.0: 加载摘要 ──
    function loadAbstract(paperId) {
      fetch('/api/abstracts/' + encodeURIComponent(paperId))
        .then(function(response) { return response.json(); })
        .then(function(data) {
          if (config.container) {
            let html = '<div class="abstract-viewer" style="background:#fff; padding:24px; overflow-y:auto; height:100%; box-sizing:border-box;">';
            html += '<h2 style="margin-top:0; color:#1a1a1a;">' + (data.title || paperId) + '</h2>';
            html += '<p style="color:#666; margin:8px 0 16px 0;">' + (data.journal || '') + ' · ' + (data.year || '') + '</p>';
            html += '<div style="color:#333; line-height:1.8;">';
            html += '<h3 style="color:#1a1a1a;">摘要</h3>';
            html += '<p style="color:#333; line-height:1.8;">' + (data.abstract || '没有找到摘要内容。') + '</p>';
            html += '</div></div>';
            config.container.innerHTML = html;
          }
          if (config.onPaperLoaded) config.onPaperLoaded();
        })
        .catch(function(error) {
          console.error('加载摘要失败:', error);
          if (config.container) {
            config.container.innerHTML = '<div style="background:#fff; padding:24px; color:#c00;">加载摘要失败，请稍后重试。</div>';
          }
          if (config.onPaperLoaded) config.onPaperLoaded();
        });
    }

    // ── V26.0: 加载 XML 全文 ──
    function loadXmlFullText(paperId) {
      fetch('/api/papers/' + encodeURIComponent(paperId) + '/fulltext')
        .then(function(response) { return response.json(); })
        .then(function(data) {
          if (config.container) {
            let html = '<div class="fulltext-viewer">';
            html += '<h2>' + (data.title || paperId) + '</h2>';
            html += '<div class="fulltext-content">';
            // 分段显示
            if (data.paragraphs && data.paragraphs.length > 0) {
              data.paragraphs.forEach(function(p) {
                html += '<p class="fulltext-paragraph">' + p.text + '</p>';
              });
            } else {
              html += '<p>没有找到全文内容。</p>';
            }
            html += '</div></div>';
            config.container.innerHTML = html;
          }
          if (config.onPaperLoaded) config.onPaperLoaded();
        })
        .catch(function(error) {
          console.error('加载全文失败:', error);
          if (config.container) {
            config.container.innerHTML = '<div class="error">加载全文失败，请稍后重试。</div>';
          }
          if (config.onPaperLoaded) config.onPaperLoaded();
        });
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
      loadAbstract: loadAbstract,  // V26.4: 暴露加载摘要的方法
      loadXmlFullText: loadXmlFullText,  // V26.4: 暴露加载 XML 全文的方法
      getState: getState,
      getDoc: getDoc,
    };
  }

  window.SciPal = window.SciPal || {};
  window.SciPal.createPdfViewer = createPdfViewer;

})();
