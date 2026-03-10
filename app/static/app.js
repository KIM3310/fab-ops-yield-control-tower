function renderStatusCard(container, title, body, tone = "empty") {
  container.innerHTML = "";
  const node = document.createElement("article");
  node.className = `stack-item is-${tone}`;
  node.innerHTML = `
    <p class="stack-kicker">${tone.toUpperCase()}</p>
    <h3>${title}</h3>
    <p>${body}</p>
  `;
  container.appendChild(node);
}

function renderBulletList(container, items, fallbackText) {
  container.innerHTML = "";
  const listItems = items.length > 0 ? items : [fallbackText];
  listItems.forEach((item) => {
    const li = document.createElement("li");
    li.textContent = item;
    container.appendChild(li);
  });
}

function renderList(container, items, formatter, options = {}) {
  container.innerHTML = "";
  if (items.length === 0) {
    renderStatusCard(
      container,
      options.emptyTitle || "No records available",
      options.emptyMessage || "The control tower has nothing to show for this panel yet.",
      "empty"
    );
    return;
  }
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

function describeError(error) {
  if (error instanceof Error) {
    return error.message;
  }
  return "Request failed";
}

function populateSelect(select, items, valueKey, labelBuilder, selectedValue) {
  select.innerHTML = "";
  select.disabled = items.length === 0;
  if (items.length === 0) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "Unavailable";
    option.selected = true;
    select.appendChild(option);
    return;
  }
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
  const runtimeBanner = document.getElementById("runtime-banner");

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

  function setRuntimeBanner(state, message) {
    runtimeBanner.className = `runtime-banner is-${state}`;
    runtimeBanner.textContent = message;
  }

  function setRefreshBusy(isBusy) {
    refreshBoardBtn.disabled = isBusy;
    refreshBoardBtn.classList.toggle("is-busy", isBusy);
    refreshBoardBtn.textContent = isBusy
      ? "Refreshing Control Tower…"
      : "Refresh Control Tower";
  }

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
    const [ownershipResult, gateResult, signatureResult] = await Promise.allSettled([
      fetchJson(`/api/tool-ownership?tool_id=${encodeURIComponent(selectedToolId)}`),
      fetchJson(`/api/release-gate?lot_id=${encodeURIComponent(selectedLotId)}`),
      fetchJson("/api/shift-handoff/signature"),
    ]);
    const focusedFailures = [];

    if (ownershipResult.status === "fulfilled") {
      latestOwnership = ownershipResult.value.payload;
      renderList(toolOwnership, [ownershipResult.value.payload], (item) => `
        <p class="stack-kicker">${item.tool_id.toUpperCase()} · ${item.status.toUpperCase()}</p>
        <h3>${item.primary_operator}</h3>
        <p>${item.maintenance_owner} · ${item.escalation_lane}</p>
        <p class="stack-meta">Due ${item.due_by} · Ack ${item.ack_required ? "required" : "not required"}</p>
      `);
    } else {
      latestOwnership = null;
      focusedFailures.push("tool ownership");
      renderStatusCard(
        toolOwnership,
        "Tool ownership unavailable",
        describeError(ownershipResult.reason),
        "error"
      );
    }

    if (gateResult.status === "fulfilled") {
      latestGate = gateResult.value.payload;
      renderList(releaseGate, [gateResult.value.payload], (item) => `
        <p class="stack-kicker">${item.decision.toUpperCase()} · ${item.tool_id}</p>
        <h3>${item.lot_id}</h3>
        <p>${item.next_action}</p>
        <p class="stack-meta">Risk ${item.yield_risk_score} · ${item.failed_checks.join(" / ") || "no failed checks"}</p>
      `);
    } else {
      latestGate = null;
      focusedFailures.push("release gate");
      renderStatusCard(
        releaseGate,
        "Release gate unavailable",
        describeError(gateResult.reason),
        "error"
      );
    }

    if (signatureResult.status === "fulfilled") {
      latestSignaturePayload = signatureResult.value.payload;
      latestSignatureId = signatureResult.value.payload.signature_id || latestSignatureId;
    } else {
      latestSignaturePayload = null;
      focusedFailures.push("handoff signature");
    }

    reviewRoutePreview.innerHTML = "";
    [
      `tool ownership -> /api/tool-ownership?tool_id=${selectedToolId}`,
      `release gate -> /api/release-gate?lot_id=${selectedLotId}`,
      `handoff signature -> ${latestSignaturePayload?.signature_id || "pending-signature"}`,
      `next action -> ${latestGate?.next_action || "pending"}`,
    ].forEach((item) => {
      const li = document.createElement("li");
      li.textContent = item;
      reviewRoutePreview.appendChild(li);
    });

    return focusedFailures;
  }

  async function loadBoard() {
    setRefreshBusy(true);
    setRuntimeBanner("loading", "Refreshing control tower data…");

    const results = await Promise.allSettled([
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

    const [
      briefResult,
      reviewPackResult,
      alarmsResult,
      lotsResult,
      toolsResult,
      auditResult,
      handoffResult,
      signatureResult,
      replayResult,
      recoveryResult,
    ] = results;

    const degradedPanels = [];

    if (briefResult.status === "fulfilled") {
      briefStatus.textContent = briefResult.value.status.toUpperCase();
      criticalCount.textContent = String(
        briefResult.value.ops_snapshot.critical_alarm_count
      );
      severeCount.textContent = String(
        briefResult.value.ops_snapshot.severe_lot_count
      );
    } else {
      degradedPanels.push("runtime brief");
      briefStatus.textContent = "DEGRADED";
      criticalCount.textContent = "--";
      severeCount.textContent = "--";
    }

    if (replayResult.status === "fulfilled") {
      replayScore.textContent = `${replayResult.value.summary.score_pct}%`;
      renderList(
        replayList,
        replayResult.value.runs,
        (item) => `
          <p class="stack-kicker">${item.status.toUpperCase()}</p>
          <h3>${item.scenario}</h3>
          <p class="stack-meta">${item.checks} checks</p>
        `,
        {
          emptyTitle: "No replay runs yet",
          emptyMessage:
            "Run replay evals to populate the scenario summary panel.",
        }
      );
    } else {
      degradedPanels.push("replay summary");
      replayScore.textContent = "--";
      renderStatusCard(
        replayList,
        "Replay summary unavailable",
        describeError(replayResult.reason),
        "error"
      );
    }

    if (reviewPackResult.status === "fulfilled") {
      reviewHeadline.textContent = reviewPackResult.value.headline;
      renderBulletList(
        reviewPromises,
        [
          ...reviewPackResult.value.operator_promises,
          ...(reviewPackResult.value.two_minute_review || []).map(
            (item) => `2-minute: ${item}`
          ),
        ],
        "Operator promises are not available yet."
      );
      renderBulletList(
        reviewBoundary,
        [
          ...reviewPackResult.value.trust_boundary,
          ...((reviewPackResult.value.proof_assets || []).map(
            (item) => `proof: ${item.label} -> ${item.href}`
          )),
        ],
        "Trust boundary details are not available yet."
      );
    } else {
      degradedPanels.push("review pack");
      reviewHeadline.textContent = "Review pack temporarily unavailable";
      renderBulletList(
        reviewPromises,
        [],
        "Review pack data could not be loaded right now."
      );
      renderBulletList(
        reviewBoundary,
        [],
        "Trust boundary details are unavailable while the review pack is down."
      );
    }

    if (recoveryResult.status === "fulfilled") {
      latestRecoveryBoard = recoveryResult.value;
      renderList(
        recoveryBoard,
        recoveryResult.value.items,
        (item) => `
          <p class="stack-kicker">${item.board_status.toUpperCase()} · ${item.tool_id}</p>
          <h3>${item.lot_id}</h3>
          <p>${item.next_action}</p>
          <p class="stack-meta">Risk ${item.yield_risk_score} · ${item.maintenance_owner} · ${item.failed_checks.join(" / ") || "no failed checks"}</p>
        `,
        {
          emptyTitle: "Recovery board is clear",
          emptyMessage:
            "No hold/watch/ready lots match the current recovery mode.",
        }
      );
    } else {
      latestRecoveryBoard = null;
      degradedPanels.push("recovery board");
      renderStatusCard(
        recoveryBoard,
        "Recovery board unavailable",
        describeError(recoveryResult.reason),
        "error"
      );
    }

    const toolItems =
      toolsResult.status === "fulfilled" ? toolsResult.value.items || [] : [];
    const lotItems =
      lotsResult.status === "fulfilled" ? lotsResult.value.items || [] : [];
    latestLots = lotItems;
    if (toolsResult.status !== "fulfilled") {
      degradedPanels.push("tools");
      renderStatusCard(
        toolList,
        "Tool watchlist unavailable",
        describeError(toolsResult.reason),
        "error"
      );
    }
    if (lotsResult.status !== "fulfilled") {
      degradedPanels.push("lots");
      renderStatusCard(
        lotList,
        "Lots at risk unavailable",
        describeError(lotsResult.reason),
        "error"
      );
    }
    if (!toolItems.find((item) => item.tool_id === selectedToolId) && toolItems[0]) {
      selectedToolId = toolItems[0].tool_id;
    }
    if (!lotItems.find((item) => item.lot_id === selectedLotId) && lotItems[0]) {
      selectedLotId = lotItems[0].lot_id;
    }

    populateSelect(toolSelect, toolItems, "tool_id", (item) => `${item.tool_id} · ${item.status}`, selectedToolId);
    populateSelect(lotSelect, lotItems, "lot_id", (item) => `${item.lot_id} · risk ${item.yield_risk_score}`, selectedLotId);

    if (alarmsResult.status === "fulfilled") {
      renderList(alarmList, alarmsResult.value.items, (item) => `
        <p class="stack-kicker">${item.severity.toUpperCase()} · ${item.tool_id}</p>
        <h3>${item.category}</h3>
        <p>${item.symptom}</p>
        <p class="stack-meta">Lot ${item.lot_id} · SOP ${item.sop_ref}</p>
      `, {
        emptyTitle: "No active alarms",
        emptyMessage: "The alarm queue is currently clear.",
      });
    } else {
      degradedPanels.push("alarms");
      renderStatusCard(
        alarmList,
        "Alarm queue unavailable",
        describeError(alarmsResult.reason),
        "error"
      );
    }

    if (lotsResult.status === "fulfilled") {
      renderList(lotList, lotItems, (item) => `
        <p class="stack-kicker">${item.risk_bucket.toUpperCase()} · ${item.tool_id}</p>
        <h3>${item.lot_id}</h3>
        <p>${item.product_family}</p>
        <p class="stack-meta">Risk ${item.yield_risk_score} · ${item.next_action}</p>
      `, {
        emptyTitle: "No lots at risk",
        emptyMessage: "No lots currently match the selected risk conditions.",
      });
    }

    if (toolsResult.status === "fulfilled") {
      renderList(toolList, toolItems, (item) => `
        <p class="stack-kicker">${item.status.toUpperCase()} · ${item.line}</p>
        <h3>${item.tool_id}</h3>
        <p>Chamber ${item.chamber}</p>
        <p class="stack-meta">PM ${item.last_pm_hours}h · MTBF ${item.mtbf_risk}</p>
      `, {
        emptyTitle: "No tools available",
        emptyMessage: "The equipment feed did not return any tools.",
      });
    }

    if (auditResult.status === "fulfilled") {
      renderList(auditFeed, auditResult.value.items, (item) => `
        <p class="stack-kicker">${item.event.toUpperCase()} · ${item.tool_id}</p>
        <h3>${item.actor}</h3>
        <p>Lot ${item.lot_id}</p>
        <p class="stack-meta">${item.at}</p>
      `, {
        emptyTitle: "No recent audit events",
        emptyMessage: "Audit activity will appear here after the next shift event.",
      });
    } else {
      degradedPanels.push("audit feed");
      renderStatusCard(
        auditFeed,
        "Audit feed unavailable",
        describeError(auditResult.reason),
        "error"
      );
    }

    if (handoffResult.status === "fulfilled") {
      latestHandoff = handoffResult.value.payload;
      handoffHeadline.textContent = handoffResult.value.payload.headline;
      renderBulletList(
        handoffActions,
        handoffResult.value.payload.must_acknowledge,
        "No shift handoff actions are pending."
      );
    } else {
      latestHandoff = null;
      degradedPanels.push("shift handoff");
      handoffHeadline.textContent = "Shift handoff unavailable";
      renderBulletList(
        handoffActions,
        [],
        "Shift handoff actions are unavailable right now."
      );
    }

    if (signatureResult.status === "fulfilled") {
      latestSignaturePayload = signatureResult.value.payload;
      latestSignatureId = signatureResult.value.payload.signature_id || latestSignatureId;
      renderList(handoffSignature, [signatureResult.value.payload], (item) => `
        <p class="stack-kicker">${item.signature_contract.toUpperCase()}</p>
        <h3>${item.signature_id}</h3>
        <p>${item.signed_by} · ${item.release_channel}</p>
        <p class="stack-meta">Digest ${item.digest_preview}</p>
      `);
    } else {
      latestSignaturePayload = null;
      degradedPanels.push("handoff signature");
      renderStatusCard(
        handoffSignature,
        "Handoff signature unavailable",
        describeError(signatureResult.reason),
        "error"
      );
    }

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
        auditResult.status === "fulfilled"
          && auditResult.value.items[index]?.tool_id === selectedToolId
          && auditResult.value.items[index]?.lot_id === selectedLotId
      );
      node.addEventListener("click", () => {
        if (auditResult.status !== "fulfilled") {
          return;
        }
        selectedToolId = auditResult.value.items[index].tool_id;
        selectedLotId = auditResult.value.items[index].lot_id;
        toolSelect.value = selectedToolId;
        lotSelect.value = selectedLotId;
        loadBoard().catch(handleLoadError);
      });
    });

    const focusedFailures = await loadFocusedPanels();
    if (focusedFailures.length > 0) {
      degradedPanels.push(...focusedFailures);
    }

    if (degradedPanels.length > 0) {
      setRuntimeBanner(
        "degraded",
        `Degraded mode: ${degradedPanels.join(", ")} temporarily unavailable. Remaining panels stay live.`
      );
    } else {
      setRuntimeBanner("ok", "All runtime surfaces are live.");
    }

    setRefreshBusy(false);
  }

  function handleLoadError(error) {
    briefStatus.textContent = "ERROR";
    reviewHeadline.textContent = "Runtime surfaces unavailable";
    setRuntimeBanner(
      "error",
      `Control tower unavailable: ${describeError(error)}`
    );
    setRefreshBusy(false);
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
