const state = { status: "proposed", plans: [] };

const list = document.getElementById("list");
const errorBox = document.getElementById("error");

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

function stepNode(step) {
  const box = el("div", "step");
  const main = el(
    "div",
    "step-main",
    `${step.step_order}. ${step.action} · ${step.rag_id}${step.library_id ? ` · ${step.library_id}` : ""}`
  );
  box.appendChild(main);
  const meta = el("div", "step-meta");
  meta.textContent = [
    step.query ? `query: ${step.query}` : "",
    step.snapshot ? `snapshot: ${step.snapshot}` : "",
    `status: ${step.status}`,
    `risk: ${step.risk_level}`,
  ]
    .filter(Boolean)
    .join(" · ");
  box.appendChild(meta);
  return box;
}

function planNode(plan) {
  const card = el("section", "plan");
  const title = el("h2", "", plan.intent || "(no intent)");
  const risk = el("span", `badge ${plan.risk_level}`, plan.risk_level);
  title.appendChild(risk);
  title.appendChild(el("span", "badge", plan.status));
  card.appendChild(title);

  const meta = el(
    "div",
    "meta",
    `${plan.plan_id} · created_by ${plan.created_by} · hash ${plan.plan_hash.slice(0, 12)}…` +
      (plan.approved_by ? ` · approved_by ${plan.approved_by}` : "")
  );
  card.appendChild(meta);

  const steps = el("div", "steps");
  for (const step of plan.steps || []) steps.appendChild(stepNode(step));
  card.appendChild(steps);

  const actions = el("div", "actions");
  if (plan.status === "proposed") {
    const approve = el("button", "approve", "批准");
    approve.addEventListener("click", async () => {
      approve.disabled = true;
      try {
        await api(`/api/rag/plans/${encodeURIComponent(plan.plan_id)}/approve`, {
          method: "POST",
          body: JSON.stringify({ plan_hash: plan.plan_hash }),
        });
        setStatus("approved");
        await load();
      } catch (error) {
        errorBox.textContent = error.message;
        approve.disabled = false;
      }
    });
    actions.appendChild(approve);
  }
  if (plan.status === "approved") {
    const dispatch = el("button", "dispatch", "派发");
    dispatch.addEventListener("click", async () => {
      dispatch.disabled = true;
      try {
        await api(`/api/rag/plans/${encodeURIComponent(plan.plan_id)}/dispatch`, {
          method: "POST",
          body: "{}",
        });
        setStatus("dispatched");
        await load();
      } catch (error) {
        errorBox.textContent = error.message;
        dispatch.disabled = false;
      }
    });
    actions.appendChild(dispatch);
  }
  if (["proposed", "approved", "dispatched", "running"].includes(plan.status)) {
    const cancel = el("button", "cancel", "取消");
    cancel.addEventListener("click", async () => {
      if (!confirm(`取消 ${plan.plan_id}？`)) return;
      try {
        await api(`/api/rag/plans/${encodeURIComponent(plan.plan_id)}/cancel`, {
          method: "POST",
          body: "{}",
        });
        await load();
      } catch (error) {
        errorBox.textContent = error.message;
      }
    });
    actions.appendChild(cancel);
  }
  card.appendChild(actions);
  return card;
}

function render() {
  list.replaceChildren();
  if (!state.plans.length) {
    list.appendChild(el("div", "empty", "没有计划。让 DSH 用 rag_plan 提交一个，或切换状态。"));
    return;
  }
  for (const plan of state.plans) list.appendChild(planNode(plan));
}

async function load() {
  errorBox.textContent = "";
  try {
    const body = await api(`/api/rag/plans?status=${encodeURIComponent(state.status)}`);
    state.plans = body.plans || [];
    render();
  } catch (error) {
    if (String(error.message).includes("401")) {
      window.location.replace("/login.html");
      return;
    }
    errorBox.textContent = error.message;
  }
}

function setStatus(status) {
  state.status = status;
  for (const item of document.querySelectorAll("#tabs button")) {
    item.classList.toggle("active", item.dataset.status === status);
  }
}

document.getElementById("tabs").addEventListener("click", (event) => {
  const button = event.target.closest("button[data-status]");
  if (!button) return;
  setStatus(button.dataset.status);
  load();
});

document.getElementById("refresh").addEventListener("click", load);

async function init() {
  try {
    await api("/api/auth/me");
  } catch {
    window.location.replace("/login.html");
    return;
  }
  await load();
}

init();
