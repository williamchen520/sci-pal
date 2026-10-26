/** 论文详情页：?id=<paper_id>，数据来自 /api/papers/<id>。 */
const contentEl = document.getElementById('content');

function escapeHtml(text) {
    return String(text == null ? '' : text)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;')
        .replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

async function load() {
    const paperId = new URLSearchParams(window.location.search).get('id');
    if (!paperId) {
        contentEl.innerHTML = '<div class="empty error">缺少 ?id= 参数</div>';
        return;
    }
    try {
        const resp = await fetch(`/api/papers/${encodeURIComponent(paperId)}`);
        const body = await resp.json();
        if (!resp.ok) throw new Error(body.error || `HTTP ${resp.status}`);
        const paper = body.paper || {};
        document.title = `${paper.title || paperId} - Sci-Pal`;
        const doiLink = paper.doi
            ? `<a href="https://doi.org/${encodeURIComponent(paper.doi)}" target="_blank" rel="noreferrer">${escapeHtml(paper.doi)}</a>`
            : '';
        contentEl.innerHTML = `
            <h1>${escapeHtml(paper.title || paperId)}</h1>
            <div class="meta">
                ${escapeHtml(paper.authors || '')}
                ${paper.journal ? ` · ${escapeHtml(paper.journal)}` : ''}
                ${paper.year ? ` · ${escapeHtml(paper.year)}` : ''}
                ${doiLink ? ` · ${doiLink}` : ''}
            </div>
            <div class="abstract">${escapeHtml(paper.abstract || '（无摘要）')}</div>`;
    } catch (err) {
        contentEl.innerHTML = `<div class="empty error">加载失败：${escapeHtml(err.message)}</div>`;
    }
}

load();
