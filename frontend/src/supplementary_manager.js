/* V25.17 - Sci-Pal 补充材料管理模块（独立）
 *
 * 职责：
 * 1. 显示某篇论文的补充材料列表
 * 2. 上传新的补充材料文件
 * 3. 删除补充材料
 * 4. 打开/下载补充材料
 *
 * 不负责：论文列表渲染、PDF 渲染
 */

(function() {
  'use strict';

  /**
   * 创建补充材料管理器
   * @param {Object} config
   * @param {HTMLElement} config.container - 面板容器（模态框）
   * @param {Function} config.escapeHtml - HTML 转义函数
   * @param {Function} config.onFileAdded - 文件添加成功回调
   */
  function createSupplementaryManager(config) {
    let currentPaperId = null;
    let currentPaperTitle = null;

    // ── 打开面板 ──
    function open(paperId, paperTitle) {
      currentPaperId = paperId;
      currentPaperTitle = paperTitle;
      // container 是内层内容区，parentElement 才是外层模态框（控制显示/隐藏）
      if (config.container.parentElement) {
        config.container.parentElement.classList.add('open');
      }
      render();
    }

    // ── 关闭面板 ──
    function close() {
      if (config.container.parentElement) {
        config.container.parentElement.classList.remove('open');
      }
      currentPaperId = null;
      currentPaperTitle = null;
    }

    // ── 渲染补充材料列表 ──
    function render() {
      if (!currentPaperId) return;

      const titleHtml = config.escapeHtml(currentPaperTitle || currentPaperId);
      let html =
        '<div class="supp-header">' +
        '<div class="supp-title">📎 补充材料 — ' + titleHtml + '</div>' +
        '<button class="supp-close-btn" id="supp-close-btn">✕</button>' +
        '</div>' +
        '<div class="supp-upload-area">' +
        '<label class="supp-upload-label">' +
        '<input type="file" id="supp-file-input" multiple style="display:none">' +
        '<span class="supp-upload-icon">⬆</span>' +
        '<span>点击选择文件上传（支持 PDF / Excel / Word / PPT / 压缩包等）</span>' +
        '</label>' +
        '<div class="supp-upload-hint">文件将关联到当前论文，不解析内容，仅做文件管理</div>' +
        '</div>' +
        '<div class="supp-list" id="supp-list">' +
        '<div class="supp-loading">加载中...</div>' +
        '</div>';

      config.container.innerHTML = html;

      // 绑定关闭按钮
      document.getElementById('supp-close-btn').addEventListener('click', close);

      // 绑定文件上传
      const fileInput = document.getElementById('supp-file-input');
      fileInput.addEventListener('change', handleFileUpload);

      // 加载列表
      loadList();
    }

    // ── 加载补充材料列表 ──
    function loadList() {
      const listEl = document.getElementById('supp-list');
      if (!listEl) return;

      fetch('/api/papers/' + currentPaperId + '/supplementary')
        .then(function(r) { return r.json(); })
        .then(function(data) {
          const files = data.supplementary_files || [];
          if (files.length === 0) {
            listEl.innerHTML = '<div class="supp-empty">暂无补充材料，上传后将显示在这里</div>';
            return;
          }

          let html = '';
          files.forEach(function(f) {
            const sizeKb = (f.file_size / 1024).toFixed(1);
            const sizeStr = f.file_size > 1024 * 1024
              ? (f.file_size / (1024 * 1024)).toFixed(2) + ' MB'
              : sizeKb + ' KB';
            const icon = getFileIcon(f.file_type);

            html +=
              '<div class="supp-item" data-supp-id="' + config.escapeHtml(f.supp_id) + '">' +
              '<div class="supp-item-icon">' + icon + '</div>' +
              '<div class="supp-item-info">' +
              '<div class="supp-item-name">' + config.escapeHtml(f.filename) + '</div>' +
              '<div class="supp-item-meta">' +
              (f.file_type ? f.file_type.toUpperCase() + ' · ' : '') +
              sizeStr +
              (f.created_at ? ' · ' + f.created_at.substring(0, 10) : '') +
              '</div>' +
              (f.description ? '<div class="supp-item-desc">' + config.escapeHtml(f.description) + '</div>' : '') +
              '</div>' +
              '<div class="supp-item-actions">' +
              '<button class="supp-action-btn open" data-action="open" title="打开">📂</button>' +
              '<button class="supp-action-btn delete" data-action="delete" title="删除">🗑</button>' +
              '</div>' +
              '</div>';
          });
          listEl.innerHTML = html;

          // 绑定操作按钮
          listEl.querySelectorAll('.supp-item').forEach(function(itemEl) {
            const suppId = itemEl.dataset.suppId;
            itemEl.querySelector('[data-action="open"]').addEventListener('click', function() {
              openFile(suppId);
            });
            itemEl.querySelector('[data-action="delete"]').addEventListener('click', function() {
              deleteFile(suppId, itemEl);
            });
          });
        })
        .catch(function(err) {
          listEl.innerHTML = '<div class="supp-error">加载失败: ' + config.escapeHtml(err.message) + '</div>';
        });
    }

    // ── 处理文件上传 ──
    function handleFileUpload(event) {
      const files = event.target.files;
      if (!files || files.length === 0) return;

      const listEl = document.getElementById('supp-list');
      let uploaded = 0;
      let failed = 0;

      Array.from(files).forEach(function(file) {
        const formData = new FormData();
        formData.append('file', file);

        // 显示上传中状态
        let loading = null;
        if (listEl) {
          loading = document.createElement('div');
          loading.className = 'supp-uploading';
          loading.textContent = '上传中: ' + file.name + ' ...';
          listEl.prepend(loading);
        }

        fetch('/api/papers/' + currentPaperId + '/supplementary', {
          method: 'POST',
          body: formData
        })
          .then(function(r) { return r.json(); })
          .then(function(data) {
            if (data.success) {
              uploaded++;
              console.log('✅ 补充材料上传成功:', data.filename);
            } else {
              failed++;
              console.error('❌ 补充材料上传失败:', data.error);
            }
          })
          .catch(function(err) {
            failed++;
            console.error('❌ 上传错误:', err);
          })
          .finally(function() {
            // 移除上传中状态
            if (loading && loading.parentNode) {
              loading.parentNode.removeChild(loading);
            }
            // 全部上传完成后刷新列表
            if (uploaded + failed === files.length) {
              loadList();
              if (config.onFileAdded) {
                config.onFileAdded(currentPaperId, uploaded);
              }
            }
          });
      });

      // 清空 input，允许重复选择同一文件
      event.target.value = '';
    }

    // ── 打开文件 ──
    function openFile(suppId) {
      const url = '/api/papers/' + currentPaperId + '/supplementary/' + suppId + '/download';
      window.open(url, '_blank');
    }

    // ── 删除文件 ──
    function deleteFile(suppId, itemEl) {
      if (!confirm('确定删除这个补充材料吗？\n（仅删除记录，文件保留在 documents 目录）')) {
        return;
      }

      fetch('/api/papers/' + currentPaperId + '/supplementary/' + suppId + '?delete_file=0', {
        method: 'DELETE'
      })
        .then(function(r) { return r.json(); })
        .then(function(data) {
          if (data.success) {
            if (itemEl && itemEl.parentNode) {
              itemEl.parentNode.removeChild(itemEl);
            }
            console.log('🗑 补充材料已删除:', suppId);
            if (config.onFileAdded) {
              config.onFileAdded(currentPaperId, -1);
            }
          } else {
            alert('删除失败: ' + (data.error || '未知错误'));
          }
        })
        .catch(function(err) {
          alert('删除错误: ' + err.message);
        });
    }

    // ── 获取文件图标 ──
    function getFileIcon(fileType) {
      const type = (fileType || '').toLowerCase();
      if (type === 'pdf') return '📕';
      if (['doc', 'docx'].indexOf(type) >= 0) return '📘';
      if (['xls', 'xlsx', 'csv'].indexOf(type) >= 0) return '📗';
      if (['ppt', 'pptx'].indexOf(type) >= 0) return '📙';
      if (['zip', 'rar', '7z', 'tar', 'gz'].indexOf(type) >= 0) return '📦';
      if (['png', 'jpg', 'jpeg', 'gif', 'svg', 'tiff'].indexOf(type) >= 0) return '🖼';
      if (['txt', 'md', 'rtf'].indexOf(type) >= 0) return '📝';
      return '📎';
    }

    return {
      open: open,
      close: close,
      render: render,
      loadList: loadList,
    };
  }

  window.SciPal = window.SciPal || {};
  window.SciPal.createSupplementaryManager = createSupplementaryManager;

})();
