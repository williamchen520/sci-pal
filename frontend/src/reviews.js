/**
 * 历史综述页：列表 + 详情。
 *
 * 数据来自 /api/reviews（reviews 表，CLI / 外部工具生成的综述也在这里），
 * 与 /review.html 的即时生成流程互补。
 */

const listEl = document.getElementById('reviewList');
const detailEl = document.getElementById('reviewDetail');
let activeId = null;

function escapeHtml(text) {
    return String(text == null ? '' : text)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

/** 极简 Markdown 渲染：先转义，再只处理标题/列表/段落，避免 XSS。 */
function renderMarkdown(markdown) {
    const lines = escapeHtml(markdown || '').split(/\r?\n/);
    const html = [];
    let listOpen = false;

    const closeList = () => {
        if (listOpen) { html.push('</ul>'); listOpen = false; }
    };

    for (const line of lines) {
        const text = line.trim();
        if (!text) { closeList(); continue; }

        const heading = text.match(/^(#{1,3})\s+(.*)$/);
        if (heading) {
            closeList();
            const level = heading[1].length;
            html.push(`<h${level}>${heading[2]}</h${level}>`);
            continue;
        }

        const bullet = text.match(/^[-*]\s+(.*)$/);
        if (bullet) {
            if (!listOpen) { html.push('<ul>'); listOpen = true; }
            html.push(`<li>${bullet[1]}</li>`);
            continue;
        }

        closeList();
        html.push(`<p>${text}</p>`);
    }
    closeList();
    return html.join('');
}

function formatTime(value) {
    if (!value) return '';
    const date = new Date(value);
    return isNaN(date.getTime()) ? value : date.toLocaleString();
}

/** draft.md 以 "# 主题" 开头，详情页已单独显示标题，这里去掉重复的一级标题。 */
function stripDuplicateTitle(markdown, topic) {
    const lines = String(markdown || '').split(/\r?\n/);
    const first = lines[0] ? lines[0].trim() : '';
    if (/^#\s+/.test(first)) {
        const title = first.replace(/^#\s+/, '').trim();
        if (!topic || title.toLowerCase() === String(topic).trim().toLowerCase()) {
            lines.shift();
        }
    }
    return lines.join('\n');
}

function renderList(reviews) {
    if (!reviews.length) {
        listEl.innerHTML = '<div class="empty">还没有已保存的综述</div>';
        return;
    }
    listEl.innerHTML = reviews.map((review) => {
        const stats = review.stats || {};
        const rate = stats.pass_rate != null ? `${Math.round(stats.pass_rate * 100)}%` : '—';
        return `
            <div class="card${review.review_id === activeId ? ' active' : ''}" data-id="${escapeHtml(review.review_id)}">
                <div class="card-title">${escapeHtml(review.topic || '(无标题)')}</div>
                <div class="card-meta">${formatTime(review.created_at)} · 引用通过率 ${rate}</div>
            </div>`;
    }).join('');

    listEl.querySelectorAll('.card').forEach((card) => {
        card.addEventListener('click', () => loadReview(card.dataset.id));
    });
}

function renderDetail(review) {
    const stats = review.stats || {};
    const references = review.references || [];
    const guard = review.guard || null;
    const guardCounts = (guard && guard.counts) || {};
    const defined = (guard && guard.defined_abbreviations) || {};
    const definedEntries = Object.entries(defined);
    const definedText = definedEntries.length ? ` · 文中定义 ${definedEntries.length}` : '';
    const guardBadge = guard && guard.checked
        ? `<div class="guard-badge">🛡 术语校验：checked ${guard.checked} · curated ${guardCounts.known_curated || 0}` +
          ` · ambiguous ${guardCounts.ambiguous || 0} · unknown ${guard.unknown || 0}` +
          `（${((guard.unknown_ratio || 0) * 100).toFixed(2)}%）${definedText}</div>` +
          (definedEntries.length
              ? `<details class="guard-defs"><summary>文中定义的缩写（${definedEntries.length}）</summary><ul>` +
                definedEntries.map(([abbr, full]) => `<li><strong>${escapeHtml(abbr)}</strong> = ${escapeHtml(full)}</li>`).join('') +
                '</ul></details>'
              : '')
        : '';
    detailEl.innerHTML = `
        <h2>${escapeHtml(review.topic || '(无标题)')}</h2>
        <div class="meta">
            ${escapeHtml(review.review_id)} · ${formatTime(review.created_at)}
            ${stats.total_sentences != null ? ` · ${stats.verified}/${stats.total_sentences} 句通过校验` : ''}
            ${review.run_id ? ` · run ${escapeHtml(review.run_id)}` : ''}
        </div>
        ${guardBadge}
        <div class="actions">
            <button onclick="createProtocolDraft('${escapeHtml(review.review_id)}')">🧪 生成实验方案草稿</button>
            <span id="draftStatus" class="meta"></span>
        </div>
        <div class="markdown">${renderMarkdown(stripDuplicateTitle(review.markdown, review.topic))}</div>
        ${references.length ? `
            <div class="refs">
                <h3>参考文献（${references.length}）</h3>
                <ol>
                    ${references.map((ref) => {
                        const title = escapeHtml(String(ref.title || '').replace(/^[#\s]+/, ''));
                        const linkedTitle = ref.paper_id
                            ? `<a href="/paper.html?id=${encodeURIComponent(ref.paper_id)}">${title}</a>`
                            : title;
                        const doi = ref.doi_url
                            ? ` · <a href="${escapeHtml(ref.doi_url)}" target="_blank" rel="noreferrer">DOI</a>`
                            : '';
                        return `<li>${escapeHtml(ref.authors || '')} ${escapeHtml(ref.year || '')} ${linkedTitle} ${escapeHtml(ref.journal || '')}${doi}</li>`;
                    }).join('')}
                </ol>
            </div>` : ''}
    `;
}

async function createProtocolDraft(reviewId) {
    const status = document.getElementById('draftStatus');
    if (!status) return;
    status.textContent = '生成中…';
    try {
        const resp = await fetch(`/api/reviews/${encodeURIComponent(reviewId)}/to-protocol`, {
            method: 'POST',
        });
        const body = await resp.json();
        if (!resp.ok || !body.ok) throw new Error(body.error || `HTTP ${resp.status}`);
        status.innerHTML = `已生成草稿 <a href="/protocols.html">${escapeHtml(body.protocol_id)}</a>（${body.steps} 步）`;
    } catch (err) {
        status.textContent = `生成失败：${err.message}`;
    }
}

async function loadReview(reviewId) {
    activeId = reviewId;
    listEl.querySelectorAll('.card').forEach((card) => {
        card.classList.toggle('active', card.dataset.id === reviewId);
    });
    detailEl.innerHTML = '<div class="empty">加载中...</div>';
    try {
        const resp = await fetch(`/api/reviews/${encodeURIComponent(reviewId)}`);
        const body = await resp.json();
        if (!resp.ok || !body.ok) {
            throw new Error((body.error && body.error.message) || `HTTP ${resp.status}`);
        }
        renderDetail(body.data);
    } catch (err) {
        detailEl.innerHTML = `<div class="empty error">加载失败：${escapeHtml(err.message)}</div>`;
    }
}

async function loadList() {
    try {
        const resp = await fetch('/api/reviews?limit=50');
        const body = await resp.json();
        if (!resp.ok || !body.ok) {
            throw new Error((body.error && body.error.message) || `HTTP ${resp.status}`);
        }
        renderList(body.data.reviews || []);
    } catch (err) {
        listEl.innerHTML = `<div class="empty error">加载失败：${escapeHtml(err.message)}</div>`;
    }
}

loadList().then(() => {
    const requested = new URLSearchParams(location.search).get('review_id');
    if (requested) loadReview(requested);
});
