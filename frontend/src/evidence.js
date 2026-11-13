const content = document.getElementById("content");
const errorBox = document.getElementById("error");
const params = new URLSearchParams(window.location.search);
const multiRunId = params.get("multi_run_id") || "";

async function api(path, options = {}) {
  const response = await fetch(path, {
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.error || `请求失败 (${response.status})`);
  return body;
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function evidenceText(item) {
  const metadata = item.metadata || {};
  if (metadata.snippet) return metadata.snippet;
  if (metadata.text) return metadata.text;
  const sentences = metadata.matched_sentences || [];
  if (sentences.length) return sentences.map((sentence) => sentence.text || "").join(" ");
  return "(evidence text unavailable)";
}

function evidenceNode(item) {
  const box = el("div", "evidence");
  const source = el("div", "source", item.source_path || item.rag_id || "");
  box.appendChild(source);
  box.appendChild(el("div", "text", evidenceText(item)));
  const meta = el(
    "div",
    "source",
    `evidence_id=${item.evidence_id}` +
      (item.score !== null && item.score !== undefined ? ` · score=${Number(item.score).toFixed(4)}` : "")
  );
  box.appendChild(meta);
  return box;
}

function groupNode(group) {
  const card = el("section", "group");
  const title = el("h2", "", `${group.rag_id} · ${group.result_count} 条`);
  title.appendChild(el("span", `signal ${group.machine_signal}`, group.machine_signal || "unknown"));
  card.appendChild(title);
  if (group.run_id) card.appendChild(el("div", "source", `run_id=${group.run_id}`));

  if (!group.evidence.length) {
    card.appendChild(el("div", "empty", "没有证据。机器信号是 insufficient_evidence。"));
  } else {
    for (const item of group.evidence) card.appendChild(evidenceNode(item));
  }

  const decisions = el("div", "decisions");
  const existing = group.adjudications || [];
  if (existing.length) {
    const list = el("ul", "");
    for (const item of existing) list.appendChild(el("li", "", `${item.decision} · ${item.decided_by} · ${item.note}`));
    decisions.appendChild(list);
  }
  const conflicts = (group.conflicts || []);
  if (conflicts.length) {
    const list = el("ul", "");
    for (const item of conflicts) list.appendChild(el("li", "", `冲突 · ${item.flagged_by} · ${item.note}`));
    decisions.appendChild(list);
  }
  card.appendChild(decisions);

  const form = el("div", "decision");
  const select = document.createElement("select");
  for (const [value, label] of [
    ["accept", "接受证据"],
    ["reject", "拒绝证据"],
    ["needs_more_evidence", "需要更多证据"],
  ]) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = label;
    select.appendChild(option);
  }
  const note = document.createElement("textarea");
  note.placeholder = "裁决理由（会写入审计）";
  const submit = el("button", "", "记录人工裁决");
  submit.addEventListener("click", async () => {
    submit.disabled = true;
    try {
      await api(`/api/rag/multi/${encodeURIComponent(multiRunId)}/adjudications`, {
        method: "POST",
        body: JSON.stringify({ rag_id: group.rag_id, decision: select.value, note: note.value }),
      });
      await load();
    } catch (error) {
      errorBox.textContent = error.message;
      submit.disabled = false;
    }
  });
  const flag = el("button", "flag", "标记冲突");
  flag.addEventListener("click", async () => {
    const reason = window.prompt("冲突说明（会写入审计）");
    if (!reason) return;
    flag.disabled = true;
    try {
      await api(`/api/rag/multi/${encodeURIComponent(multiRunId)}/conflicts`, {
        method: "POST",
        body: JSON.stringify({ rag_id: group.rag_id, note: reason }),
      });
      await load();
    } catch (error) {
      errorBox.textContent = error.message;
      flag.disabled = false;
    }
  });
  form.appendChild(select);
  form.appendChild(note);
  form.appendChild(submit);
  form.appendChild(flag);
  card.appendChild(form);
  return card;
}

function attachAdjudications(run, group) {
  group.adjudications = (run.adjudications || []).filter(
    (item) => item.rag_id === group.rag_id || item.rag_id === "*"
  );
  group.conflicts = (run.conflicts || []).filter((item) => item.rag_id === group.rag_id);
  return group;
}

async function load() {
  errorBox.textContent = "";
  content.replaceChildren();
  if (!multiRunId) {
    const body = await api("/api/rag/multi");
    if (!body.multi_runs.length) {
      content.appendChild(el("div", "empty", "还没有多 RAG 查询。"));
      return;
    }
    for (const run of body.multi_runs) {
      const link = el("a", "run", run.query);
      link.href = `/evidence.html?multi_run_id=${encodeURIComponent(run.multi_run_id)}`;
      link.appendChild(el("div", "meta", `${run.multi_run_id} · ${(run.rag_ids || []).join(", ")} · ${run.created_at}`));
      content.appendChild(link);
    }
    return;
  }
  const run = await api(`/api/rag/multi/${encodeURIComponent(multiRunId)}`);
  const header = el("section", "group");
  header.appendChild(el("h2", "", run.query));
  header.appendChild(el("div", "meta", `${run.multi_run_id} · ${(run.rag_ids || []).join(", ")}`));
  const exportLink = el("a", "source", "导出审计 JSON");
  exportLink.href = `/api/rag/multi/${encodeURIComponent(multiRunId)}/export.json`;
  header.appendChild(exportLink);
  content.appendChild(header);
  for (const raw of run.groups) content.appendChild(groupNode(attachAdjudications(run, raw)));
}

async function init() {
  try {
    await api("/api/auth/me");
  } catch {
    window.location.replace("/login.html");
    return;
  }
  try {
    await load();
  } catch (error) {
    errorBox.textContent = error.message;
  }
}

init();
