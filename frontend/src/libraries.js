const state = { libraries: [], selected: null };

const $ = (id) => document.getElementById(id);

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  }[ch]));
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const body = await response.json().catch(() => ({ error: "invalid JSON" }));
  if (!response.ok) throw new Error(body.error || `HTTP ${response.status}`);
  return body;
}

function renderLibraries() {
  const root = $("libraries");
  root.innerHTML = "";
  if (!state.libraries.length) {
    root.innerHTML = '<p class="muted">还没有代码库。</p>';
    return;
  }
  for (const library of state.libraries) {
    const div = document.createElement("div");
    div.className = "library" + (state.selected?.library_id === library.library_id ? " active" : "");
    div.innerHTML = `<strong>${escapeHtml(library.name)}</strong>
      <div class="muted">${escapeHtml(library.status)} · ${escapeHtml(library.library_id)}</div>`;
    div.addEventListener("click", () => selectLibrary(library));
    root.appendChild(div);
  }
}

async function loadLibraries() {
  try {
    const body = await api("/api/libraries?kind=code");
    state.libraries = body.libraries || [];
    renderLibraries();
    if (!state.selected && state.libraries.length) selectLibrary(state.libraries[0]);
  } catch (error) {
    $("message").textContent = error.message;
  }
}

async function selectLibrary(library) {
  state.selected = library;
  renderLibraries();
  $("current").textContent = `${library.name} · ${library.library_id}`;
  $("hits").innerHTML = "";
  $("trace").textContent = "选择结果的“Trace”查看 1–2 跳。";
  await loadStatus();
}

async function loadStatus() {
  if (!state.selected) return;
  try {
    const body = await api(`/api/code/libraries/${encodeURIComponent(state.selected.library_id)}/status`);
    const lib = body.library || {};
    $("status").innerHTML = [
      `<span>schema v${escapeHtml(body.schema_version)}</span>`,
      `<span>snapshots ${escapeHtml(lib.snapshots ?? 0)}</span>`,
      `<span>units ${escapeHtml(lib.units ?? 0)}</span>`,
      `<span>${body.ok ? "healthy" : "degraded"}</span>`,
    ].join("");
  } catch (error) {
    $("status").innerHTML = `<span style="color:#fca5a5">${escapeHtml(error.message)}</span>`;
  }
}

async function createLibrary() {
  const name = $("name").value.trim();
  const repoUrl = $("repo_url").value.trim();
  if (!name || !repoUrl) {
    $("message").textContent = "名称和 repo URL 必填";
    return;
  }
  try {
    await api("/api/libraries", {
      method: "POST",
      body: JSON.stringify({
        name,
        kind: "code",
        config: { repo_url: repoUrl, ref: $("ref").value.trim() },
      }),
    });
    $("name").value = "";
    $("repo_url").value = "";
    $("ref").value = "";
    $("message").textContent = "已注册；索引完成后可搜索。";
    await loadLibraries();
  } catch (error) {
    $("message").textContent = error.message;
  }
}

async function runSearch() {
  if (!state.selected) return;
  const query = $("query").value.trim();
  if (!query) return;
  $("message").textContent = "搜索中…";
  $("hits").innerHTML = "";
  try {
    const body = await api(`/api/code/libraries/${encodeURIComponent(state.selected.library_id)}/search`, {
      method: "POST",
      body: JSON.stringify({ query, top_k: 8 }),
    });
    $("message").textContent = `${body.hits.length} 条结果`;
    for (const hit of body.hits) {
      const div = document.createElement("div");
      div.className = "hit";
      div.innerHTML = `<strong>${escapeHtml(hit.symbol_name)}</strong>
        <span class="muted"> ${escapeHtml(hit.unit_type)} · ${escapeHtml(hit.path)}:${hit.start_line}-${hit.end_line}</span>
        <pre>${escapeHtml(hit.snippet)}</pre>`;
      const traceButton = document.createElement("button");
      traceButton.className = "secondary";
      traceButton.textContent = "Trace";
      traceButton.addEventListener("click", () => runTrace(hit.unit_id));
      div.appendChild(traceButton);
      $("hits").appendChild(div);
    }
  } catch (error) {
    $("message").textContent = error.message;
  }
}

async function runTrace(unitId) {
  if (!state.selected) return;
  $("trace").textContent = "图扩展中…";
  try {
    const params = new URLSearchParams({ unit_id: unitId, direction: "both", max_hops: "2", max_nodes: "30" });
    const body = await api(`/api/code/libraries/${encodeURIComponent(state.selected.library_id)}/trace?${params}`);
    const lines = [
      `start: ${body.start}`,
      `nodes: ${body.nodes.length}`,
      "",
      ...body.nodes.map((node) => `${node.symbol_name}  ${node.path}:${node.start_line}-${node.end_line}`),
      "",
      "edges:",
      ...body.edges.slice(0, 40).map((edge) => `${edge.src} --${edge.relation}--> ${edge.dst}`),
    ];
    $("trace").textContent = lines.join("\n");
  } catch (error) {
    $("trace").textContent = error.message;
  }
}

$("create").addEventListener("click", createLibrary);
$("search").addEventListener("click", runSearch);
$("query").addEventListener("keydown", (event) => { if (event.key === "Enter") runSearch(); });
loadLibraries();
