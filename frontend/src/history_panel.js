/** 综述生成页内嵌「历史综述」列表：点击跳到 reviews.html 并自动打开该篇。 */
(function () {
    const toggle = document.getElementById('historyToggle');
    const panel = document.getElementById('historyPanel');
    if (!toggle || !panel) return;

    let loaded = false;

    function formatTime(value) {
        if (!value) return '';
        const date = new Date(value);
        return isNaN(date.getTime()) ? value : date.toLocaleString();
    }

    async function load() {
        panel.innerHTML = '<div class="history-empty">加载中...</div>';
        try {
            const resp = await fetch('/api/reviews?limit=10');
            const body = await resp.json();
            if (!resp.ok || !body.ok) throw new Error((body.error && body.error.message) || resp.status);
            const reviews = body.data.reviews || [];
            if (!reviews.length) {
                panel.innerHTML = '<div class="history-empty">还没有已保存的综述</div>';
                return;
            }
            panel.innerHTML = reviews.map((review) => {
                const rate = review.stats && review.stats.pass_rate != null
                    ? `${Math.round(review.stats.pass_rate * 100)}%` : '—';
                const href = `/reviews.html?review_id=${encodeURIComponent(review.review_id)}`;
                return `<a class="history-item" href="${href}">
                    <div class="history-title">${escapeHtml(review.topic || '(无标题)')}</div>
                    <div class="history-meta">${formatTime(review.created_at)} · 通过率 ${rate}</div>
                </a>`;
            }).join('');
        } catch (err) {
            panel.innerHTML = `<div class="history-empty">加载失败：${escapeHtml(err.message)}</div>`;
        }
    }

    function escapeHtml(text) {
        return String(text == null ? '' : text)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;')
            .replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    }

    toggle.addEventListener('click', async () => {
        panel.classList.toggle('hidden');
        if (!panel.classList.contains('hidden') && !loaded) {
            loaded = true;
            await load();
        }
    });
})();
