/* V25.17 - Sci-Pal 文献导入模块（独立）
 *
 * 职责：
 * 1. 显示导入对话框（正文 PDF 必选 + 补充材料可选多选）
 * 2. 上传文件到 /api/papers/import
 * 3. 上传后自动触发解析 /api/papers/parse
 * 4. 解析完成后自动关联补充材料
 * 5. 回调通知外部（刷新列表、打开 PDF）
 *
 * 不负责：解析逻辑、补充材料管理面板、PDF 渲染
 */

(function() {
  'use strict';

  /**
   * 创建文献导入器
   * @param {Object} config
   * @param {HTMLElement} config.container - 模态框容器
   * @param {Function} config.escapeHtml - HTML 转义函数
   * @param {Function} config.onImportComplete - 导入完成回调 (paperId, paperTitle, filename)
   * @param {Function} config.onRefreshList - 刷新文献列表回调
   */
  function createPaperImporter(config) {
    let selectedPaperFile = null;
    let selectedSuppFiles = [];

    // ── 打开对话框 ──
    function open() {
      selectedPaperFile = null;
      selectedSuppFiles = [];
      // container 是内层内容区，parentElement 才是外层模态框（控制显示/隐藏）
      if (config.container.parentElement) {
        config.container.parentElement.classList.add('open');
      }
      render();
    }

    // ── 关闭对话框 ──
    function close() {
      if (config.container.parentElement) {
        config.container.parentElement.classList.remove('open');
      }
      selectedPaperFile = null;
      selectedSuppFiles = [];
    }

    // ── 渲染对话框 ──
    function render() {
      let html =
        '<div class="import-header">' +
        '<div class="import-title">📥 导入文献</div>' +
        '<button class="import-close-btn" id="import-close-btn">✕</button>' +
        '</div>' +
        '<div class="import-body">' +

        // 正文 PDF
        '<div class="import-section">' +
        '<div class="import-section-title">正文 PDF <span class="import-required">*</span></div>' +
        '<label class="import-file-label" id="import-paper-label">' +
        '<input type="file" id="import-paper-input" accept=".pdf" style="display:none">' +
        '<span class="import-file-icon">📕</span>' +
        '<span class="import-file-text" id="import-paper-text">点击选择正文 PDF 文件</span>' +
        '</label>' +
        '</div>' +

        // 补充材料
        '<div class="import-section">' +
        '<div class="import-section-title">补充材料 <span class="import-optional">（可选，可多选）</span></div>' +
        '<label class="import-file-label" id="import-supp-label">' +
        '<input type="file" id="import-supp-input" multiple style="display:none">' +
        '<span class="import-file-icon">📎</span>' +
        '<span class="import-file-text" id="import-supp-text">点击选择补充材料（PDF / Excel / Word / 压缩包等）</span>' +
        '</label>' +
        '<div class="import-supp-list" id="import-supp-list"></div>' +
        '</div>' +

        // 提示
        '<div class="import-hint">' +
        '💡 导入后系统将自动解析正文，补充材料自动关联到同一篇文章。' +
        '初看文章可以只选正文，不需要补充材料。' +
        '</div>' +

        '</div>' +
        '<div class="import-footer">' +
        '<button class="import-btn cancel" id="import-cancel-btn">取消</button>' +
        '<button class="import-btn confirm" id="import-confirm-btn" disabled>开始导入</button>' +
        '</div>';

      config.container.innerHTML = html;

      // 绑定关闭
      document.getElementById('import-close-btn').addEventListener('click', close);
      document.getElementById('import-cancel-btn').addEventListener('click', close);

      // 绑定正文选择
      document.getElementById('import-paper-input').addEventListener('change', function(e) {
        if (e.target.files && e.target.files.length > 0) {
          selectedPaperFile = e.target.files[0];
          document.getElementById('import-paper-text').textContent =
            selectedPaperFile.name + ' (' + formatSize(selectedPaperFile.size) + ')';
          document.getElementById('import-paper-label').classList.add('selected');
        }
        updateConfirmBtn();
      });

      // 绑定补充材料选择
      document.getElementById('import-supp-input').addEventListener('change', function(e) {
        if (e.target.files && e.target.files.length > 0) {
          selectedSuppFiles = Array.from(e.target.files);
          renderSuppList();
        }
        updateConfirmBtn();
      });

      // 绑定确认
      document.getElementById('import-confirm-btn').addEventListener('click', handleImport);

      updateConfirmBtn();
    }

    // ── 渲染已选补充材料列表 ──
    function renderSuppList() {
      const listEl = document.getElementById('import-supp-list');
      if (!listEl) return;

      if (selectedSuppFiles.length === 0) {
        listEl.innerHTML = '';
        return;
      }

      let html = '';
      selectedSuppFiles.forEach(function(file, idx) {
        html +=
          '<div class="import-supp-item">' +
          '<span class="import-supp-icon">' + getFileIcon(file.name) + '</span>' +
          '<span class="import-supp-name">' + config.escapeHtml(file.name) + '</span>' +
          '<span class="import-supp-size">' + formatSize(file.size) + '</span>' +
          '<button class="import-supp-remove" data-idx="' + idx + '" title="移除">✕</button>' +
          '</div>';
      });
      listEl.innerHTML = html;

      // 绑定移除按钮
      listEl.querySelectorAll('.import-supp-remove').forEach(function(btn) {
        btn.addEventListener('click', function() {
          const idx = parseInt(this.dataset.idx);
          selectedSuppFiles.splice(idx, 1);
          renderSuppList();
          // 重置 input，允许重新选择
          document.getElementById('import-supp-input').value = '';
        });
      });
    }

    // ── 更新确认按钮状态 ──
    function updateConfirmBtn() {
      const btn = document.getElementById('import-confirm-btn');
      if (btn) {
        btn.disabled = !selectedPaperFile;
      }
    }

    // ── 执行导入 ──
    function handleImport() {
      if (!selectedPaperFile) {
        alert('请先选择正文 PDF 文件');
        return;
      }

      const confirmBtn = document.getElementById('import-confirm-btn');
      const cancelBtn = document.getElementById('import-cancel-btn');
      confirmBtn.disabled = true;
      cancelBtn.disabled = true;
      confirmBtn.textContent = '上传中...';

      // 构建 FormData
      const formData = new FormData();
      formData.append('paper', selectedPaperFile);
      selectedSuppFiles.forEach(function(f) {
        formData.append('supplementary', f);
      });

      // 第一步：上传文件
      fetch('/api/papers/import', {
        method: 'POST',
        body: formData
      })
        .then(function(r) { return r.json(); })
        .then(function(data) {
          if (!data.success) {
            throw new Error(data.error || '上传失败');
          }
          console.log('✅ 文件上传成功:', data.paper_filename,
            '补充材料:', data.supplementary_count, '个');

          confirmBtn.textContent = '解析中...';

          // 第二步：触发解析
          return triggerParse(data.paper_filename, data.supplementary_files);
        })
        .then(function(result) {
          if (result && result.success) {
            console.log('✅ 导入并解析完成:', result.paper_id);
            // 第三步：关联补充材料（如果有）
            if (result.supplementary_files && result.supplementary_files.length > 0) {
              return associateSupplementary(result.paper_id, result.supplementary_files)
                .then(function() { return result; });
            }
            return result;
          }
          throw new Error(result ? (result.error || '解析失败') : '解析失败');
        })
        .then(function(result) {
          // 全部完成
          close();
          if (config.onRefreshList) {
            config.onRefreshList();
          }
          if (config.onImportComplete && result) {
            config.onImportComplete(result.paper_id, result.paper_title, result.filename);
          }
          alert('✅ 导入成功！\n正文已解析，' +
            (result.supplementary_count > 0 ? result.supplementary_count + ' 个补充材料已关联。' : '无补充材料。'));
        })
        .catch(function(err) {
          console.error('❌ 导入失败:', err);
          confirmBtn.disabled = false;
          cancelBtn.disabled = false;
          confirmBtn.textContent = '开始导入';
          alert('❌ 导入失败: ' + err.message + '\n\n文件已上传到 documents 目录，可以在文献列表中手动点击解析。');
        });
    }

    // ── 触发解析（轮询等待完成） ──
    function triggerParse(filename, supplementaryFiles) {
      return fetch('/api/papers/parse', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filename: filename })
      })
        .then(function(r) { return r.json(); })
        .then(function(data) {
          if (data.error) {
            throw new Error(data.error);
          }
          return {
            success: true,
            paper_id: data.paper_id,
            paper_title: data.title || filename,
            filename: filename,
            paragraph_count: data.paragraph_count || 0,
            supplementary_files: supplementaryFiles || [],
            supplementary_count: (supplementaryFiles || []).length,
          };
        });
    }

    // ── 关联补充材料到 paper_id（按文件名关联已上传文件） ──
    function associateSupplementary(paperId, suppFiles) {
      const promises = suppFiles.map(function(supp) {
        return fetch('/api/papers/' + paperId + '/supplementary/link', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            filename: supp.filename,
            description: supp.original_name || '',
          })
        })
          .then(function(r) { return r.json(); })
          .then(function(data) {
            if (data.success) {
              console.log('🔗 补充材料关联成功:', supp.filename);
            } else {
              console.warn('⚠️ 补充材料关联失败:', supp.filename, data.error);
            }
            return data.success;
          })
          .catch(function(err) {
            console.warn('⚠️ 补充材料关联异常:', supp.filename, err);
            return false;
          });
      });
      return Promise.all(promises);
    }

    // ── 工具函数 ──
    function formatSize(bytes) {
      if (bytes > 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(2) + ' MB';
      if (bytes > 1024) return (bytes / 1024).toFixed(1) + ' KB';
      return bytes + ' B';
    }

    function getFileIcon(filename) {
      const ext = filename.split('.').pop().toLowerCase();
      if (ext === 'pdf') return '📕';
      if (['doc', 'docx'].indexOf(ext) >= 0) return '📘';
      if (['xls', 'xlsx', 'csv'].indexOf(ext) >= 0) return '📗';
      if (['ppt', 'pptx'].indexOf(ext) >= 0) return '📙';
      if (['zip', 'rar', '7z', 'tar', 'gz'].indexOf(ext) >= 0) return '📦';
      if (['png', 'jpg', 'jpeg', 'gif', 'svg'].indexOf(ext) >= 0) return '🖼';
      return '📎';
    }

    return {
      open: open,
      close: close,
    };
  }

  window.SciPal = window.SciPal || {};
  window.SciPal.createPaperImporter = createPaperImporter;

})();
