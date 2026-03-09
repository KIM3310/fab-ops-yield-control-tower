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

function populateSelect(select, items, valueKey, labelBuilder, selectedValue) {
  select.innerHTML = "";
  items.forEach((item) => {
    const option = document.createElement("option");
    option.value = item[valueKey];
    option.textContent = labelBuilder(item);
    if (item[valueKey] === selectedValue) {
      option.selected = true;
    }
    select.appendChild(option);
  });
}

async function boot() {
  const briefStatus = document.getElementById("brief-status");
  const criticalCount = document.getElementById("critical-count");
  const severeCount = document.getElementById("severe-count");
  const replayScore = document.getElementById("replay-score");
  const reviewHeadline = document.getElementById("review-headline");
  const reviewPromises = document.getElementById("review-promises");
  const reviewBoundary = document.getElementById("review-boundary");
  const reviewRoutePreview = document.getElementById("review-route-preview");
  const alarmList = document.getElementById("alarm-list");
  const lotList = document.getElementById("lot-list");
  const toolList = document.getElementById("tool-list");
  const toolOwnership = document.getElementById("tool-ownership");
  const releaseGate = document.getElementById("release-gate");
  const auditFeed = document.getElementById("audit-feed");
  const recoveryBoard = document.getElementById("recovery-board");
  const recoveryModeSelect = document.getElementById("recovery-mode-select");
  const handoffHeadline = document.getElementById("handoff-headline");
  const handoffActions = document.getElementById("handoff-actions");
  const handoffSignature = document.getElementById("handoff-signature");
  const replayList = document.getElementById("replay-list");
  const toolSelect = document.getElementById("tool-select");
  const lotSelect = document.getElementById("lot-select");
  const focusSevereLotBtn = document.getElementById("focus-severe-lot-btn");
  const copyReviewRouteBtn = document.getElementById("copy-review-route-btn");
  const copySevereLotBtn = document.getElementById("copy-severe-lot-btn");
  const copyShiftSnapshotBtn = document.getElementById("copy-shift-snapshot-btn");
  const refreshBoardBtn = document.getElementById("refresh-board-btn");

  let selectedToolId = "etch-14";
  let selectedLotId = "lot-8812";
  let latestLots = [];
  let latestSignatureId = "";
  let latestOwnership = null;
  let latestGate = null;
  let latestHandoff = null;
  let latestSignaturePayload = null;
  let latestRecoveryBoard = null;
  let selectedRecoveryMode = "all";

  async function copyTextValue(text) {
    if (!text) return false;
    try {
      if (navigator.clipboard && typeof navigator.clipboard.writeText === "function") {
        await navigator.clipboard.writeText(text);
        return true;
      }
    } catch {
      // Fallback below.
    }

    try {
      const temp = document.createElement("textarea");
      temp.value = text;
      temp.style.position = "fixed";
      temp.style.opacity = "0";
      document.body.appendChild(temp);
      temp.focus();
      temp.select();
      const success = document.execCommand("copy");
      document.body.removeChild(temp);
      return Boolean(success);
    } catch {
      return false;
    }
  }

  async function loadFocusedPanels() {
    const [ownership, gate, signature] = await Promise.all([
      fetchJson(`/api/tool-ownership?tool_id=${encodeURIComponent(selectedToolId)}`),
      fetchJson(`/api/release-gate?lot_id=${encodeURIComponent(selectedLotId)}`),
      fetchJson("/api/shift-handoff/signature"),
    ]);
    latestOwnership = ownership.payload;
    latestGate = gate.payload;
    latestSignaturePayload = signature.payload;

    renderList(toolOwnership, [ownership.payload], (item) => `
      <p class="stack-kicker">${item.tool_id.toUpperCase()} · ${item.status.toUpperCase()}</p>
      <h3>${item.primary_operator}</h3>
      <p>${item.maintenance_owner} · ${item.escalation_lane}</p>
      <p class="stack-meta">Due ${item.due_by} · Ack ${item.ack_required ? "required" : "not required"}</p>
    `);

    renderList(releaseGate, [gate.payload], (item) => `
      <p class="stack-kicker">${item.decision.toUpperCase()} · ${item.tool_id}</p>
      <h3>${item.lot_id}</h3>
      <p>${item.next_action}</p>
      <p class="stack-meta">Risk ${item.yield_risk_score} · ${item.failed_checks.join(" / ") || "no failed checks"}</p>
    `);

    reviewRoutePreview.innerHTML = "";
    [
      `tool ownership -> /api/tool-ownership?tool_id=${selectedToolId}`,
      `release gate -> /api/release-gate?lot_id=${selectedLotId}`,
      `handoff signature -> ${signature.payload.signature_id}`,
      `next action -> ${gate.payload.next_action}`,
    ].forEach((item) => {
      const li = document.createElement("li");
      li.textContent = item;
      reviewRoutePreview.appendChild(li);
    });
  }

  async function loadBoard() {
    const [brief, reviewPack, alarms, lots, tools, audit, handoff, signature, replay, recovery] = await Promise.all([
      fetchJson("/api/runtime/brief"),
      fetchJson("/api/review-pack"),
      fetchJson("/api/alarms"),
      fetchJson("/api/lots/at-risk"),
      fetchJson("/api/tools"),
      fetchJson("/api/audit/feed"),
      fetchJson("/api/shift-handoff"),
      fetchJson("/api/shift-handoff/signature"),
      fetchJson("/api/evals/replays"),
      fetchJson(`/api/recovery-board?mode=${encodeURIComponent(selectedRecoveryMode)}`),
    ]);
    latestSignatureId = signature.payload.signature_id || "";
    latestHandoff = handoff.payload;
    latestSignaturePayload = signature.payload;
    latestRecoveryBoard = recovery;

    briefStatus.textContent = brief.status.toUpperCase();
    criticalCount.textContent = String(brief.ops_snapshot.critical_alarm_count);
    severeCount.textContent = String(brief.ops_snapshot.severe_lot_count);
    replayScore.textContent = `${replay.summary.score_pct}%`;

    reviewHeadline.textContent = reviewPack.headline;
    reviewPromises.innerHTML = "";
    [...reviewPack.operator_promises, ...(reviewPack.two_minute_review || []).map((item) => `2-minute: ${item}`)].forEach((item) => {
      const li = document.createElement("li");
      li.textContent = item;
      reviewPromises.appendChild(li);
    });

    reviewBoundary.innerHTML = "";
    [
      ...reviewPack.trust_boundary,
      ...((reviewPack.proof_assets || []).map((item) => `proof: ${item.label} -> ${item.href}`)),
    ].forEach((item) => {
      const li = document.createElement("li");
      li.textContent = item;
      reviewBoundary.appendChild(li);
    });

    renderList(recoveryBoard, recovery.items, (item) => `
      <p class="stack-kicker">${item.board_status.toUpperCase()} · ${item.tool_id}</p>
      <h3>${item.lot_id}</h3>
      <p>${item.next_action}</p>
      <p class="stack-meta">Risk ${item.yield_risk_score} · ${item.maintenance_owner} · ${item.failed_checks.join(" / ") || "no failed checks"}</p>
    `);

    const toolItems = tools.items || [];
    const lotItems = lots.items || [];
    latestLots = lotItems;
    if (!toolItems.find((item) => item.tool_id === selectedToolId) && toolItems[0]) {
      selectedToolId = toolItems[0].tool_id;
    }
    if (!lotItems.find((item) => item.lot_id === selectedLotId) && lotItems[0]) {
      selectedLotId = lotItems[0].lot_id;
    }

    populateSelect(toolSelect, toolItems, "tool_id", (item) => `${item.tool_id} · ${item.status}`, selectedToolId);
    populateSelect(lotSelect, lotItems, "lot_id", (item) => `${item.lot_id} · risk ${item.yield_risk_score}`, selectedLotId);

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

    renderList(auditFeed, audit.items, (item) => `
      <p class="stack-kicker">${item.event.toUpperCase()} · ${item.tool_id}</p>
      <h3>${item.actor}</h3>
      <p>Lot ${item.lot_id}</p>
      <p class="stack-meta">${item.at}</p>
    `);

    handoffHeadline.textContent = handoff.payload.headline;
    handoffActions.innerHTML = "";
    handoff.payload.must_acknowledge.forEach((item) => {
      const li = document.createElement("li");
      li.textContent = item;
      handoffActions.appendChild(li);
    });

    renderList(handoffSignature, [signature.payload], (item) => `
      <p class="stack-kicker">${item.signature_contract.toUpperCase()}</p>
      <h3>${item.signature_id}</h3>
      <p>${item.signed_by} · ${item.release_channel}</p>
      <p class="stack-meta">Digest ${item.digest_preview}</p>
    `);

    renderList(replayList, replay.runs, (item) => `
      <p class="stack-kicker">${item.status.toUpperCase()}</p>
      <h3>${item.scenario}</h3>
      <p class="stack-meta">${item.checks} checks</p>
    `);

    document.querySelectorAll("#tool-list .stack-item").forEach((node, index) => {
      node.classList.toggle("selected", toolItems[index]?.tool_id === selectedToolId);
      node.addEventListener("click", () => {
        selectedToolId = toolItems[index].tool_id;
        toolSelect.value = selectedToolId;
        loadBoard().catch(handleLoadError);
      });
    });

    document.querySelectorAll("#lot-list .stack-item").forEach((node, index) => {
      node.classList.toggle("selected", lotItems[index]?.lot_id === selectedLotId);
      node.addEventListener("click", () => {
        selectedLotId = lotItems[index].lot_id;
        lotSelect.value = selectedLotId;
        loadBoard().catch(handleLoadError);
      });
    });

    document.querySelectorAll("#audit-feed .stack-item").forEach((node, index) => {
      node.classList.toggle(
        "selected",
        audit.items[index]?.tool_id === selectedToolId && audit.items[index]?.lot_id === selectedLotId
      );
      node.addEventListener("click", () => {
        selectedToolId = audit.items[index].tool_id;
        selectedLotId = audit.items[index].lot_id;
        toolSelect.value = selectedToolId;
        lotSelect.value = selectedLotId;
        loadBoard().catch(handleLoadError);
      });
    });

    await loadFocusedPanels();
  }

  function handleLoadError(error) {
    briefStatus.textContent = "ERROR";
    reviewHeadline.textContent = "Runtime surfaces unavailable";
    console.error(error);
  }

  toolSelect.addEventListener("change", () => {
    selectedToolId = toolSelect.value;
    loadBoard().catch(handleLoadError);
  });

  lotSelect.addEventListener("change", () => {
    selectedLotId = lotSelect.value;
    loadBoard().catch(handleLoadError);
  });

  refreshBoardBtn.addEventListener("click", () => {
    loadBoard().catch(handleLoadError);
  });

  recoveryModeSelect.addEventListener("change", () => {
    selectedRecoveryMode = recoveryModeSelect.value;
    loadBoard().catch(handleLoadError);
  });

  focusSevereLotBtn.addEventListener("click", () => {
    if (latestLots.length === 0) {
      loadBoard().catch(handleLoadError);
      return;
    }
    const severeLot = latestLots.reduce((best, item) =>
      item.yield_risk_score > best.yield_risk_score ? item : best
    );
    selectedRecoveryMode = "hold";
    recoveryModeSelect.value = selectedRecoveryMode;
    selectedLotId = severeLot.lot_id;
    selectedToolId = severeLot.tool_id;
    toolSelect.value = selectedToolId;
    lotSelect.value = selectedLotId;
    loadBoard().catch(handleLoadError);
  });

  copyReviewRouteBtn.addEventListener("click", async () => {
    const payload = [
      `recovery board -> /api/recovery-board?mode=${selectedRecoveryMode}`,
      `tool ownership -> /api/tool-ownership?tool_id=${selectedToolId}`,
      `release gate -> /api/release-gate?lot_id=${selectedLotId}`,
      `handoff signature -> ${latestSignatureId || "pending-signature"}`,
    ].join("\n");
    await copyTextValue(payload);
  });

  copySevereLotBtn.addEventListener("click", async () => {
    const severeLot = latestRecoveryBoard?.spotlight || (latestLots.length > 0
      ? latestLots.reduce((best, item) =>
          item.yield_risk_score > best.yield_risk_score ? item : best
        )
      : null);
    const payload = severeLot
      ? [
          `lot_id: ${severeLot.lot_id}`,
          `tool_id: ${severeLot.tool_id}`,
          `yield_risk_score: ${severeLot.yield_risk_score}`,
          `risk_bucket: ${severeLot.risk_bucket}`,
          `board_status: ${severeLot.board_status || "unknown"}`,
          `maintenance_owner: ${severeLot.maintenance_owner || "unknown"}`,
          `next_action: ${severeLot.next_action}`,
          `route: /api/recovery-board?mode=${selectedRecoveryMode}`,
          `route: /api/release-gate?lot_id=${severeLot.lot_id}`,
        ].join("\n")
      : "No severe lot is loaded yet.";
    await copyTextValue(payload);
  });

  copyShiftSnapshotBtn.addEventListener("click", async () => {
    const lines = [
      "fab-ops shift snapshot",
      `Tool: ${selectedToolId}`,
      `Lot: ${selectedLotId}`,
      `Ownership lane: ${latestOwnership?.escalation_lane || "unknown"}`,
      `Primary operator: ${latestOwnership?.primary_operator || "unknown"}`,
      `Decision: ${latestGate?.decision || "pending"}`,
      `Next action: ${latestGate?.next_action || "pending"}`,
      `Yield risk: ${latestGate?.yield_risk_score ?? "unknown"}`,
      `Recovery lane: ${latestRecoveryBoard?.spotlight?.board_status || selectedRecoveryMode}`,
      `Recovery route: /api/recovery-board?mode=${selectedRecoveryMode}`,
      `Failed checks: ${latestGate?.failed_checks?.join(", ") || "none"}`,
      `Handoff: ${latestHandoff?.headline || "pending-handoff"}`,
      `Signature: ${latestSignaturePayload?.signature_id || latestSignatureId || "pending-signature"}`,
      `Signed by: ${latestSignaturePayload?.signed_by || "unknown"}`,
      "",
      "Focused routes",
      `/api/tool-ownership?tool_id=${selectedToolId}`,
      `/api/release-gate?lot_id=${selectedLotId}`,
      "/api/shift-handoff",
      "/api/shift-handoff/signature",
    ];
    await copyTextValue(lines.join("\n"));
  });

  loadBoard().catch(handleLoadError);
}

document.addEventListener("DOMContentLoaded", boot);
