(function () {
  "use strict";

  const storageKey = "gas_v1a_prototype_state";

  const steps = [
    { id: "intake", label: "Intake" },
    { id: "operator", label: "Operator packet" },
    { id: "spine", label: "Spine" },
    { id: "draft", label: "Draft" },
    { id: "review", label: "Review" },
    { id: "output", label: "Output" },
    { id: "evidence", label: "Evidence" },
  ];

  const defaultState = {
    activeStep: "intake",
    participant: {
      id: "001",
      displayName: "Justin",
      inviteStatus: "ready to send",
    },
    intake: {
      name: "Justin",
      email: "",
      followUp: "email",
      projectTitle: "",
      artifactType: "book / long-form manuscript",
      artifactStage: "loose notes",
      sourceNotes: "",
      importantFragments: "",
      existingStructure: "",
      desiredOutput: "",
      firstSectionPreference: "recommend the best first section",
      usefulnessDefinition: "",
      audience: "",
      audienceOutcome: "",
      whyItMatters: "",
      desiredTone: "clear, reflective, practical",
      mustNotSoundLike: "",
      constraints: "",
      phrasesToPreserve: "",
      privacyAck: false,
    },
    operator: null,
    spine: null,
    draft: null,
    review: null,
    output: null,
    evidence: {
      inviteSent: "ready",
      accepted: "pending",
      intakeReceived: "no",
      outputDelivered: "no",
      feedbackReceived: "no",
      ahaMoment: "",
      wouldPay: "",
      privacyConcern: "",
      mainFriction: "",
      nextAction: "send invite/intake",
      status: "invited",
      operatorNotes: "",
    },
  };

  let state = loadState();

  const app = document.getElementById("app");
  const stepNav = document.getElementById("stepNav");
  const stateSummary = document.getElementById("stateSummary");
  const progressFill = document.getElementById("progressFill");
  const progressLabel = document.getElementById("progressLabel");
  const toast = document.getElementById("toast");

  document.getElementById("copyInviteButton").addEventListener("click", () => {
    copyText(buildInviteText());
  });

  document.getElementById("resetButton").addEventListener("click", () => {
    if (!window.confirm("Reset the local prototype state for participant 001?")) {
      return;
    }
    state = structuredClone(defaultState);
    saveState();
    render();
    showToast("Local prototype state reset.");
  });

  function loadState() {
    try {
      const raw = localStorage.getItem(storageKey);
      if (!raw) return structuredClone(defaultState);
      return { ...structuredClone(defaultState), ...JSON.parse(raw) };
    } catch (error) {
      return structuredClone(defaultState);
    }
  }

  function saveState() {
    localStorage.setItem(storageKey, JSON.stringify(state));
  }

  function setStep(stepId) {
    state.activeStep = stepId;
    saveState();
    render();
  }

  function currentStepIndex() {
    return steps.findIndex((step) => step.id === state.activeStep);
  }

  function completedStepIds() {
    const completed = new Set();
    if (state.operator) completed.add("intake");
    if (state.spine) completed.add("operator");
    if (state.draft) completed.add("spine");
    if (state.review) completed.add("draft");
    if (state.output) completed.add("review");
    if (state.evidence.status === "completed") completed.add("output");
    return completed;
  }

  function render() {
    renderNav();
    renderProgress();
    renderStateSummary();

    if (state.activeStep === "operator") renderOperator();
    else if (state.activeStep === "spine") renderSpine();
    else if (state.activeStep === "draft") renderDraft();
    else if (state.activeStep === "review") renderReview();
    else if (state.activeStep === "output") renderOutput();
    else if (state.activeStep === "evidence") renderEvidence();
    else renderIntake();
  }

  function renderNav() {
    const completed = completedStepIds();
    stepNav.innerHTML = steps
      .map((step, index) => {
        const isActive = step.id === state.activeStep;
        const isComplete = completed.has(step.id);
        return `
          <button class="step-button ${isActive ? "active" : ""} ${isComplete ? "complete" : ""}" type="button" data-step="${step.id}">
            <span class="step-number">${index + 1}</span>
            <span>${escapeHtml(step.label)}</span>
            <span class="step-status-dot" aria-hidden="true"></span>
          </button>
        `;
      })
      .join("");

    stepNav.querySelectorAll("[data-step]").forEach((button) => {
      button.addEventListener("click", () => setStep(button.dataset.step));
    });
  }

  function renderProgress() {
    const completedCount = completedStepIds().size;
    const percent = Math.round((completedCount / steps.length) * 100);
    progressFill.style.width = `${percent}%`;
    progressLabel.textContent = `${completedCount} of ${steps.length} workflow gates complete. Current gate: ${activeStepLabel()}.`;
  }

  function renderStateSummary() {
    const rows = [
      ["Participant", `${state.participant.id} - ${state.participant.displayName}`],
      ["Project", state.intake.projectTitle || "Untitled artifact"],
      ["Artifact type", state.intake.artifactType],
      ["State", activeStepLabel()],
      ["Next action", state.evidence.nextAction || "Continue workflow"],
    ];

    stateSummary.innerHTML = rows
      .map(
        ([term, value]) => `
        <div>
          <dt>${escapeHtml(term)}</dt>
          <dd>${escapeHtml(value)}</dd>
        </div>
      `,
      )
      .join("");
  }

  function activeStepLabel() {
    return steps.find((step) => step.id === state.activeStep)?.label || "Intake";
  }

  function renderIntake() {
    app.innerHTML = `
      <div class="screen-grid">
        <section class="card">
          <h2>Participant Intake</h2>
          <p>Capture enough source material and consent to begin the concierge-assisted V1A workflow.</p>
          <form id="intakeForm" class="form-grid" autocomplete="off">
            ${inputField("name", "Name", state.intake.name, "Justin", true)}
            ${inputField("email", "Email", state.intake.email, "name@example.com", false, "email")}
            ${selectField("followUp", "Preferred follow-up", state.intake.followUp, ["email", "short call", "async notes only"])}
            ${inputField("projectTitle", "Working title", state.intake.projectTitle, "A rough title is enough")}
            ${selectField("artifactType", "Artifact type", state.intake.artifactType, ["book / long-form manuscript", "essay series", "course or teaching outline", "not sure yet"])}
            ${selectField("artifactStage", "Artifact stage", state.intake.artifactStage, ["loose notes", "rough outline", "partial draft", "scattered materials", "restarting a stalled project"])}
            ${textareaField("sourceNotes", "Paste rough material", state.intake.sourceNotes, "Notes, fragments, claims, outlines, teaching ideas, or rough thinking.", true)}
            ${textareaField("importantFragments", "What parts feel most important?", state.intake.importantFragments, "Point to anything that should not get lost.")}
            ${textareaField("existingStructure", "Existing structure", state.intake.existingStructure, "Optional outline, section list, or module list.")}
            ${textareaField("desiredOutput", "What should this become?", state.intake.desiredOutput, "Describe the finished artifact in ordinary language.", true)}
            ${selectField("firstSectionPreference", "What should we create first?", state.intake.firstSectionPreference, ["first chapter or section", "first essay", "first lesson", "strongest opening section", "recommend the best first section"])}
            ${textareaField("usefulnessDefinition", "What would make this useful?", state.intake.usefulnessDefinition, "Name the progress you want to feel after the first packet.", true)}
            ${textareaField("audience", "Who is this for?", state.intake.audience, "Describe the reader, learner, or audience.", true)}
            ${textareaField("audienceOutcome", "What should they understand or do?", state.intake.audienceOutcome, "Define the audience outcome.")}
            ${textareaField("whyItMatters", "Why does this matter?", state.intake.whyItMatters, "Why is this artifact worth making?")}
            ${inputField("desiredTone", "Desired tone", state.intake.desiredTone, "clear, reflective, practical")}
            ${textareaField("mustNotSoundLike", "What should this not sound like?", state.intake.mustNotSoundLike, "Styles, tones, or genres to avoid.", true)}
            ${textareaField("constraints", "Constraints", state.intake.constraints, "Length, claims to avoid, sensitivity, boundaries.")}
            ${textareaField("phrasesToPreserve", "Phrases or ideas to preserve", state.intake.phrasesToPreserve, "Optional language that should remain visible.")}
            <label class="checkbox-row field full">
              <input id="privacyAck" type="checkbox" ${state.intake.privacyAck ? "checked" : ""}>
              <span>I understand V1A is concierge-assisted. A human operator may review submitted material, source stays private by default, and generated output remains separate from original source.</span>
            </label>
          </form>
          <div class="button-row">
            <button id="saveIntake" class="button secondary" type="button">Save intake</button>
            <button id="buildOperatorPacket" class="button" type="button">Build operator packet</button>
          </div>
        </section>

        <aside class="card">
          <h2>Invite / Intake Packet</h2>
          <p class="small-note">Copy this message into the channel you use for Justin. The app does not send external messages.</p>
          <div class="button-row">
            <button id="copyInviteInline" class="button secondary" type="button">Copy invite text</button>
            <button id="markInviteReady" class="button ghost" type="button">Mark ready</button>
          </div>
          <pre class="code-box">${escapeHtml(buildInviteText())}</pre>
        </aside>
      </div>
    `;

    document.getElementById("saveIntake").addEventListener("click", () => {
      captureIntakeForm();
      saveState();
      render();
      showToast("Intake saved locally.");
    });

    document.getElementById("buildOperatorPacket").addEventListener("click", () => {
      captureIntakeForm();
      state.operator = buildOperatorPacket();
      state.evidence.intakeReceived = state.operator.status === "Accepted" ? "yes" : "needs clarification";
      state.evidence.accepted = state.operator.status === "Accepted" ? "yes" : "pending";
      state.evidence.nextAction = state.operator.status === "Accepted" ? "generate spine" : "request clarification";
      state.evidence.status = state.operator.status === "Accepted" ? "intake" : "blocked";
      setStep("operator");
    });

    document.getElementById("copyInviteInline").addEventListener("click", () => copyText(buildInviteText()));
    document.getElementById("markInviteReady").addEventListener("click", () => {
      state.evidence.inviteSent = "ready";
      state.evidence.nextAction = "send invite/intake";
      state.evidence.status = "invited";
      saveState();
      render();
      showToast("Justin invite marked ready to send.");
    });
  }

  function renderOperator() {
    const packet = state.operator || buildOperatorPacket();
    state.operator = packet;
    saveState();

    app.innerHTML = `
      <div class="screen-grid">
        <section class="card stack">
          <div>
            <span class="pill ${packet.status === "Accepted" ? "good" : "warn"}">${escapeHtml(packet.status)}</span>
            <h2>Operator Packet</h2>
            <p>This packet turns the submitted intake into an operator-ready project state.</p>
          </div>
          <div class="summary-grid">
            ${summaryItem("Project", state.intake.projectTitle || "Untitled artifact")}
            ${summaryItem("Artifact type", state.intake.artifactType)}
            ${summaryItem("Source sufficiency", packet.sourceSufficiency)}
            ${summaryItem("Audience clarity", packet.audienceClarity)}
            ${summaryItem("Privacy status", packet.privacyStatus)}
            ${summaryItem("Next action", packet.nextAction)}
          </div>
          <section class="section-card">
            <h3>Clarified Direction</h3>
            <p>${escapeHtml(packet.clarifiedDirection)}</p>
          </section>
          <section class="section-card">
            <h3>Operator Notes</h3>
            <p>${escapeHtml(packet.operatorNotes)}</p>
          </section>
          <div class="button-row">
            <button class="button secondary" type="button" data-back="intake">Back to intake</button>
            <button id="generateSpine" class="button" type="button">Generate spine</button>
          </div>
        </section>

        <aside class="card">
          <h2>Completeness Checks</h2>
          <ul class="check-list ${packet.warnings.length ? "warning-list" : ""}">
            ${packet.warnings.length ? packet.warnings.map((warning) => `<li>${escapeHtml(warning)}</li>`).join("") : "<li>Minimum packet is present.</li><li>Ready for provisional spine.</li>"}
          </ul>
        </aside>
      </div>
    `;

    bindBackButtons();
    document.getElementById("generateSpine").addEventListener("click", () => {
      state.spine = buildSpine();
      state.evidence.nextAction = "draft first section";
      state.evidence.status = "in production";
      setStep("spine");
    });
  }

  function renderSpine() {
    state.spine = state.spine || buildSpine();
    saveState();

    app.innerHTML = `
      <div class="screen-grid">
        <section class="card stack">
          <div>
            <span class="pill info">Spine preview</span>
            <h2>${escapeHtml(state.spine.title)}</h2>
            <p>${escapeHtml(state.spine.structureSummary)}</p>
          </div>
          <section class="section-card">
            <h3>Central Direction</h3>
            <p>${escapeHtml(state.spine.centralDirection)}</p>
          </section>
          <div class="stack">
            ${state.spine.sections
              .map(
                (section, index) => `
                <article class="section-card">
                  <h3>${index + 1}. ${escapeHtml(section.title)}</h3>
                  <p>${escapeHtml(section.purpose)}</p>
                  <p class="small-note">${escapeHtml(section.seedPoints)}</p>
                </article>
              `,
              )
              .join("")}
          </div>
          <section class="section-card">
            <h3>Assumptions and Missing Material</h3>
            <p>${escapeHtml(state.spine.assumptions)}</p>
          </section>
          <div class="button-row">
            <button class="button secondary" type="button" data-back="operator">Back to packet</button>
            <button id="draftSection" class="button" type="button">Draft first section</button>
          </div>
        </section>

        <aside class="card">
          <h2>Source Lineage</h2>
          <p>${escapeHtml(state.spine.sourceLineage)}</p>
        </aside>
      </div>
    `;

    bindBackButtons();
    document.getElementById("draftSection").addEventListener("click", () => {
      state.draft = buildDraft();
      state.evidence.nextAction = "run review gate";
      setStep("draft");
    });
  }

  function renderDraft() {
    state.draft = state.draft || buildDraft();
    saveState();

    app.innerHTML = `
      <div class="screen-grid">
        <section class="card stack">
          <div>
            <span class="pill info">Assisted draft</span>
            <h2>${escapeHtml(state.draft.title)}</h2>
            <p>${escapeHtml(state.draft.whyThisSection)}</p>
          </div>
          <textarea id="draftBody" class="export-box" aria-label="Draft body">${escapeHtml(state.draft.body)}</textarea>
          <section class="section-card">
            <h3>Assumptions</h3>
            <p>${escapeHtml(state.draft.assumptions)}</p>
          </section>
          <div class="button-row">
            <button class="button secondary" type="button" data-back="spine">Back to spine</button>
            <button id="saveDraft" class="button secondary" type="button">Save draft edits</button>
            <button id="runReview" class="button" type="button">Run review gate</button>
          </div>
        </section>

        <aside class="card">
          <h2>Source Notes Used</h2>
          <p>${escapeHtml(state.draft.sourceNotesUsed)}</p>
        </aside>
      </div>
    `;

    bindBackButtons();
    document.getElementById("saveDraft").addEventListener("click", () => {
      state.draft.body = document.getElementById("draftBody").value;
      saveState();
      showToast("Draft edits saved locally.");
    });
    document.getElementById("runReview").addEventListener("click", () => {
      state.draft.body = document.getElementById("draftBody").value;
      state.review = buildReview();
      state.evidence.nextAction = "prepare output packet";
      setStep("review");
    });
  }

  function renderReview() {
    state.review = state.review || buildReview();
    saveState();

    app.innerHTML = `
      <div class="screen-grid">
        <section class="card stack">
          <div>
            <span class="pill ${state.review.status === "Ready to continue" ? "good" : "warn"}">${escapeHtml(state.review.status)}</span>
            <h2>Review Gate Summary</h2>
            <p>${escapeHtml(state.review.summary)}</p>
          </div>
          <div class="stack">
            ${state.review.findings
              .map(
                (finding) => `
                <article class="finding">
                  <h3>${escapeHtml(finding.label)}</h3>
                  <p><strong>${escapeHtml(finding.result)}:</strong> ${escapeHtml(finding.note)}</p>
                </article>
              `,
              )
              .join("")}
          </div>
          <div class="button-row">
            <button class="button secondary" type="button" data-back="draft">Back to draft</button>
            <button id="prepareOutput" class="button" type="button">Prepare output packet</button>
          </div>
        </section>

        <aside class="card">
          <h2>Review Rule</h2>
          <p>Findings guide the next action. They do not silently rewrite the source or promote the artifact without user approval.</p>
        </aside>
      </div>
    `;

    bindBackButtons();
    document.getElementById("prepareOutput").addEventListener("click", () => {
      state.output = buildOutputPacket();
      state.evidence.outputDelivered = "ready";
      state.evidence.nextAction = "deliver output and request feedback";
      setStep("output");
    });
  }

  function renderOutput() {
    state.output = state.output || buildOutputPacket();
    saveState();

    app.innerHTML = `
      <div class="screen-grid">
        <section class="card stack">
          <div>
            <span class="pill good">Output packet ready</span>
            <h2>Exportable Packet</h2>
            <p>Copy or download the packet. This is what the participant receives after the V1A run.</p>
          </div>
          <textarea id="outputPacket" class="export-box" aria-label="Output packet">${escapeHtml(state.output.markdown)}</textarea>
          <div class="button-row">
            <button class="button secondary" type="button" data-back="review">Back to review</button>
            <button id="copyOutput" class="button secondary" type="button">Copy packet</button>
            <button id="downloadOutput" class="button secondary" type="button">Download markdown</button>
            <button id="recordEvidence" class="button" type="button">Record evidence</button>
          </div>
        </section>

        <aside class="card">
          <h2>Delivery Checklist</h2>
          <ul class="check-list">
            <li>Source material preserved separately.</li>
            <li>Assumptions marked.</li>
            <li>Review gate included.</li>
            <li>Privacy reminder included.</li>
            <li>Next step visible.</li>
          </ul>
        </aside>
      </div>
    `;

    bindBackButtons();
    document.getElementById("copyOutput").addEventListener("click", () => {
      state.output.markdown = document.getElementById("outputPacket").value;
      saveState();
      copyText(state.output.markdown);
    });
    document.getElementById("downloadOutput").addEventListener("click", () => {
      state.output.markdown = document.getElementById("outputPacket").value;
      saveState();
      downloadText("governed-authoring-studio-v1a-output.md", state.output.markdown);
    });
    document.getElementById("recordEvidence").addEventListener("click", () => {
      state.output.markdown = document.getElementById("outputPacket").value;
      state.evidence.nextAction = "send feedback form";
      state.evidence.status = "delivered";
      setStep("evidence");
    });
  }

  function renderEvidence() {
    app.innerHTML = `
      <div class="screen-grid">
        <section class="card">
          <h2>Evidence Log</h2>
          <p>Record product-learning signals after the participant receives the output. Keep this non-sensitive.</p>
          <form id="evidenceForm" class="form-grid" autocomplete="off">
            ${selectField("inviteSent", "Invite sent", state.evidence.inviteSent, ["ready", "yes", "no", "scheduled"])}
            ${selectField("accepted", "Accepted", state.evidence.accepted, ["pending", "yes", "no"])}
            ${selectField("intakeReceived", "Intake received", state.evidence.intakeReceived, ["no", "yes", "partial", "needs clarification"])}
            ${selectField("outputDelivered", "Output delivered", state.evidence.outputDelivered, ["no", "ready", "yes", "in progress", "blocked"])}
            ${selectField("feedbackReceived", "Feedback received", state.evidence.feedbackReceived, ["no", "pending", "partial", "yes"])}
            ${selectField("ahaMoment", "Aha moment", state.evidence.ahaMoment, ["", "clear", "partial", "no", "unclear"])}
            ${selectField("wouldPay", "Would pay", state.evidence.wouldPay, ["", "yes", "maybe", "no", "unclear"])}
            ${selectField("privacyConcern", "Privacy concern", state.evidence.privacyConcern, ["", "none", "minor", "major", "unclear"])}
            ${inputField("mainFriction", "Main friction", state.evidence.mainFriction, "artifact type, source too thin, draft generic")}
            ${inputField("nextAction", "Next action", state.evidence.nextAction, "send feedback form")}
            ${selectField("status", "Status", state.evidence.status, ["invited", "accepted", "intake", "in production", "delivered", "feedback", "completed", "closed", "blocked"])}
            ${textareaField("operatorNotes", "Operator notes", state.evidence.operatorNotes, "Short, factual, non-sensitive notes only.")}
          </form>
          <div class="button-row">
            <button class="button secondary" type="button" data-back="output">Back to output</button>
            <button id="saveEvidence" class="button" type="button">Save evidence</button>
          </div>
        </section>

        <aside class="card stack">
          <h2>Tracker Row</h2>
          <pre id="trackerRow" class="code-box">${escapeHtml(buildTrackerRow())}</pre>
          <button id="copyTrackerRow" class="button secondary" type="button">Copy tracker row</button>
        </aside>
      </div>
    `;

    bindBackButtons();
    document.getElementById("saveEvidence").addEventListener("click", () => {
      captureEvidenceForm();
      if (state.evidence.feedbackReceived === "yes") {
        state.evidence.status = "completed";
      }
      saveState();
      render();
      showToast("Evidence saved locally.");
    });
    document.getElementById("copyTrackerRow").addEventListener("click", () => {
      captureEvidenceForm();
      saveState();
      copyText(buildTrackerRow());
    });
  }

  function captureIntakeForm() {
    Object.keys(state.intake).forEach((key) => {
      const input = document.getElementById(key);
      if (!input) return;
      state.intake[key] = input.type === "checkbox" ? input.checked : input.value;
    });
  }

  function captureEvidenceForm() {
    Object.keys(state.evidence).forEach((key) => {
      const input = document.getElementById(key);
      if (!input) return;
      state.evidence[key] = input.value;
    });
  }

  function bindBackButtons() {
    document.querySelectorAll("[data-back]").forEach((button) => {
      button.addEventListener("click", () => setStep(button.dataset.back));
    });
  }

  function inputField(id, label, value, placeholder, required = false, type = "text") {
    return `
      <div class="field ${id === "mainFriction" || id === "nextAction" ? "" : ""}">
        <label for="${id}">${escapeHtml(label)}${required ? " *" : ""}</label>
        <input id="${id}" type="${type}" value="${escapeAttr(value || "")}" placeholder="${escapeAttr(placeholder || "")}" ${required ? "required" : ""}>
      </div>
    `;
  }

  function textareaField(id, label, value, placeholder, required = false) {
    return `
      <div class="field full">
        <label for="${id}">${escapeHtml(label)}${required ? " *" : ""}</label>
        <textarea id="${id}" placeholder="${escapeAttr(placeholder || "")}" ${required ? "required" : ""}>${escapeHtml(value || "")}</textarea>
      </div>
    `;
  }

  function selectField(id, label, value, options) {
    return `
      <div class="field">
        <label for="${id}">${escapeHtml(label)}</label>
        <select id="${id}">
          ${options.map((option) => `<option value="${escapeAttr(option)}" ${option === value ? "selected" : ""}>${escapeHtml(option || "not recorded")}</option>`).join("")}
        </select>
      </div>
    `;
  }

  function summaryItem(term, value) {
    return `
      <dl class="summary-item">
        <dt>${escapeHtml(term)}</dt>
        <dd>${escapeHtml(value || "not set")}</dd>
      </dl>
    `;
  }

  function buildOperatorPacket() {
    const warnings = [];
    const sourceWordCount = countWords(state.intake.sourceNotes);

    if (!state.intake.privacyAck) warnings.push("Privacy acknowledgment is incomplete.");
    if (!state.intake.sourceNotes.trim()) warnings.push("Source material is missing.");
    else if (sourceWordCount < 120) warnings.push("Source is thin. Operator may need clarification.");
    if (!state.intake.desiredOutput.trim()) warnings.push("Desired output is unclear.");
    if (!state.intake.audience.trim()) warnings.push("Audience is missing.");
    if (state.intake.artifactType === "not sure yet") warnings.push("Artifact type is provisional.");

    const hardBlock = !state.intake.privacyAck || !state.intake.sourceNotes.trim();
    const status = hardBlock ? "Needs Clarification" : "Accepted";
    const title = state.intake.projectTitle || "Untitled artifact";

    return {
      status,
      sourceSufficiency: sourceWordCount >= 300 ? "strong" : sourceWordCount >= 120 ? "usable" : "thin",
      audienceClarity: state.intake.audience.trim() ? "named" : "missing",
      privacyStatus: state.intake.privacyAck ? "acknowledged" : "missing",
      warnings,
      nextAction: status === "Accepted" ? "Create provisional spine" : "Request clarification",
      clarifiedDirection: `${title} is being shaped as a ${state.intake.artifactType} for ${state.intake.audience || "a still-unnamed audience"}. The first output should make the project easier to continue, not pretend the full artifact is complete.`,
      operatorNotes: warnings.length
        ? `Proceed carefully. ${warnings.join(" ")}`
        : "Minimum V1A packet is present. Proceed to spine while marking assumptions and preserving source separation.",
    };
  }

  function buildSpine() {
    const type = state.intake.artifactType;
    const title = state.intake.projectTitle || titleFromSource();
    const central = state.intake.desiredOutput || state.intake.whyItMatters || "Turn the source material into a clearer artifact direction.";
    const themes = extractThemes();
    const sections = sectionsForType(type, themes);

    return {
      title,
      centralDirection: central,
      structureSummary: `${title} becomes a ${type} organized around ${themes.slice(0, 3).join(", ") || "the strongest recurring ideas in the source"}.`,
      sections,
      assumptions: buildAssumptions(),
      sourceLineage: `Spine derived from source notes (${countWords(state.intake.sourceNotes)} words), desired output, audience notes, constraints, and phrases to preserve. Original source remains separate.`,
    };
  }

  function sectionsForType(type, themes) {
    const cleanedThemes = themes.length ? themes : ["core idea", "audience need", "practical path", "next step"];
    if (type === "essay series") {
      return cleanedThemes.slice(0, 5).map((theme, index) => ({
        title: index === 0 ? `Opening Essay: ${capitalize(theme)}` : `Essay ${index + 1}: ${capitalize(theme)}`,
        purpose: index === 0 ? "Establish the central argument and why it matters." : "Develop one part of the argument with concrete support.",
        seedPoints: `Seed points: ${theme}; audience question; example needed.`,
      }));
    }
    if (type === "course or teaching outline") {
      return cleanedThemes.slice(0, 5).map((theme, index) => ({
        title: `Module ${index + 1}: ${capitalize(theme)}`,
        purpose: index === 0 ? "Orient the learner and define the outcome." : "Move the learner through one practical concept or skill.",
        seedPoints: `Lesson seed: ${theme}; learner action; exercise or example needed.`,
      }));
    }
    return cleanedThemes.slice(0, 6).map((theme, index) => ({
      title: index === 0 ? `Opening: ${capitalize(theme)}` : `Chapter ${index + 1}: ${capitalize(theme)}`,
      purpose: index === 0 ? "Open the artifact with the clearest version of the problem and promise." : "Develop a distinct layer of the manuscript argument.",
      seedPoints: `Seed points: ${theme}; source fragment; transition question.`,
    }));
  }

  function buildDraft() {
    const spine = state.spine || buildSpine();
    const selected = spine.sections[0];
    const sourceExcerpt = trimToWords(state.intake.sourceNotes, 120);
    const tone = state.intake.desiredTone || "clear and direct";
    const avoid = state.intake.mustNotSoundLike || "generic or over-polished";
    const phrase = state.intake.phrasesToPreserve ? `A phrase to preserve is: "${state.intake.phrasesToPreserve.split(/[.\n]/)[0]}."` : "";

    const body = [
      `# ${selected.title}`,
      "",
      `This section opens the artifact by giving the idea a stable first shape. The goal is not to finish the whole work at once. The goal is to make the project specific enough that the next section can be written on purpose.`,
      "",
      `The source material points toward this direction: ${state.intake.desiredOutput || "a more structured artifact that makes the idea usable."}`,
      "",
      state.intake.audience
        ? `The audience is ${state.intake.audience}. That matters because the structure should answer their real confusion instead of displaying every thought the project contains.`
        : "Audience is still an assumption. The draft should stay provisional until the user confirms who this is for.",
      "",
      sourceExcerpt
        ? `Source signal used: ${sourceExcerpt}`
        : "Needs source: the first section needs more concrete user material before it can become fully specific.",
      "",
      `A useful first draft should sound ${tone} and should not sound like ${avoid}. ${phrase}`,
      "",
      `Assumption: this opening section should clarify the project before it tries to persuade, teach, or launch anything. If that assumption is wrong, the spine should change before more drafting happens.`,
    ]
      .filter(Boolean)
      .join("\n");

    return {
      title: selected.title,
      whyThisSection: state.intake.firstSectionPreference === "recommend the best first section"
        ? "This section was chosen because it creates the clearest first value moment."
        : `This follows the requested preference: ${state.intake.firstSectionPreference}.`,
      body,
      sourceNotesUsed: sourceExcerpt || "No substantial source notes yet. Request more material before production delivery.",
      assumptions: "The draft is assisted output, not source. It marks uncertainty and should be approved before further sections are drafted.",
    };
  }

  function buildReview() {
    const draftBody = state.draft?.body || "";
    const findings = [];
    findings.push({
      label: "Clarity",
      result: countWords(draftBody) > 120 ? "usable" : "thin",
      note: countWords(draftBody) > 120 ? "The section has a recognizable opening direction." : "The draft needs more source and development before delivery.",
    });
    findings.push({
      label: "Coherence",
      result: state.spine ? "aligned" : "needs spine",
      note: state.spine ? "The draft follows the first spine section." : "A spine should exist before this draft is reviewed.",
    });
    findings.push({
      label: "Audience fit",
      result: state.intake.audience ? "named" : "unclear",
      note: state.intake.audience ? "Audience is visible in the draft." : "Audience should be clarified before expanding the artifact.",
    });
    findings.push({
      label: "Voice preservation",
      result: state.intake.desiredTone ? "provisional" : "weak",
      note: state.intake.desiredTone ? `Tone target is ${state.intake.desiredTone}.` : "Tone needs a clearer user signal.",
    });
    findings.push({
      label: "Overclaiming risk",
      result: "controlled",
      note: "The draft uses assumptions and avoids promising publication or guaranteed outcomes.",
    });
    findings.push({
      label: "Missing examples",
      result: state.intake.importantFragments || state.intake.existingStructure ? "some support" : "needs examples",
      note: state.intake.importantFragments || state.intake.existingStructure ? "Some source anchors are present." : "Ask the user for one concrete example before deeper drafting.",
    });

    const ready = findings.filter((finding) => ["thin", "unclear", "weak", "needs examples"].includes(finding.result)).length < 2;
    return {
      status: ready ? "Ready to continue" : "Usable with revision",
      summary: ready
        ? "The first section is specific enough for user review and export."
        : "The first section can be exported as a prototype packet, but the next pass needs more user source or clearer audience detail.",
      findings,
      confidence: ready ? "Medium" : "Low",
    };
  }

  function buildOutputPacket() {
    const today = new Date().toISOString().slice(0, 10);
    const spine = state.spine || buildSpine();
    const draft = state.draft || buildDraft();
    const review = state.review || buildReview();

    const markdown = `# Governed Authoring Studio V1A Output Packet

## Output Header

- Project title: ${state.intake.projectTitle || "Untitled artifact"}
- Artifact type: ${state.intake.artifactType}
- Prepared for: ${state.intake.name || state.participant.displayName}
- Prepared on: ${today}
- Operator: V1A operator
- Status: ${review.status}
- Version: 0.1 local prototype
- Privacy level: Private by default

## Project Summary

### User starting point

${trimToWords(state.intake.sourceNotes, 90) || "Source material not yet supplied."}

### Desired output

${state.intake.desiredOutput || "Not specified."}

### Target audience

${state.intake.audience || "Needs confirmation."}

### Tone or style

${state.intake.desiredTone || "Needs confirmation."}

### Constraints

${state.intake.constraints || "No constraints supplied yet."}

### Assumptions made

${spine.assumptions}

## Clarified Direction

${spine.centralDirection}

## Artifact Spine

${spine.sections
  .map((section, index) => `${index + 1}. ${section.title}\n   - Purpose: ${section.purpose}\n   - Seeds: ${section.seedPoints}`)
  .join("\n\n")}

## First Draft Section

### ${draft.title}

${draft.body}

## Review Gate Summary

- Review status: ${review.status}
- Confidence level: ${review.confidence}

${review.findings.map((finding) => `- ${finding.label}: ${finding.result}. ${finding.note}`).join("\n")}

## User Next Steps

1. Confirm whether the spine reflects the idea.
2. Mark anything that feels generic, wrong, or over-smoothed.
3. Add one concrete example for the first section.
4. Decide whether to continue with the next section or revise the spine.

## Privacy Reminder

Your content is private by default. Your submitted source material and this generated output are kept separate. Nothing is shared publicly without your approval. Because V1A is operator-assisted, a human operator may have reviewed your submitted material to prepare this packet.
`;

    return { markdown };
  }

  function buildTrackerRow() {
    const e = state.evidence;
    return `| 001 | ${e.inviteSent || ""} | ${e.accepted || ""} | ${e.intakeReceived || ""} | ${e.outputDelivered || ""} | ${e.feedbackReceived || ""} | ${e.ahaMoment || ""} | ${e.wouldPay || ""} | ${e.privacyConcern || ""} | ${e.mainFriction || ""} | ${e.nextAction || ""} | ${e.status || ""} |`;
  }

  function buildInviteText() {
    return `Justin, I am testing an early version of Governed Authoring Studio, a guided workflow for people with serious unfinished ideas.

The trial is simple: you share rough notes, fragments, or a foggy project idea. I use the workflow to turn that material into a clear direction, a structured artifact spine, one draft section, a review summary, and suggested next steps.

This is not a public app yet. It is concierge-assisted, which means a human operator may review what you submit. Please do not send passwords, financial details, medical records, legal documents, confidential third-party material, or anything you would not want reviewed during this test.

The goal is to learn whether this helps people get unstuck and make real progress on work that has been sitting in fragments.

If you are open to trying it, the intake asks for artifact type, rough notes, desired output, audience, tone, constraints, and a privacy acknowledgment.`;
  }

  function extractThemes() {
    const text = [
      state.intake.importantFragments,
      state.intake.existingStructure,
      state.intake.desiredOutput,
      state.intake.whyItMatters,
      state.intake.phrasesToPreserve,
    ]
      .join(" ")
      .toLowerCase();
    const words = text
      .replace(/[^a-z0-9\s-]/g, " ")
      .split(/\s+/)
      .filter((word) => word.length > 4 && !commonWords.has(word));
    const counts = new Map();
    words.forEach((word) => counts.set(word, (counts.get(word) || 0) + 1));
    const ranked = [...counts.entries()].sort((a, b) => b[1] - a[1]).map(([word]) => word);
    return [...new Set(ranked)].slice(0, 6);
  }

  function buildAssumptions() {
    const assumptions = [];
    if (state.intake.artifactType === "not sure yet") assumptions.push("Artifact type is provisional.");
    if (!state.intake.audienceOutcome) assumptions.push("Audience outcome needs confirmation.");
    if (!state.intake.importantFragments) assumptions.push("Important fragments were not marked, so spine emphasis is inferred.");
    if (!state.intake.existingStructure) assumptions.push("No existing structure was supplied, so section order is generated.");
    if (!assumptions.length) assumptions.push("Spine uses submitted source, desired output, audience, and constraints.");
    return assumptions.join(" ");
  }

  function titleFromSource() {
    const firstLine = state.intake.sourceNotes.split(/\n+/).map((line) => line.trim()).find(Boolean);
    if (!firstLine) return "Untitled artifact";
    return trimToWords(firstLine, 7).replace(/[.?!,:;]+$/, "");
  }

  function countWords(text) {
    return (text || "").trim().split(/\s+/).filter(Boolean).length;
  }

  function trimToWords(text, maxWords) {
    const words = (text || "").trim().split(/\s+/).filter(Boolean);
    if (words.length <= maxWords) return words.join(" ");
    return `${words.slice(0, maxWords).join(" ")}...`;
  }

  function capitalize(text) {
    if (!text) return "";
    return text.charAt(0).toUpperCase() + text.slice(1);
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function escapeAttr(value) {
    return escapeHtml(value).replace(/"/g, "&quot;");
  }

  function copyText(text) {
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text).then(
        () => showToast("Copied to clipboard."),
        () => fallbackCopy(text),
      );
    } else {
      fallbackCopy(text);
    }
  }

  function fallbackCopy(text) {
    const textarea = document.createElement("textarea");
    textarea.value = text;
    textarea.setAttribute("readonly", "");
    textarea.style.position = "fixed";
    textarea.style.opacity = "0";
    document.body.appendChild(textarea);
    textarea.select();
    try {
      document.execCommand("copy");
      showToast("Copied to clipboard.");
    } catch (error) {
      showToast("Copy failed. Select and copy manually.");
    } finally {
      textarea.remove();
    }
  }

  function downloadText(filename, text) {
    const blob = new Blob([text], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }

  let toastTimer = null;
  function showToast(message) {
    toast.textContent = message;
    toast.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toast.classList.remove("show"), 2400);
  }

  const commonWords = new Set([
    "about",
    "after",
    "again",
    "because",
    "before",
    "being",
    "could",
    "first",
    "from",
    "have",
    "helps",
    "into",
    "should",
    "their",
    "there",
    "these",
    "thing",
    "those",
    "through",
    "under",
    "where",
    "which",
    "while",
    "would",
  ]);

  render();
})();
