/* V25.13 - Sci-Pal 三栏拖拽调宽模块（独立）— 基于相邻元素
 *
 * 职责：
 * 1. 监听 .resizer 拖拽条的 mousedown/mousemove/mouseup
 * 2. 拖动时调整左侧面板（previousElementSibling）宽度
 * 3. 右侧 flex:1 面板自动填充剩余空间
 * 4. 宽度保存到 localStorage，刷新后恢复
 * 5. 双击分隔条重置默认宽度
 * 6. 最小宽度限制
 *
 * V25.13 变更：从按 class 查找改为按相邻元素查找
 * - 每个 resizer 调整其 previousElementSibling（左侧面板）
 * - 互换布局后无需修改 data-panel，自动适配
 * - 不依赖面板的 class 名称，更健壮
 */

(function() {
  'use strict';

  const STORAGE_KEY = 'scipal_panel_widths';
  const MIN_PANEL = 200;   // 面板最小宽度 px

  let activeResizer = null;
  let startX = 0;
  let startWidth = 0;

  function init() {
    const resizers = document.querySelectorAll('.resizer');
    if (resizers.length === 0) return;

    restoreWidths();

    resizers.forEach(function(resizer) {
      resizer.addEventListener('mousedown', startDrag);
      resizer.addEventListener('dblclick', resetWidth);
    });

    document.addEventListener('mousemove', onDrag);
    document.addEventListener('mouseup', stopDrag);
  }

  function startDrag(e) {
    e.preventDefault();
    activeResizer = e.currentTarget;
    startX = e.clientX;

    // 调整左侧面板（previousElementSibling）
    const leftPanel = activeResizer.previousElementSibling;
    if (!leftPanel) return;
    startWidth = leftPanel.offsetWidth;

    document.body.classList.add('resizing');
    activeResizer.classList.add('active');
  }

  function onDrag(e) {
    if (!activeResizer) return;
    e.preventDefault();

    const leftPanel = activeResizer.previousElementSibling;
    if (!leftPanel) return;

    const dx = e.clientX - startX;
    const newWidth = Math.max(MIN_PANEL, startWidth + dx);

    // 确保右侧还有空间（不超过容器宽度的 80%）
    const main = leftPanel.parentElement;
    if (main) {
      const maxWidth = main.clientWidth * 0.8;
      if (newWidth > maxWidth) return;
    }

    leftPanel.style.flex = 'none';
    leftPanel.style.width = newWidth + 'px';
  }

  function stopDrag() {
    if (!activeResizer) return;
    document.body.classList.remove('resizing');
    activeResizer.classList.remove('active');
    activeResizer = null;
    saveWidths();
  }

  function resetWidth(e) {
    const leftPanel = e.currentTarget.previousElementSibling;
    if (!leftPanel) return;
    leftPanel.style.flex = '';
    leftPanel.style.width = '';
    saveWidths();
  }

  function saveWidths() {
    const main = document.querySelector('.editor-main');
    if (!main) return;
    // 保存所有非 flex:1 面板的宽度
    const data = {};
    const panels = main.querySelectorAll('.editor-left, .editor-center, .editor-pdf');
    panels.forEach(function(panel) {
      const cls = panel.className.split(' ')[0];
      if (panel.style.width) {
        data[cls] = panel.style.width;
      }
    });
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
    } catch (e) {}
  }

  function restoreWidths() {
    let data = null;
    try {
      data = JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null');
    } catch (e) {
      return;
    }
    if (!data) return;

    const main = document.querySelector('.editor-main');
    if (!main) return;

    Object.keys(data).forEach(function(cls) {
      const panel = main.querySelector('.' + cls);
      if (panel && data[cls]) {
        panel.style.flex = 'none';
        panel.style.width = data[cls];
      }
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

})();
