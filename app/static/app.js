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

const RICH_TEXT_TAGS = new Set(["strong", "code"]);

function renderRichBulletList(container, items, fallbackText) {
  container.textContent = "";
  const listItems = items.length > 0 ? items : [[fallbackText]];
  listItems.forEach((segments) => {
    const li = document.createElement("li");
    segments.forEach((segment) => {
      if (typeof segment === "string") {
        li.appendChild(document.createTextNode(segment));
        return;
      }

      const tagName = RICH_TEXT_TAGS.has(segment.tag) ? segment.tag : "span";
      const node = document.createElement(tagName);
      node.textContent = String(segment.text ?? "");
      li.appendChild(node);
    });
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

const RECORDED_FAB = {
  brief: {
    status: "recorded",
    ops_snapshot: {
      critical_alarm_count: 2,
      severe_lot_count: 1,
    },
  },
  replay: {
    status: "unavailable",
    message: "Live replay API unavailable; no executed replay result is available as evidence.",
  },
  architecturePack: {
    headline: "Shift review pack for synthetic risk, recovery, and handoff status.",
    operator_promises: [
      "Alarms, lots, tools, and handoff stay in one operator view.",
      "Recovery what-if and release-gate decisions remain tied to the same lot context.",
    ],
    two_minute_architecture: [
      "Focus the severe lot first.",
      "Compare recovery what-if against the release gate before discussing readiness.",
    ],
    trust_boundary: [
      "Recorded mode shows workflow proof, not live fab telemetry freshness.",
    ],
    proof_assets: [
      { label: "Recovery Board", href: "/api/fab-ops/recovery-board?mode=hold" },
      { label: "Release Gate", href: "/api/fab-ops/release-gate?lot_id=LOT-8812" },
    ],
  },
  recoveryBoard: {
    items: [
      {
        board_status: "hold",
        tool_id: "ETCH-04",
        lot_id: "LOT-8812",
        next_action: "Finish chamber maintenance, then rerun the release gate.",
        simulated_yield_risk_score: 87,
        maintenance_owner: "team-park",
        failed_checks: ["maintenance-open", "signature-pending"],
      },
      {
        board_status: "watch",
        tool_id: "CMP-08",
        lot_id: "LOT-7741",
        next_action: "Keep on watch until the next replay checkpoint clears.",
        simulated_yield_risk_score: 54,
        maintenance_owner: "team-choi",
        failed_checks: ["watch-window-open"],
      },
    ],
    spotlight: {
      lot_id: "LOT-8812",
      tool_id: "ETCH-04",
      simulated_yield_risk_score: 87,
      risk_bucket: "hold",
      board_status: "hold",
      maintenance_owner: "team-park",
      next_action: "Finish chamber maintenance, then rerun the release gate.",
    },
  },
  recoveryWhatIf: {
    lot_id: "LOT-8812",
    baseline: { decision: "hold" },
    simulated: { decision: "watch" },
    delta: {
      release_eta_minutes: 48,
      risk_score_reduction: 12,
      maintenance_clearance: true,
    },
  },
  alarms: {
    items: [
      { severity: "critical", tool_id: "ETCH-04", category: "RF drift", symptom: "Synthetic drift scenario on chamber 2", lot_id: "LOT-8812", sop_ref: "ETCH-RF-12" },
    ],
  },
  lots: {
    items: [
      { risk_bucket: "hold", tool_id: "ETCH-04", lot_id: "LOT-8812", product_family: "FICTIONAL_DRAM_ALPHA", simulated_yield_risk_score: 87, next_action: "Complete maintenance then rerun gate" },
      { risk_bucket: "watch", tool_id: "CMP-08", lot_id: "LOT-7741", product_family: "FICTIONAL_NAND_BETA", simulated_yield_risk_score: 54, next_action: "Watch next replay checkpoint" },
    ],
  },
  tools: {
    items: [
      { status: "degraded", line: "L1", tool_id: "ETCH-04", chamber: "C2", last_pm_hours: 41, mtbf_risk: "high" },
      { status: "watch", line: "L3", tool_id: "CMP-08", chamber: "C1", last_pm_hours: 18, mtbf_risk: "medium" },
    ],
  },
  audit: {
    items: [
      { event: "maintenance-opened", tool_id: "ETCH-04", actor: "team-park", lot_id: "LOT-8812", at: "2026-03-12T05:22:00Z" },
      { event: "review-checkpoint-recorded", tool_id: "CMP-08", actor: "ops-shift-b", lot_id: "LOT-7741", at: "2026-03-12T04:58:00Z" },
    ],
  },
  handoff: {
    payload: {
      headline: "Finish ETCH-04 maintenance, then recheck LOT-8812 before the next shift handoff.",
      must_acknowledge: [
        "ETCH-04 is still the top blocker for the next release window.",
        "LOT-8812 stays on hold until maintenance closes and live executed replay evidence is reviewed.",
      ],
    },
  },
  signature: {
    payload: {
      signature_contract: "fab-handoff-v1",
      signature_id: "sig-fab-8812",
      generated_by: "fab-ops-demo-hmac-service",
      artifact_channel: "shift-review",
      signature_purpose: "Integrity evidence only; human approval not recorded.",
      human_approval_status: "not_recorded",
      digest_preview: "sha256:fab8812",
    },
  },
  focused: {
    ownership: {
      payload: {
        tool_id: "ETCH-04",
        primary_operator: "operator-han",
        maintenance_owner: "team-park",
        escalation_lane: "yield-escalation",
        due_by: "2026-03-12T18:00:00Z",
        ack_required: true,
      },
    },
    gate: {
      payload: {
        lot_id: "LOT-8812",
        tool_id: "ETCH-04",
        decision: "hold",
        next_action: "Finish maintenance and rerun the replay bundle before release.",
        simulated_yield_risk_score: 87,
        failed_checks: ["maintenance-open", "signature-pending"],
      },
    },
  },
};

const REVIEW_LENSES = {
  operator: {
    headline: "Shift lead lens",
    summary: "Start with the severe lot, then compare recovery and release posture before copying a handoff.",
    cards: [
      ["01 · Severe lot", "Focus the top blocker before you explain any other metric."],
      ["02 · Recovery", "Use recovery what-if and release gate together so the next action is concrete."],
      ["03 · Shift handoff", "Copy the shift snapshot only after the blocker and handoff proof match."],
    ],
    actions: ["Focus Severe Lot", "Copy Shift Snapshot", "Copy Focused Route"],
  },
  architecture: {
    headline: "Audit lens",
    summary: "Keep the review pack, trust boundary, and replay evidence together so the control tower stays auditable.",
    cards: [
      ["01 · Review pack", "Read operator promises and trust boundary before touching the severe lot."],
      ["02 · Focused route", "Connect recovery board, release gate, and signature in one path."],
      ["03 · Replay", "Use replay summary as the confidence layer after the route is clear."],
    ],
    actions: ["Copy Focused Route", "Copy Severe Lot", "Refresh Control Tower"],
  },
  executive: {
    headline: "Ops director lens",
    summary: "Lead with blocker, ETA delta, and handoff readiness so the business story reads in under a minute.",
    cards: [
      ["01 · Blocker", "Use the severe lot as the headline instead of the whole dashboard."],
      ["02 · ETA", "Explain recovery what-if as a release timing decision, not just a technical tweak."],
      ["03 · Handoff", "End with the shift snapshot because that is the operational commitment."],
    ],
    actions: ["Copy Shift Snapshot", "Copy Severe Lot", "Focus Severe Lot"],
  },
};

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
  const reviewHeadline = document.getElementById("architecture-headline");
  const reviewPromises = document.getElementById("architecture-promises");
  const reviewBoundary = document.getElementById("architecture-boundary");
  const reviewRoutePreview = document.getElementById("architecture-route-preview");
  const storylineSummary = document.getElementById("storyline-summary");
  const storylineRoute = document.getElementById("storyline-route");
  const alarmList = document.getElementById("alarm-list");
  const lotList = document.getElementById("lot-list");
  const toolList = document.getElementById("tool-list");
  const toolOwnership = document.getElementById("tool-ownership");
  const releaseGate = document.getElementById("release-gate");
  const recoveryWhatIf = document.getElementById("recovery-what-if");
  const auditFeed = document.getElementById("audit-feed");
  const recoveryBoard = document.getElementById("recovery-board");
  const recoveryModeSelect = document.getElementById("recovery-mode-select");
  const handoffHeadline = document.getElementById("handoff-headline");
  const handoffActions = document.getElementById("handoff-actions");
  const handoffSignature = document.getElementById("handoff-signature");
  const continuityOwnerLane = document.getElementById("continuity-owner-lane");
  const continuityProofFreshness = document.getElementById("continuity-proof-freshness");
  const continuitySignature = document.getElementById("continuity-signature");
  const continuityGuard = document.getElementById("continuity-guard");
  const continuityBlockers = document.getElementById("continuity-blockers");
  const replayList = document.getElementById("replay-list");
  const spcControlPlan = document.getElementById("spc-control-plan");
  const spcDisposition = document.getElementById("spc-disposition");
  const spcFlowAuthority = document.getElementById("spc-flow-authority");
  const toolSelect = document.getElementById("tool-select");
  const lotSelect = document.getElementById("lot-select");
  const focusSevereLotBtn = document.getElementById("focus-severe-lot-btn");
  const copyArchitectureRouteBtn = document.getElementById("copy-architecture-route-btn");
  const copySevereLotBtn = document.getElementById("copy-severe-lot-btn");
  const copyShiftSnapshotBtn = document.getElementById("copy-shift-snapshot-btn");
  const refreshBoardBtn = document.getElementById("refresh-board-btn");
  const runtimeBanner = document.getElementById("runtime-banner");
  const lensHeadline = document.getElementById("lens-headline");
  const lensSummary = document.getElementById("lens-summary");
  const lensGrid = document.getElementById("lens-grid");
  const lensOperatorBtn = document.getElementById("lens-operator-btn");
  const lensArchitectureBtn = document.getElementById("lens-architecture-btn");
  const lensExecutiveBtn = document.getElementById("lens-executive-btn");
  const lensPrimaryBtn = document.getElementById("lens-primary-btn");
  const lensSecondaryBtn = document.getElementById("lens-secondary-btn");
  const lensTertiaryBtn = document.getElementById("lens-tertiary-btn");

  let selectedToolId = "";
  let selectedLotId = "";
  let latestLots = [];
  let latestSignatureId = "";
  let latestOwnership = null;
  let latestGate = null;
  let latestHandoff = null;
  let latestSignaturePayload = null;
  let latestRecoveryBoard = null;
  let latestRecoveryWhatIf = null;
  let selectedRecoveryMode = "all";
  let currentLens = "operator";


  function formatIsoStamp(value) {
    if (!value) return 'pending';
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return String(value);
    return parsed.toISOString().replace('.000Z', 'Z');
  }

  function renderContinuityCheckpoint() {
    const signatureId = latestSignaturePayload?.signature_id || latestSignatureId || 'pending-signature';
    const signedAt = latestSignaturePayload?.signed_at || latestHandoff?.generated_at || null;
    const owner = latestOwnership?.primary_operator || latestOwnership?.maintenance_owner || 'pending owner';
    const escalationLane = latestOwnership?.escalation_lane || 'pending escalation lane';
    const gateDecision = latestGate?.decision || latestGate?.release_decision || 'pending gate';
    const blocker = latestGate?.blocking_reason || latestGate?.headline || 'release evidence still loading';
    const failedChecks = Array.isArray(latestGate?.failed_checks) ? latestGate.failed_checks : [];
    const ackCount = Array.isArray(latestHandoff?.must_acknowledge) ? latestHandoff.must_acknowledge.length : 0;

    if (continuityOwnerLane) continuityOwnerLane.textContent = `${owner} owns ${escalationLane} while ${blocker}.`;
    if (continuityProofFreshness) continuityProofFreshness.textContent = `Integrity envelope ${formatIsoStamp(signedAt)} · gate ${gateDecision} · ${ackCount} ack items.`;
    if (continuitySignature) continuitySignature.textContent = `Signature ${signatureId} is integrity evidence only; human release approval remains separate.`;
    if (continuityGuard) continuityGuard.textContent = gateDecision === 'release'
      ? 'Integrity evidence is aligned. Human release approval remains a separate governed decision.'
      : 'Shift continuity stays blocked until owner, release gate, and signature line up.';
    if (continuityBlockers) continuityBlockers.textContent = failedChecks.length
      ? `${failedChecks.length} gate blockers stay attached to the focused lot: ${failedChecks.join(', ')}.`
      : 'Gate blockers cleared in the fixture. Keep the focused evidence attached; no human approval is recorded.';
  }

  function setRuntimeBanner(state, message) {
    runtimeBanner.className = `runtime-banner is-${state}`;
    const spinner = state === "loading" ? '<span class="loading-spinner" aria-hidden="true"></span> ' : '';
    runtimeBanner.innerHTML = spinner + message;
  }

  function setRefreshBusy(isBusy) {
    refreshBoardBtn.disabled = isBusy;
    refreshBoardBtn.classList.toggle("is-busy", isBusy);
    refreshBoardBtn.textContent = isBusy
      ? "Refreshing Control Tower…"
      : "Refresh Control Tower";
  }

  function renderLensPanel() {
    const config = REVIEW_LENSES[currentLens] || REVIEW_LENSES.operator;
    lensHeadline.textContent = config.headline;
    lensSummary.textContent = config.summary;
    lensGrid.innerHTML = config.cards
      .map(
        ([title, body]) => `
          <article class="panel">
            <h2>${title}</h2>
            <p class="stack-meta">${body}</p>
          </article>`,
      )
      .join("");
    [lensOperatorBtn, lensArchitectureBtn, lensExecutiveBtn].forEach((btn) => btn?.classList.remove("is-active"));
    if (currentLens === "operator") lensOperatorBtn?.classList.add("is-active");
    if (currentLens === "architecture") lensArchitectureBtn?.classList.add("is-active");
    if (currentLens === "executive") lensExecutiveBtn?.classList.add("is-active");
    lensPrimaryBtn.textContent = config.actions[0];
    lensSecondaryBtn.textContent = config.actions[1];
    lensTertiaryBtn.textContent = config.actions[2];
  }

  function runLensAction(action) {
    if (action === "Focus Severe Lot") return focusSevereLotBtn.click();
    if (action === "Copy Shift Snapshot") return copyShiftSnapshotBtn.click();
    if (action === "Copy Focused Route") return copyArchitectureRouteBtn.click();
    if (action === "Copy Severe Lot") return copySevereLotBtn.click();
    if (action === "Refresh Control Tower") return refreshBoardBtn.click();
  }

  function renderStoryline() {
    const spotlight = latestRecoveryBoard?.spotlight || null;
    const storyLotId = selectedLotId || spotlight?.lot_id || latestGate?.lot_id || "pending-lot";
    const boardStatus = spotlight?.board_status || spotlight?.risk_bucket || selectedRecoveryMode;
    const simulatedDecision = latestRecoveryWhatIf?.simulated?.decision || "pending";
    const etaGain = latestRecoveryWhatIf?.delta?.release_eta_minutes;
    const riskDelta = latestRecoveryWhatIf?.delta?.risk_score_reduction;
    const maintenanceState = latestRecoveryWhatIf?.delta?.maintenance_clearance ? "complete" : "still open";
    const signatureId = latestSignaturePayload?.signature_id || latestSignatureId || "pending-signature";

    renderRichBulletList(
      storylineSummary,
      [
        [
          { tag: "strong", text: storyLotId },
          " is the live lot-risk anchor, currently reading as ",
          { tag: "strong", text: boardStatus },
          " until the release gate changes.",
        ],
        [
          { tag: "strong", text: "Recovery what-if" },
          " shifts the posture toward ",
          { tag: "strong", text: simulatedDecision },
          typeof etaGain === "number" ? ` with ${etaGain} minutes of ETA recovery` : "",
          typeof riskDelta === "number" ? ` and ${riskDelta} risk-score reduction` : "",
          ".",
        ],
        [
          { tag: "strong", text: "Operator-proof handoff" },
          " stays honest: maintenance is ",
          { tag: "strong", text: maintenanceState },
          ", gate evidence remains required, and the next shift should see signature ",
          { tag: "strong", text: signatureId },
          " before anyone talks about release confidence.",
        ],
      ],
      "Storyline details load after the focused lot is available."
    );

    renderContinuityCheckpoint();

    renderRichBulletList(
      storylineRoute,
      [
        [
          { tag: "strong", text: "1." },
          " Recovery board -> ",
          { tag: "code", text: `/api/fab-ops/recovery-board?mode=${selectedRecoveryMode}` },
          " keeps the blocker visible first.",
        ],
        [
          { tag: "strong", text: "2." },
          " Recovery what-if -> ",
          {
            tag: "code",
            text: `/api/fab-ops/recovery-what-if?lot_id=${storyLotId}&yield_gain=0.25&maintenance_complete=true`,
          },
          " shows the bounded improvement claim instead of implying recovery.",
        ],
        [
          { tag: "strong", text: "3." },
          " Release gate + ownership -> ",
          { tag: "code", text: `/api/fab-ops/release-gate?lot_id=${storyLotId}` },
          " and ",
          { tag: "code", text: `/api/fab-ops/tool-ownership?tool_id=${selectedToolId || "pending-tool"}` },
          " prove who owns the next move.",
        ],
        [
          { tag: "strong", text: "4." },
          " Shift handoff -> ",
          { tag: "code", text: "/api/fab-ops/shift-handoff" },
          " plus ",
          { tag: "code", text: "/api/fab-ops/shift-handoff/signature" },
          " closes the story with next-shift continuity, not a cosmetic dashboard ending.",
        ],
      ],
      "Reviewer route details load after the focused lot is available."
    );
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
      fetchJson(`/api/fab-ops/tool-ownership?tool_id=${encodeURIComponent(selectedToolId)}`),
      fetchJson(`/api/fab-ops/release-gate?lot_id=${encodeURIComponent(selectedLotId)}`),
      fetchJson("/api/fab-ops/shift-handoff/signature"),
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
        <p class="stack-meta">Simulated fixture risk ${item.simulated_yield_risk_score} · ${item.failed_checks.join(" / ") || "no failed checks"}</p>
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
      `tool ownership -> /api/fab-ops/tool-ownership?tool_id=${selectedToolId}`,
      `release gate -> /api/fab-ops/release-gate?lot_id=${selectedLotId}`,
      `handoff signature -> ${latestSignaturePayload?.signature_id || "pending-signature"}`,
      `next action -> ${latestGate?.next_action || "pending"}`,
    ].forEach((item) => {
      const li = document.createElement("li");
      li.textContent = item;
      reviewRoutePreview.appendChild(li);
    });
    renderStoryline();

    return focusedFailures;
  }

  async function loadBoard() {
    setRefreshBusy(true);
    setRuntimeBanner("loading", "Refreshing control tower data…");

    const results = await Promise.allSettled([
      fetchJson("/api/fab-ops/runtime/brief"),
      fetchJson("/api/fab-ops/architecture-pack"),
      fetchJson("/api/fab-ops/alarms"),
      fetchJson("/api/fab-ops/lots/at-risk"),
      fetchJson("/api/fab-ops/tools"),
      fetchJson("/api/fab-ops/audit/feed"),
      fetchJson("/api/fab-ops/shift-handoff"),
      fetchJson("/api/fab-ops/shift-handoff/signature"),
      fetchJson("/api/fab-ops/v1/evals/replays"),
      fetchJson("/api/fab-ops/v1/control-plan"),
      fetchJson(`/api/fab-ops/v1/lots/${encodeURIComponent(selectedLotId || "lot-8812")}/disposition`),
      fetchJson(`/api/fab-ops/recovery-board?mode=${encodeURIComponent(selectedRecoveryMode)}`),
      fetchJson(`/api/fab-ops/recovery-what-if?lot_id=${encodeURIComponent(selectedLotId || "lot-8812")}&yield_gain=0.25&maintenance_complete=true`),
    ]);

    const [
      briefResult,
      architecturePackResult,
      alarmsResult,
      lotsResult,
      toolsResult,
      auditResult,
      handoffResult,
      signatureResult,
      replayResult,
      controlPlanResult,
      dispositionResult,
      recoveryResult,
      recoveryWhatIfResult,
    ] = results;

    const allFailed = results.every((item) => item.status === "rejected");
    if (allFailed) {
      briefStatus.textContent = RECORDED_FAB.brief.status.toUpperCase();
      criticalCount.textContent = String(RECORDED_FAB.brief.ops_snapshot.critical_alarm_count);
      severeCount.textContent = String(RECORDED_FAB.brief.ops_snapshot.severe_lot_count);
      replayScore.textContent = "--";
      reviewHeadline.textContent = RECORDED_FAB.architecturePack.headline;
      renderBulletList(
        reviewPromises,
        [
          ...RECORDED_FAB.architecturePack.operator_promises,
          ...RECORDED_FAB.architecturePack.two_minute_architecture.map((item) => `2-minute: ${item}`),
        ],
        "Operator promises are not available yet."
      );
      renderBulletList(
        reviewBoundary,
        [
          ...RECORDED_FAB.architecturePack.trust_boundary,
          ...RECORDED_FAB.architecturePack.proof_assets.map((item) => `proof: ${item.label} -> ${item.href}`),
        ],
        "Trust boundary details are not available yet."
      );
      renderStatusCard(
        replayList,
        "Executed replay evidence unavailable",
        RECORDED_FAB.replay.message,
        "error"
      );
      latestRecoveryBoard = RECORDED_FAB.recoveryBoard;
      latestRecoveryWhatIf = RECORDED_FAB.recoveryWhatIf;
      latestLots = RECORDED_FAB.lots.items;
      latestHandoff = RECORDED_FAB.handoff.payload;
      latestSignaturePayload = RECORDED_FAB.signature.payload;
      latestSignatureId = RECORDED_FAB.signature.payload.signature_id;
      latestOwnership = RECORDED_FAB.focused.ownership.payload;
      latestGate = RECORDED_FAB.focused.gate.payload;
      selectedToolId = RECORDED_FAB.focused.ownership.payload.tool_id;
      selectedLotId = RECORDED_FAB.focused.gate.payload.lot_id;
      populateSelect(toolSelect, RECORDED_FAB.tools.items, "tool_id", (item) => `${item.tool_id} · ${item.status}`, selectedToolId);
      populateSelect(lotSelect, RECORDED_FAB.lots.items, "lot_id", (item) => `${item.lot_id} · simulated fixture risk ${item.simulated_yield_risk_score}`, selectedLotId);
      renderList(recoveryBoard, RECORDED_FAB.recoveryBoard.items, (item) => `
        <p class="stack-kicker">${item.board_status.toUpperCase()} · ${item.tool_id}</p>
        <h3>${item.lot_id}</h3>
        <p>${item.next_action}</p>
        <p class="stack-meta">Simulated fixture risk ${item.simulated_yield_risk_score} · ${item.maintenance_owner} · ${item.failed_checks.join(" / ")}</p>
      `);
      renderList(recoveryWhatIf, [RECORDED_FAB.recoveryWhatIf], (item) => `
        <p class="stack-kicker">${item.simulated.decision.toUpperCase()} · eta gain ${item.delta.release_eta_minutes}m</p>
        <h3>${item.lot_id}</h3>
        <p>Baseline ${item.baseline.decision} -> Simulated ${item.simulated.decision}</p>
        <p class="stack-meta">Simulated risk delta ${item.delta.risk_score_reduction} · maintenance ${item.delta.maintenance_clearance ? "complete" : "pending"}</p>
      `);
      renderList(alarmList, RECORDED_FAB.alarms.items, (item) => `
        <p class="stack-kicker">${item.severity.toUpperCase()} · ${item.tool_id}</p>
        <h3>${item.category}</h3>
        <p>${item.symptom}</p>
        <p class="stack-meta">Lot ${item.lot_id} · SOP ${item.sop_ref}</p>
      `);
      renderList(lotList, RECORDED_FAB.lots.items, (item) => `
        <p class="stack-kicker">${item.risk_bucket.toUpperCase()} · ${item.tool_id}</p>
        <h3>${item.lot_id}</h3>
        <p>${item.product_family}</p>
        <p class="stack-meta">Simulated fixture risk ${item.simulated_yield_risk_score} · ${item.next_action}</p>
      `);
      renderList(toolList, RECORDED_FAB.tools.items, (item) => `
        <p class="stack-kicker">${item.status.toUpperCase()} · ${item.line}</p>
        <h3>${item.tool_id}</h3>
        <p>Chamber ${item.chamber}</p>
        <p class="stack-meta">PM ${item.last_pm_hours}h · MTBF ${item.mtbf_risk}</p>
      `);
      renderList(auditFeed, RECORDED_FAB.audit.items, (item) => `
        <p class="stack-kicker">${item.event.toUpperCase()} · ${item.tool_id}</p>
        <h3>${item.actor}</h3>
        <p>Lot ${item.lot_id}</p>
        <p class="stack-meta">${item.at}</p>
      `);
      handoffHeadline.textContent = RECORDED_FAB.handoff.payload.headline;
      renderBulletList(handoffActions, RECORDED_FAB.handoff.payload.must_acknowledge, "No shift handoff actions are pending.");
      renderList(handoffSignature, [RECORDED_FAB.signature.payload], (item) => `
        <p class="stack-kicker">${item.signature_contract.toUpperCase()}</p>
        <h3>${item.signature_id}</h3>
        <p>${item.generated_by} · ${item.artifact_channel}</p>
        <p class="stack-meta">Digest ${item.digest_preview}</p>
      `);
      renderStatusCard(
        spcControlPlan,
        "Recorded synthetic control plan",
        "Live API unavailable; packaged recorded mode does not claim an executed SPC result.",
        "empty"
      );
      renderStatusCard(
        spcDisposition,
        "Recorded advisory posture",
        "No live disposition was executed. Human approval remains not recorded.",
        "empty"
      );
      renderStatusCard(
        spcFlowAuthority,
        "Synthetic flow context",
        "Q-time, TAT, and routing require the live packaged fixture endpoint.",
        "empty"
      );
      reviewRoutePreview.innerHTML = "";
      [
        `recovery board -> /api/fab-ops/recovery-board?mode=hold`,
        `tool ownership -> /api/fab-ops/tool-ownership?tool_id=${selectedToolId}`,
        `release gate -> /api/fab-ops/release-gate?lot_id=${selectedLotId}`,
        `handoff signature -> ${latestSignatureId}`,
      ].forEach((item) => {
        const li = document.createElement("li");
        li.textContent = item;
        reviewRoutePreview.appendChild(li);
      });
      renderList(toolOwnership, [RECORDED_FAB.focused.ownership.payload], (item) => `
        <p class="stack-kicker">${item.tool_id}</p>
        <h3>${item.primary_operator}</h3>
        <p>${item.maintenance_owner} · ${item.escalation_lane}</p>
        <p class="stack-meta">Due ${item.due_by} · Ack ${item.ack_required ? "required" : "not required"}</p>
      `);
      renderList(releaseGate, [RECORDED_FAB.focused.gate.payload], (item) => `
        <p class="stack-kicker">${item.decision.toUpperCase()} · ${item.tool_id}</p>
        <h3>${item.lot_id}</h3>
        <p>${item.next_action}</p>
        <p class="stack-meta">Simulated fixture risk ${item.simulated_yield_risk_score} · ${item.failed_checks.join(" / ")}</p>
      `);
      renderStoryline();
        setRuntimeBanner("ok", "Recorded technical review loaded locally. Focus the severe lot first, then compare recovery and release posture.");
      setRefreshBusy(false);
      return;
    }

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
          <h3>${item.case_id || item.scenario}</h3>
          <p>${item.description || `Actual: ${item.actual?.recommendation || item.actual?.unique_rule_ids?.join(", ") || "no rule signal"}`}</p>
          <p class="stack-meta">${item.assertions ? `${item.assertions.filter((assertion) => assertion.passed).length}/${item.assertions.length} assertions passed` : `${item.checks} recorded checks`}</p>
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

    if (controlPlanResult.status === "fulfilled") {
      const plan = controlPlanResult.value;
      renderList(spcControlPlan, [plan], (item) => `
        <p class="stack-kicker">${item.api_version.toUpperCase()} · ${item.dataset.data_classification.toUpperCase()}</p>
        <h3>${item.control_plan.policy_id} · ${item.control_plan.revision}</h3>
        <p>${item.control_plan.chart}</p>
        <p class="stack-meta">${item.control_plan.rules.length} rules · fixture ${item.dataset.fixture_sha256.slice(0, 12)}… · measured yield: no</p>
      `);
    } else {
      degradedPanels.push("SPC control plan");
      renderStatusCard(spcControlPlan, "Control plan unavailable", describeError(controlPlanResult.reason), "error");
    }

    if (dispositionResult.status === "fulfilled") {
      const disposition = dispositionResult.value;
      const flow = disposition.flow_indicators;
      renderList(spcDisposition, [disposition], (item) => `
        <p class="stack-kicker">${item.gate.recommendation} · ADVISORY ONLY</p>
        <h3>${item.lot.lot_id} · ${item.lot.tool_id}</h3>
        <p>Rules ${item.spc.unique_rule_ids.join(", ") || "none"} · ${item.gate.hard_blockers.length} containment blocker(s)</p>
        <p class="stack-meta">${item.lineage.data_classification} · measured yield: no · material moved: ${item.gate.material_state_changed ? "yes" : "no"}</p>
      `);
      renderList(spcFlowAuthority, [disposition], () => `
        <p class="stack-kicker">HUMAN APPROVAL ${disposition.gate.human_approval_status.toUpperCase()}</p>
        <h3>Q-time ${flow.q_time.status} · TAT ${flow.tat.status}</h3>
        <p>${flow.routing.route_id}: step ${flow.routing.current_step} → ${flow.routing.next_step} (${flow.routing.route_state})</p>
        <p class="stack-meta">${flow.q_time.elapsed_minutes} / ${flow.q_time.limit_minutes} min q-time · route changed: no</p>
      `);
    } else {
      degradedPanels.push("fixture disposition");
      renderStatusCard(spcDisposition, "Disposition unavailable", describeError(dispositionResult.reason), "error");
      renderStatusCard(spcFlowAuthority, "Flow indicators unavailable", "Disposition evidence did not load.", "error");
    }

    if (architecturePackResult.status === "fulfilled") {
      reviewHeadline.textContent = architecturePackResult.value.headline;
      renderBulletList(
        reviewPromises,
        [
          ...architecturePackResult.value.operator_promises,
          ...(architecturePackResult.value.two_minute_architecture || []).map(
            (item) => `2-minute: ${item}`
          ),
        ],
        "Operator promises are not available yet."
      );
      renderBulletList(
        reviewBoundary,
        [
          ...architecturePackResult.value.trust_boundary,
          ...((architecturePackResult.value.proof_assets || []).map(
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
          <p class="stack-meta">Simulated fixture risk ${item.simulated_yield_risk_score} · ${item.maintenance_owner} · ${item.failed_checks.join(" / ") || "no failed checks"}</p>
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

    if (recoveryWhatIfResult.status === "fulfilled") {
      latestRecoveryWhatIf = recoveryWhatIfResult.value;
      renderList(
        recoveryWhatIf,
        [recoveryWhatIfResult.value],
        (item) => `
          <p class="stack-kicker">${item.simulated.decision.toUpperCase()} · eta gain ${item.delta.release_eta_minutes}m</p>
          <h3>${item.lot_id}</h3>
          <p>Baseline ${item.baseline.decision} -> Simulated ${item.simulated.decision}</p>
          <p class="stack-meta">Simulated risk delta ${item.delta.risk_score_reduction} · maintenance ${item.delta.maintenance_clearance ? "complete" : "pending"}</p>
        `,
        {
          emptyTitle: "Recovery what-if unavailable",
          emptyMessage: "No simulation is available for the selected lot.",
        }
      );
    } else {
      latestRecoveryWhatIf = null;
      renderStatusCard(
        recoveryWhatIf,
        "Recovery what-if unavailable",
        describeError(recoveryWhatIfResult.reason),
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
    populateSelect(lotSelect, lotItems, "lot_id", (item) => `${item.lot_id} · simulated fixture risk ${item.simulated_yield_risk_score}`, selectedLotId);

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
        <p class="stack-meta">Simulated fixture risk ${item.simulated_yield_risk_score} · ${item.next_action}</p>
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
        <p>${item.generated_by} · ${item.artifact_channel}</p>
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

    renderStoryline();
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
  lensOperatorBtn.addEventListener("click", () => {
    currentLens = "operator";
    renderLensPanel();
  });
  lensArchitectureBtn.addEventListener("click", () => {
    currentLens = "architecture";
    renderLensPanel();
  });
  lensExecutiveBtn.addEventListener("click", () => {
    currentLens = "executive";
    renderLensPanel();
  });
  lensPrimaryBtn.addEventListener("click", () => runLensAction(lensPrimaryBtn.textContent));
  lensSecondaryBtn.addEventListener("click", () => runLensAction(lensSecondaryBtn.textContent));
  lensTertiaryBtn.addEventListener("click", () => runLensAction(lensTertiaryBtn.textContent));
  renderLensPanel();

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
      item.simulated_yield_risk_score > best.simulated_yield_risk_score ? item : best
    );
    selectedRecoveryMode = "hold";
    recoveryModeSelect.value = selectedRecoveryMode;
    selectedLotId = severeLot.lot_id;
    selectedToolId = severeLot.tool_id;
    toolSelect.value = selectedToolId;
    lotSelect.value = selectedLotId;
    loadBoard().catch(handleLoadError);
  });

  copyArchitectureRouteBtn.addEventListener("click", async () => {
    const payload = [
      `recovery board -> /api/fab-ops/recovery-board?mode=${selectedRecoveryMode}`,
      `tool ownership -> /api/fab-ops/tool-ownership?tool_id=${selectedToolId}`,
      `release gate -> /api/fab-ops/release-gate?lot_id=${selectedLotId}`,
      `handoff signature -> ${latestSignatureId || "pending-signature"}`,
    ].join("\n");
    await copyTextValue(payload);
  });

  copySevereLotBtn.addEventListener("click", async () => {
    const severeLot = latestRecoveryBoard?.spotlight || (latestLots.length > 0
      ? latestLots.reduce((best, item) =>
          item.simulated_yield_risk_score > best.simulated_yield_risk_score ? item : best
        )
      : null);
    const payload = severeLot
      ? [
          `lot_id: ${severeLot.lot_id}`,
          `tool_id: ${severeLot.tool_id}`,
          `simulated_yield_risk_score: ${severeLot.simulated_yield_risk_score}`,
          `risk_bucket: ${severeLot.risk_bucket}`,
          `board_status: ${severeLot.board_status || "unknown"}`,
          `maintenance_owner: ${severeLot.maintenance_owner || "unknown"}`,
          `next_action: ${severeLot.next_action}`,
          `route: /api/fab-ops/recovery-board?mode=${selectedRecoveryMode}`,
          `route: /api/fab-ops/release-gate?lot_id=${severeLot.lot_id}`,
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
      `Simulated fixture risk: ${latestGate?.simulated_yield_risk_score ?? "unknown"}`,
      `Recovery lane: ${latestRecoveryBoard?.spotlight?.board_status || selectedRecoveryMode}`,
      `Recovery route: /api/fab-ops/recovery-board?mode=${selectedRecoveryMode}`,
      `Failed checks: ${latestGate?.failed_checks?.join(", ") || "none"}`,
      `Handoff: ${latestHandoff?.headline || "pending-handoff"}`,
      `Signature: ${latestSignaturePayload?.signature_id || latestSignatureId || "pending-signature"}`,
      `Integrity envelope generated by: ${latestSignaturePayload?.generated_by || "unknown"}`,
      `Human approval: ${latestSignaturePayload?.human_approval_status || "not_recorded"}`,
      "",
      "Focused routes",
      `/api/fab-ops/tool-ownership?tool_id=${selectedToolId}`,
      `/api/fab-ops/release-gate?lot_id=${selectedLotId}`,
      "/api/fab-ops/shift-handoff",
      "/api/fab-ops/shift-handoff/signature",
    ];
    await copyTextValue(lines.join("\n"));
  });

  loadBoard().catch(handleLoadError);
}

document.addEventListener("DOMContentLoaded", boot);
