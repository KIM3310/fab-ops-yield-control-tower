function renderList(container, items, formatter) {
  container.innerHTML = "";
  items.forEach((item) => {
    const node = document.createElement("article");
    node.className = "stack-item";
    node.innerHTML = formatter(item);
    container.appendChild(node);
  });
}

async function fetchJson(path) {
  const response = await fetch(path);
  if (!response.ok) {
    throw new Error(`${path} failed with ${response.status}`);
  }
  return response.json();
}

async function boot() {
  const briefStatus = document.getElementById("brief-status");
  const criticalCount = document.getElementById("critical-count");
  const severeCount = document.getElementById("severe-count");
  const replayScore = document.getElementById("replay-score");
  const reviewHeadline = document.getElementById("review-headline");
  const reviewPromises = document.getElementById("review-promises");
  const reviewBoundary = document.getElementById("review-boundary");
  const alarmList = document.getElementById("alarm-list");
  const lotList = document.getElementById("lot-list");
  const toolList = document.getElementById("tool-list");
  const handoffHeadline = document.getElementById("handoff-headline");
  const handoffActions = document.getElementById("handoff-actions");
  const replayList = document.getElementById("replay-list");

  try {
    const [brief, reviewPack, alarms, lots, tools, handoff, replay] = await Promise.all([
      fetchJson("/api/runtime/brief"),
      fetchJson("/api/review-pack"),
      fetchJson("/api/alarms"),
      fetchJson("/api/lots/at-risk"),
      fetchJson("/api/tools"),
      fetchJson("/api/shift-handoff"),
      fetchJson("/api/evals/replays"),
    ]);

    briefStatus.textContent = brief.status.toUpperCase();
    criticalCount.textContent = String(brief.ops_snapshot.critical_alarm_count);
    severeCount.textContent = String(brief.ops_snapshot.severe_lot_count);
    replayScore.textContent = `${replay.summary.score_pct}%`;

    reviewHeadline.textContent = reviewPack.headline;
    reviewPromises.innerHTML = "";
    reviewPack.operator_promises.forEach((item) => {
      const li = document.createElement("li");
      li.textContent = item;
      reviewPromises.appendChild(li);
    });

    reviewBoundary.innerHTML = "";
    reviewPack.trust_boundary.forEach((item) => {
      const li = document.createElement("li");
      li.textContent = item;
      reviewBoundary.appendChild(li);
    });

    renderList(alarmList, alarms.items, (item) => `
      <p class="stack-kicker">${item.severity.toUpperCase()} · ${item.tool_id}</p>
      <h3>${item.category}</h3>
      <p>${item.symptom}</p>
      <p class="stack-meta">Lot ${item.lot_id} · SOP ${item.sop_ref}</p>
    `);

    renderList(lotList, lots.items, (item) => `
      <p class="stack-kicker">${item.risk_bucket.toUpperCase()} · ${item.tool_id}</p>
      <h3>${item.lot_id}</h3>
      <p>${item.product_family}</p>
      <p class="stack-meta">Risk ${item.yield_risk_score} · ${item.next_action}</p>
    `);

    renderList(toolList, tools.items, (item) => `
      <p class="stack-kicker">${item.status.toUpperCase()} · ${item.line}</p>
      <h3>${item.tool_id}</h3>
      <p>Chamber ${item.chamber}</p>
      <p class="stack-meta">PM ${item.last_pm_hours}h · MTBF ${item.mtbf_risk}</p>
    `);

    handoffHeadline.textContent = handoff.payload.headline;
    handoffActions.innerHTML = "";
    handoff.payload.must_acknowledge.forEach((item) => {
      const li = document.createElement("li");
      li.textContent = item;
      handoffActions.appendChild(li);
    });

    renderList(replayList, replay.runs, (item) => `
      <p class="stack-kicker">${item.status.toUpperCase()}</p>
      <h3>${item.scenario}</h3>
      <p class="stack-meta">${item.checks} checks</p>
    `);
  } catch (error) {
    briefStatus.textContent = "ERROR";
    reviewHeadline.textContent = "Runtime surfaces unavailable";
    console.error(error);
  }
}

document.addEventListener("DOMContentLoaded", boot);
