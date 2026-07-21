WORKBENCH_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Axiom Forge Workbench</title>
  <style>
    :root {
      color-scheme: light;
      font-family: Arial, sans-serif;
      --ink: #17202a;
      --muted: #637083;
      --line: #d6dde6;
      --panel: #f7f9fb;
      --accent: #0d766e;
      --danger: #b42318;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: #ffffff;
      color: var(--ink);
    }
    header {
      border-bottom: 1px solid var(--line);
      padding: 18px 28px;
    }
    h1 {
      font-size: 22px;
      line-height: 1.2;
      margin: 0;
      letter-spacing: 0;
    }
    main {
      display: grid;
      grid-template-columns: minmax(260px, 360px) minmax(0, 1fr);
      min-height: calc(100vh - 59px);
    }
    aside {
      border-right: 1px solid var(--line);
      padding: 24px 28px;
      background: var(--panel);
    }
    section {
      padding: 24px 32px 40px;
    }
    label {
      display: block;
      font-weight: 700;
      font-size: 13px;
      margin: 18px 0 7px;
    }
    input, textarea, select {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 6px;
      color: var(--ink);
      background: #ffffff;
      font: inherit;
      font-size: 14px;
    }
    input, select {
      min-height: 40px;
      padding: 8px 10px;
    }
    input[type="checkbox"] {
      width: auto;
      min-height: auto;
      margin: 0 8px 0 0;
    }
    textarea {
      min-height: 120px;
      padding: 10px;
      resize: vertical;
      font-family: Consolas, "Liberation Mono", monospace;
      line-height: 1.45;
    }
    button {
      margin-top: 14px;
      width: 100%;
      min-height: 40px;
      border: 0;
      border-radius: 6px;
      background: var(--accent);
      color: #ffffff;
      font-weight: 700;
      cursor: pointer;
    }
    button:disabled {
      cursor: progress;
      opacity: 0.65;
    }
    .meta {
      color: var(--muted);
      font-size: 13px;
      line-height: 1.45;
      overflow-wrap: anywhere;
    }
    .issue {
      border-bottom: 1px solid var(--line);
      padding-bottom: 20px;
      margin-bottom: 22px;
    }
    .issue h2 {
      font-size: 18px;
      margin: 0 0 8px;
      letter-spacing: 0;
    }
    .issue pre {
      white-space: pre-wrap;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 12px;
      max-height: 260px;
      overflow: auto;
      background: #ffffff;
    }
    .grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 18px;
    }
    .full {
      grid-column: 1 / -1;
    }
    .hidden {
      display: none;
    }
    .error {
      color: var(--danger);
      font-weight: 700;
      margin-top: 12px;
      overflow-wrap: anywhere;
    }
    .approval, .execution {
      border-top: 1px solid var(--line);
      margin-top: 24px;
      padding-top: 20px;
    }
    .approval label, .execution label {
      display: flex;
      align-items: flex-start;
      font-weight: 400;
      line-height: 1.45;
    }
    .approved {
      color: var(--accent);
      font-weight: 700;
      margin-top: 12px;
      overflow-wrap: anywhere;
    }
    .queue-stage {
      border-top: 1px solid var(--line);
      padding: 18px 0;
    }
    .queue-stage h3 { font-size: 16px; margin: 0 0 10px; }
    .queue-card {
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #ffffff;
      margin: 10px 0;
      padding: 12px;
    }
    .queue-card .meta { font-family: Consolas, "Liberation Mono", monospace; margin-top: 6px; }
    .queue-card button { margin-top: 10px; }
    .queue-card.planning-default-proposal { border-color: var(--accent); box-shadow: 0 0 0 1px var(--accent); }
    .planning-transcript {
      min-height: 180px;
      max-height: 420px;
      overflow: auto;
      white-space: pre-wrap;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: var(--panel);
      padding: 12px;
    }
    @media (max-width: 820px) {
      main, .grid {
        display: block;
      }
      aside {
        border-right: 0;
        border-bottom: 1px solid var(--line);
      }
      section {
        padding: 20px;
      }
    }
  </style>
</head>
<body>
  <header>
    <h1>Axiom Forge Workbench</h1>
  </header>
  <main>
    <aside>
      <form id="issue-form">
        <label for="issue-input">GitHub Issue</label>
        <input id="issue-input" name="issue" placeholder="49 or https://github.com/owner/repo/issues/49" autocomplete="off">
        <button id="load-button" type="submit">Load Draft</button>
        <div id="error" class="error hidden"></div>
      </form>
      <p class="meta">Draft artifacts stay editable here. Only explicit approval creates committed delegation authority.</p>
      <div class="history">
        <h2>Historical captured runs</h2>
        <div id="run-history" class="meta">Loading captured-run history…</div>
      </div>
      <div id="evidence-summary" class="hidden"></div>
    </aside>
    <section>
      <div id="decision-queue">
        <div class="issue">
          <h2>Operator decision queue</h2>
          <p class="meta">Nothing awaiting a decision is invisible. This queue is re-derived from Forge-owned delegation artifacts and captured evidence each time it loads.</p>
          <button id="start-draft-button" type="button">Prepare a new task</button>
          <button id="start-planning-button" type="button">Start planning session</button>
        </div>
        <div id="decision-queue-stages" class="meta">Loading operator decisions…</div>
      </div>
      <div id="live-run" class="issue hidden">
        <h2>Live active delegation</h2>
        <p id="live-run-status" class="meta">Display-only raw output; captured evidence remains authoritative.</p>
        <h3>stdout</h3><pre id="live-run-stdout"></pre>
        <h3>stderr</h3><pre id="live-run-stderr"></pre>
      </div>
      <div id="planning-workflow" class="hidden">
        <div class="issue">
          <h2>Planning sessions</h2>
          <p class="meta">Planning can investigate a disposable target worktree but grants no authority to edit, delegate, approve, or promote.</p>
          <div class="grid">
            <div><label for="planning-adapter">Planning driver</label><select id="planning-adapter"><option>codex</option><option>claude-code</option></select></div>
            <div><label for="planning-target">Target repository</label><input id="planning-target" placeholder="C:\path\to\target-repo"></div>
            <div class="full"><label for="planning-issue-seed">Optional GitHub issue seed</label><input id="planning-issue-seed" placeholder="100 or issue URL"></div>
            <div class="full"><label for="planning-prompt">Planning prompt</label><textarea id="planning-prompt"></textarea></div>
          </div>
          <button id="create-planning-session" type="button">Start investigation-only session</button>
        </div>
        <div class="grid">
          <div><h3>Sessions</h3><div id="planning-session-list" class="meta">Loading sessions…</div></div>
          <div>
            <h3 id="planning-session-heading">Select a session</h3>
            <div id="planning-transcript" class="planning-transcript meta"></div>
            <label for="planning-message">Operator reply</label>
            <textarea id="planning-message"></textarea>
            <button id="send-planning-message" type="button">Send planning reply</button>
            <button id="close-planning-session" type="button">Close planning session</button>
            <div id="planning-proposals"></div>
          </div>
        </div>
      </div>
      <div id="draft-workflow" class="hidden">
      <div id="empty" class="meta">Load a GitHub Issue to prepare a draft task artifact.</div>
      <div id="preview" class="hidden">
        <div class="issue">
          <h2 id="issue-title"></h2>
          <div id="issue-url" class="meta"></div>
          <pre id="issue-body"></pre>
        </div>
        <div class="grid">
          <div class="full">
            <label for="task-intent">Task Intent</label>
            <textarea id="task-intent"></textarea>
          </div>
          <div class="full">
            <label for="task-text">Task Text</label>
            <textarea id="task-text"></textarea>
          </div>
          <div>
            <label for="target-scope">Target Scope</label>
            <textarea id="target-scope"></textarea>
          </div>
          <div>
            <label for="acceptance-check">Acceptance Check</label>
            <textarea id="acceptance-check"></textarea>
          </div>
          <div>
            <label for="adapter">Draft Adapter</label>
            <select id="adapter"></select>
          </div>
        </div>
        <div class="approval">
          <div class="meta">Draft content is not adapter-facing authority. Approval creates and commits the task, target scope, and acceptance check together.</div>
          <label for="approval-confirmation"><input id="approval-confirmation" type="checkbox">I approve this task text, target scope, acceptance check, and adapter selection as delegation authority.</label>
          <button id="approve-button" type="button">Approve Delegation Artifacts</button>
          <div id="approval-result" class="approved hidden"></div>
        </div>
        <div id="execution" class="execution hidden">
          <div class="meta">Starting a run invokes only the approved target-mode adapter task. It captures run evidence, then you can verify it; promotion remains outside the workbench.</div>
          <label for="execution-confirmation"><input id="execution-confirmation" type="checkbox">I confirm that I want to start this approved target-mode delegation now.</label>
          <button id="run-button" type="button">Run Approved Delegation</button>
          <div id="execution-result" class="approved hidden"></div>
        </div>
      </div>
      </div>
    </section>
  </main>
  <script>
    const form = document.querySelector("#issue-form");
    const button = document.querySelector("#load-button");
    const error = document.querySelector("#error");
    const preview = document.querySelector("#preview");
    const empty = document.querySelector("#empty");
    const approveButton = document.querySelector("#approve-button");
    const approvalConfirmation = document.querySelector("#approval-confirmation");
    const approvalResult = document.querySelector("#approval-result");
    const execution = document.querySelector("#execution");
    const executionConfirmation = document.querySelector("#execution-confirmation");
    const executionResult = document.querySelector("#execution-result");
    const runButton = document.querySelector("#run-button");
    const evidenceSummary = document.querySelector("#evidence-summary");
    const runHistory = document.querySelector("#run-history");
    const decisionQueue = document.querySelector("#decision-queue");
    const decisionQueueStages = document.querySelector("#decision-queue-stages");
    const liveRun = document.querySelector("#live-run");
    const liveRunStatus = document.querySelector("#live-run-status");
    const liveRunStdout = document.querySelector("#live-run-stdout");
    const liveRunStderr = document.querySelector("#live-run-stderr");
    const draftWorkflow = document.querySelector("#draft-workflow");
    const startDraftButton = document.querySelector("#start-draft-button");
    const planningWorkflow = document.querySelector("#planning-workflow");
    const startPlanningButton = document.querySelector("#start-planning-button");
    const planningSessionList = document.querySelector("#planning-session-list");
    const planningTranscript = document.querySelector("#planning-transcript");
    const retryAdapters = ["codex", "claude-code", "copilot", "opencode", "cursor", "kiro", "qoder", "kilo", "antigravity"];
    let loadedIssue = null;
    let approvedDelegation = null;
    let selectedPlanningSession = null;
    let selectedPlanningProposal = null;
    let liveRunPoll = null;

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      error.classList.add("hidden");
      button.disabled = true;
      try {
        const issue = encodeURIComponent(document.querySelector("#issue-input").value);
        const response = await fetch(`/api/draft?issue=${issue}`);
        const payload = await response.json();
        if (!response.ok) {
          throw new Error(payload.error || "draft_load_failed");
        }
        renderPreview(payload);
        if (selectedPlanningProposal) applyPlanningProposal(selectedPlanningProposal.proposal);
      } catch (loadError) {
        error.textContent = loadError.message;
        error.classList.remove("hidden");
      } finally {
        button.disabled = false;
      }
    });

    function renderPreview(payload) {
      draftWorkflow.classList.remove("hidden");
      decisionQueue.classList.add("hidden");
      const issue = payload.source_issue;
      loadedIssue = issue;
      approvalConfirmation.checked = false;
      approvalResult.classList.add("hidden");
      approvedDelegation = null;
      executionConfirmation.checked = false;
      execution.classList.add("hidden");
      executionResult.classList.add("hidden");
      document.querySelector("#issue-title").textContent = `#${issue.number} ${issue.title}`;
      document.querySelector("#issue-url").textContent = issue.url;
      document.querySelector("#issue-body").textContent = issue.body || "";
      document.querySelector("#task-intent").value = payload.task_intent;
      document.querySelector("#task-text").value = payload.task_text;
      document.querySelector("#target-scope").value = payload.target_scope;
      document.querySelector("#acceptance-check").value = payload.acceptance_check;

      const adapter = document.querySelector("#adapter");
      adapter.replaceChildren(...payload.adapter_options.map((name) => {
        const option = document.createElement("option");
        option.value = name;
        option.textContent = name;
        option.selected = name === payload.draft_adapter;
        return option;
      }));

      empty.classList.add("hidden");
      preview.classList.remove("hidden");
    }

    approveButton.addEventListener("click", async () => {
      error.classList.add("hidden");
      approvalResult.classList.add("hidden");
      if (!loadedIssue) {
        error.textContent = "missing_issue_reference";
        error.classList.remove("hidden");
        return;
      }

      approveButton.disabled = true;
      try {
        const response = await fetch("/api/approve", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            issue_number: loadedIssue.number,
            task_text: document.querySelector("#task-text").value,
            target_scope: document.querySelector("#target-scope").value,
            acceptance_check: document.querySelector("#acceptance-check").value,
            adapter: document.querySelector("#adapter").value,
            approved: approvalConfirmation.checked,
            planning_session_id: selectedPlanningProposal ? selectedPlanningProposal.session_id : null,
            planning_proposal_version: selectedPlanningProposal ? selectedPlanningProposal.version : null,
          }),
        });
        const payload = await response.json();
        if (!response.ok) {
          throw new Error(payload.error || "delegation_approval_failed");
        }
        approvalResult.textContent = `Approved authority: ${payload.task_file}, ${payload.scope_file}, and ${payload.acceptance_file} at ${payload.delegation_artifact_revision}.`;
        approvalResult.classList.remove("hidden");
        approvedDelegation = payload;
        executionConfirmation.checked = false;
        executionResult.classList.add("hidden");
        execution.classList.remove("hidden");
      } catch (approvalError) {
        error.textContent = approvalError.message;
        error.classList.remove("hidden");
      } finally {
        approveButton.disabled = false;
      }
    });

    runButton.addEventListener("click", async () => {
      error.classList.add("hidden");
      executionResult.classList.add("hidden");
      if (!approvedDelegation) {
        error.textContent = "missing_approved_delegation";
        error.classList.remove("hidden");
        return;
      }

      runButton.disabled = true;
      try {
        const runRequest = fetch("/api/run", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            task_file: approvedDelegation.task_file,
            confirmed: executionConfirmation.checked,
          }),
        });
        pollLiveRun();
        const response = await runRequest;
        const payload = await response.json();
        if (!response.ok) {
          throw new Error(payload.error || "target_mode_run_failed");
        }
        const failure = payload.failure_reason ? ` (${payload.failure_reason})` : "";
        executionResult.textContent = `Captured run ${payload.run_id}: ${payload.run_status}${failure}.`;
        executionResult.classList.remove("hidden");
        await renderEvidenceSummary(payload.run_id);
        await renderHistoricalRuns();
        await renderDecisionQueue();
      } catch (executionError) {
        error.textContent = executionError.message;
        error.classList.remove("hidden");
      } finally {
        runButton.disabled = false;
      }
    });
    async function pollLiveRun() {
      const response = await fetch("/api/live-run");
      const payload = await response.json();
      if (!response.ok) return;
      liveRun.classList.remove("hidden");
      liveRunStatus.textContent = payload.reason || payload.state;
      if (payload.state === "active") {
        liveRunStdout.textContent = payload.stdout.text;
        liveRunStderr.textContent = payload.stderr.text;
        liveRunPoll = setTimeout(pollLiveRun, 1000);
      } else if (payload.state === "unavailable") {
        liveRunPoll = setTimeout(pollLiveRun, 1000);
      } else if (payload.state === "terminal") {
        await renderDecisionQueue();
        await renderHistoricalRuns();
      }
    }
    async function renderEvidenceSummary(runId, verify = false, readOnly = false) {
      const response = await fetch(verify ? "/api/verify" : `/api/runs/${runId}`, {
        method: verify ? "POST" : "GET",
        headers: verify ? { "Content-Type": "application/json" } : undefined,
        body: verify ? JSON.stringify({ run_id: runId }) : undefined,
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.error || "evidence_summary_failed");
      }
      evidenceSummary.replaceChildren();
      const heading = document.createElement("h3");
      heading.textContent = `Operator evidence summary: ${payload.run_id}`;
      evidenceSummary.append(heading);
      const fields = [
        ["Task intent", payload.task_intent],
        ["Approved scope", (payload.approved_scope || []).join(", ") || "missing"],
        ["Adapter", payload.adapter],
        ["Run status", payload.run_status],
        ["Changed paths", (payload.changed_paths || []).join(", ") || "none"],
        ["Verification", payload.verification_result],
        ["Acceptance", payload.acceptance_result],
        ["Failure reason", payload.failure_reason || payload.verification_reason || "none"],
        ["Next allowed actions", (payload.next_allowed_actions || []).join(", ")],
      ];
      const list = document.createElement("dl");
      fields.forEach(([label, value]) => {
        const term = document.createElement("dt");
        term.textContent = label;
        const detail = document.createElement("dd");
        detail.textContent = value;
        list.append(term, detail);
      });
      evidenceSummary.append(list);
      if (!readOnly && payload.verification_result === "NOT_RUN" && payload.run_status === "COMPLETED") {
        const verifyButton = document.createElement("button");
        verifyButton.type = "button";
        verifyButton.textContent = "Verify Captured Run";
        verifyButton.addEventListener("click", async () => {
          verifyButton.disabled = true;
          try {
            await renderEvidenceSummary(runId, true);
          } catch (verificationError) {
            error.textContent = verificationError.message;
            error.classList.remove("hidden");
          }
        });
        evidenceSummary.append(verifyButton);
      }
      if (!readOnly && (payload.run_status === "FAILED" || payload.verification_result === "FAIL")) {
        const retry = document.createElement("div");
        retry.className = "execution";
        const retryNote = document.createElement("div");
        retryNote.className = "meta";
        retryNote.textContent = "Retry creates a new captured run from this run's recorded approved task and scope. It does not change the failed evidence.";
        const retryLabel = document.createElement("label");
        retryLabel.textContent = "Retry adapter";
        const retryAdapter = document.createElement("select");
        retryAdapters.forEach((adapter) => {
          const option = document.createElement("option");
          option.value = adapter;
          option.textContent = adapter;
          option.selected = adapter === payload.adapter;
          retryAdapter.append(option);
        });
        if (!retryAdapters.includes(payload.adapter)) retryAdapter.value = retryAdapters[0];
        const retryConfirmationLabel = document.createElement("label");
        const retryConfirmation = document.createElement("input");
        retryConfirmation.type = "checkbox";
        retryConfirmationLabel.append(retryConfirmation, "I confirm that I want to retry this approved task now.");
        const retryButton = document.createElement("button");
        retryButton.type = "button";
        retryButton.textContent = "Retry Approved Task";
        retryButton.addEventListener("click", async () => {
          error.classList.add("hidden");
          retryButton.disabled = true;
          try {
            const failedEvidenceSummary = evidenceSummary.cloneNode(true);
            const retryResponse = await fetch("/api/retry", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                run_id: runId,
                adapter: retryAdapter.value,
                confirmed: retryConfirmation.checked,
              }),
            });
            const retryPayload = await retryResponse.json();
            if (!retryResponse.ok) {
              throw new Error(retryPayload.error || "retry_failed");
            }
            await renderEvidenceSummary(retryPayload.run_id);
            const priorEvidence = document.createElement("details");
            priorEvidence.open = true;
            const priorEvidenceTitle = document.createElement("summary");
            priorEvidenceTitle.textContent = `Prior failed evidence summary: ${runId}`;
            priorEvidence.append(priorEvidenceTitle, failedEvidenceSummary);
            evidenceSummary.prepend(priorEvidence);
            await renderHistoricalRuns();
            await renderDecisionQueue();
          } catch (retryError) {
            error.textContent = retryError.message;
            error.classList.remove("hidden");
          } finally {
            retryButton.disabled = false;
          }
        });
        retry.append(retryNote, retryLabel, retryAdapter, retryConfirmationLabel, retryButton);
        evidenceSummary.append(retry);
      }
      const details = document.createElement("details");
      const summary = document.createElement("summary");
      summary.textContent = "Raw stdout, stderr, and patch diff";
      details.append(summary);
      details.addEventListener("toggle", async () => {
        if (!details.open || details.dataset.loaded) return;
        const detailResponse = await fetch(`/api/runs/${runId}/details`);
        const raw = await detailResponse.json();
        if (!detailResponse.ok) return;
        [["stdout", raw.stdout], ["stderr", raw.stderr], ["patch diff", raw.patch_diff]].forEach(([label, text]) => {
          const title = document.createElement("h4");
          title.textContent = label;
          const pre = document.createElement("pre");
          pre.textContent = text || "missing";
          details.append(title, pre);
        });
        details.dataset.loaded = "true";
      });
      evidenceSummary.append(details);
      evidenceSummary.classList.remove("hidden");
    }
    async function renderEvidenceDetails(runId) {
      const response = await fetch(`/api/runs/${runId}/details`);
      const raw = await response.json();
      if (!response.ok) throw new Error(raw.error || "captured_run_evidence_unavailable");
      evidenceSummary.replaceChildren();
      const title = document.createElement("h3");
      title.textContent = `Captured run evidence: ${runId}`;
      evidenceSummary.append(title);
      [["stdout", raw.stdout], ["stderr", raw.stderr], ["patch diff", raw.patch_diff]].forEach(([label, text]) => {
        const heading = document.createElement("h4");
        heading.textContent = label;
        const pre = document.createElement("pre");
        pre.textContent = text || "missing";
        evidenceSummary.append(heading, pre);
      });
      evidenceSummary.classList.remove("hidden");
    }
    async function runQueueAction(item) {
      error.classList.add("hidden");
      try {
        if (item.action === "execute") {
          if (!window.confirm(`Start approved delegation ${item.task_file}?`)) return;
          const response = await fetch("/api/run", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ task_file: item.task_file, confirmed: true }),
          });
          const payload = await response.json();
          if (!response.ok) throw new Error(payload.error || "target_mode_run_failed");
          await renderEvidenceSummary(payload.run_id);
        } else if (item.action === "verify") {
          await renderEvidenceSummary(item.run_id, true);
        } else if (item.action === "retry" || item.action === "prepare_review") {
          await renderEvidenceSummary(item.run_id, false, item.action === "prepare_review");
          evidenceSummary.scrollIntoView({ behavior: "smooth", block: "start" });
        } else if (item.action === "inspect_evidence") {
          await renderEvidenceDetails(item.run_id);
          evidenceSummary.scrollIntoView({ behavior: "smooth", block: "start" });
        } else if (item.action === "review_planning_proposal") {
          decisionQueue.classList.add("hidden");
          draftWorkflow.classList.add("hidden");
          planningWorkflow.classList.remove("hidden");
          await selectPlanningSession(item.planning_session_id);
        } else {
          throw new Error(item.evidence_error || "captured_run_evidence_unavailable");
        }
        await renderDecisionQueue();
        await renderHistoricalRuns();
      } catch (queueActionError) {
        error.textContent = queueActionError.message;
        error.classList.remove("hidden");
      }
    }

    async function renderDecisionQueue() {
      const response = await fetch("/api/decision-queue");
      const payload = await response.json();
      if (!response.ok) {
        decisionQueueStages.textContent = payload.error || "operator_decision_queue_unavailable";
        return;
      }
      decisionQueueStages.replaceChildren();
      payload.stages.forEach((stage) => {
        const section = document.createElement("section");
        section.className = "queue-stage";
        const heading = document.createElement("h3");
        heading.textContent = `${stage.label} (${stage.items.length})`;
        section.append(heading);
        if (!stage.items.length) {
          const emptyStage = document.createElement("p");
          emptyStage.className = "meta";
          emptyStage.textContent = `Nothing in ${stage.label.toLowerCase()}.`;
          section.append(emptyStage);
        }
        stage.items.forEach((item) => {
          const card = document.createElement("article");
          card.className = "queue-card";
          const decision = document.createElement("strong");
          decision.textContent = item.decision_label;
          const evidence = document.createElement("div");
          evidence.className = "meta";
          evidence.textContent = item.evidence_line;
          card.append(decision, evidence);
          if (item.action_label) {
            const action = document.createElement("button");
            action.type = "button";
            action.textContent = item.action_label;
            action.addEventListener("click", () => runQueueAction(item));
            card.append(action);
          }
          section.append(card);
        });
        decisionQueueStages.append(section);
      });
    }

    startDraftButton.addEventListener("click", () => {
      draftWorkflow.classList.remove("hidden");
      planningWorkflow.classList.add("hidden");
      decisionQueue.classList.add("hidden");
      document.querySelector("#issue-input").focus();
    });

    startPlanningButton.addEventListener("click", async () => {
      decisionQueue.classList.add("hidden");
      draftWorkflow.classList.add("hidden");
      planningWorkflow.classList.remove("hidden");
      await renderPlanningSessions();
    });

    document.querySelector("#create-planning-session").addEventListener("click", async () => {
      error.classList.add("hidden");
      const issueSeed = document.querySelector("#planning-issue-seed").value.trim();
      const request = {
        adapter: document.querySelector("#planning-adapter").value,
        target_repo: document.querySelector("#planning-target").value,
        prompt: document.querySelector("#planning-prompt").value,
      };
      if (issueSeed) request.issue_seed = issueSeed;
      try {
        const response = await fetch("/api/planning-sessions", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(request),
        });
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error || "planning_session_start_failed");
        selectedPlanningSession = payload;
        renderSelectedPlanningSession(payload);
        await renderPlanningSessions();
      } catch (planningError) {
        error.textContent = planningError.message;
        error.classList.remove("hidden");
      }
    });

    document.querySelector("#send-planning-message").addEventListener("click", async () => {
      if (!selectedPlanningSession) return;
      const response = await fetch(`/api/planning-sessions/${selectedPlanningSession.session_id}/messages`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: document.querySelector("#planning-message").value }),
      });
      const payload = await response.json();
      if (!response.ok) {
        error.textContent = payload.error || "planning_message_failed";
        error.classList.remove("hidden");
        return;
      }
      document.querySelector("#planning-message").value = "";
      selectedPlanningSession = payload;
      renderSelectedPlanningSession(payload);
    });

    document.querySelector("#close-planning-session").addEventListener("click", async () => {
      if (!selectedPlanningSession) return;
      const response = await fetch(`/api/planning-sessions/${selectedPlanningSession.session_id}/close`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      const payload = await response.json();
      if (!response.ok) {
        error.textContent = payload.error || "planning_close_failed";
        error.classList.remove("hidden");
        return;
      }
      selectedPlanningSession = payload;
      renderSelectedPlanningSession(payload);
      await renderPlanningSessions();
    });

    async function renderPlanningSessions() {
      const response = await fetch("/api/planning-sessions");
      const payload = await response.json();
      if (!response.ok) {
        planningSessionList.textContent = payload.error || "planning_sessions_unavailable";
        return;
      }
      planningSessionList.replaceChildren();
      if (!payload.sessions.length) {
        planningSessionList.textContent = "No planning sessions yet.";
        return;
      }
      payload.sessions.forEach((session) => {
        const button = document.createElement("button");
        button.type = "button";
        button.textContent = session.adapter + " · " + session.state + " · " + session.session_id.slice(0, 8);
        button.addEventListener("click", () => selectPlanningSession(session.session_id));
        planningSessionList.append(button);
      });
    }

    async function selectPlanningSession(sessionId) {
      const response = await fetch("/api/planning-sessions/" + sessionId);
      const payload = await response.json();
      if (!response.ok) {
        error.textContent = payload.error || "planning_session_unavailable";
        error.classList.remove("hidden");
        return;
      }
      selectedPlanningSession = payload;
      renderSelectedPlanningSession(payload);
    }

    function renderSelectedPlanningSession(session) {
      document.querySelector("#planning-session-heading").textContent =
        session.adapter + " planning session · " + session.state;
      planningTranscript.textContent = (session.events || []).map((event) => {
        const label = event.type || "event";
        return label + ": " + (event.text || JSON.stringify(event.vendor_event || event));
      }).join("\n");
      const proposals = document.querySelector("#planning-proposals");
      proposals.replaceChildren();
      const approvable = session.state !== "FAILED" && session.state !== "BOUNDARY_VIOLATION";
      const validVersions = (session.proposals || []).filter((entry) => entry.valid).map((entry) => entry.version);
      const newestValidVersion = validVersions.length ? Math.max.apply(null, validVersions) : null;
      (session.proposals || []).forEach((entry) => {
        const card = document.createElement("div");
        card.className = "queue-card";
        const isDefault = approvable && entry.valid && entry.version === newestValidVersion;
        if (isDefault) card.classList.add("planning-default-proposal");
        const status = document.createElement("strong");
        status.textContent = "Proposal " + entry.version +
          (entry.valid ? " · valid" : " · invalid") +
          (isDefault ? " · newest valid (default)" : "");
        card.append(status);
        if (entry.valid && approvable) {
          const useButton = document.createElement("button");
          useButton.type = "button";
          useButton.textContent = isDefault ? "Use newest valid proposal (default)" : "Use proposal as editable draft";
          useButton.addEventListener("click", () => usePlanningProposal(session, entry));
          card.append(useButton);
        }
        proposals.append(card);
      });
    }

    function usePlanningProposal(session, entry) {
      selectedPlanningProposal = {
        session_id: session.session_id,
        version: entry.version,
        proposal: entry.proposal,
      };
      const issue = session.source && session.source.kind === "github_issue"
        ? session.source.issue
        : null;
      if (!issue) {
        error.textContent = "Anchor this free-form proposal to a GitHub issue before approval.";
        error.classList.remove("hidden");
        document.querySelector("#issue-input").focus();
        return;
      }
      renderPreview({
        source_issue: issue,
        task_intent: entry.proposal.task_text,
        task_text: entry.proposal.task_text,
        target_scope: entry.proposal.target_scope.join("\n"),
        acceptance_check: entry.proposal.acceptance_check,
        adapter_options: retryAdapters,
        draft_adapter: entry.proposal.suggested_adapter,
      });
      planningWorkflow.classList.add("hidden");
      applyPlanningProposal(entry.proposal);
    }

    function applyPlanningProposal(proposal) {
      document.querySelector("#task-intent").value = proposal.task_text;
      document.querySelector("#task-text").value = proposal.task_text;
      document.querySelector("#target-scope").value = proposal.target_scope.join("\n");
      document.querySelector("#acceptance-check").value = proposal.acceptance_check;
      document.querySelector("#adapter").value = proposal.suggested_adapter;
    }

    setInterval(async () => {
      if (
        selectedPlanningSession
        && !planningWorkflow.classList.contains("hidden")
        && selectedPlanningSession.state === "ACTIVE"
      ) {
        await selectPlanningSession(selectedPlanningSession.session_id);
      }
    }, 2500);

    async function renderHistoricalRuns() {
      const response = await fetch("/api/runs");
      const payload = await response.json();
      if (!response.ok) {
        runHistory.textContent = payload.error || "historical_runs_unavailable";
        return;
      }
      runHistory.replaceChildren();
      if (!payload.runs.length) {
        runHistory.textContent = "No captured runs are available.";
        return;
      }
      const list = document.createElement("ul");
      payload.runs.forEach((entry) => {
        const item = document.createElement("li");
        const summary = entry.summary;
        const label = document.createElement("strong");
        label.textContent = `${entry.run_id}: ${entry.state}; ${entry.verification_state}`;
        item.append(label);
        const detail = document.createElement("div");
        detail.className = "meta";
        detail.textContent = summary
          ? `${summary.run_status}; verification ${summary.verification_result}; read-only evidence.`
          : `Missing evidence: ${entry.evidence_error}.`;
        item.append(detail);
        if (summary) {
          const button = document.createElement("button");
          button.type = "button";
          button.textContent = "View evidence summary";
          button.addEventListener("click", async () => {
            try {
              await renderEvidenceSummary(entry.run_id, false, true);
            } catch (historyError) {
              error.textContent = historyError.message;
              error.classList.remove("hidden");
            }
          });
          item.append(button);
        }
        list.append(item);
      });
      runHistory.append(list);
    }
    renderDecisionQueue();
    renderHistoricalRuns();
  </script>
</body>
</html>
"""
