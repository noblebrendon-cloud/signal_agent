(function (root) {
  "use strict";

  const PROTOTYPE_BRIDGE_SCHEMA_VERSION = "governed_authoring.prototype_bridge.v1";
  const PROTOTYPE_RESULT_SCHEMA_VERSION = "governed_authoring.prototype_result.v1";
  const SOURCE_PACKET_SCHEMA_VERSION = "governed_authoring.source_packet.v1";

  function asObject(value) {
    return value && Object.prototype.toString.call(value) === "[object Object]" ? value : {};
  }

  function asArray(value) {
    return Array.isArray(value) ? value : [];
  }

  function stringValue(value) {
    return typeof value === "string" ? value : "";
  }

  function booleanValue(value) {
    return typeof value === "boolean" ? value : false;
  }

  function firstString() {
    for (const value of arguments) {
      if (typeof value === "string" && value.trim()) {
        return value.trim();
      }
    }
    return "";
  }

  function normalizeToken(value) {
    return stringValue(value).trim().toLowerCase().replace(/[-\s]+/g, "_");
  }

  function cleanRefs() {
    const refs = [];
    const visit = (value) => {
      if (typeof value === "string" && value.trim()) {
        refs.push(value.trim());
        return;
      }
      if (Array.isArray(value)) {
        value.forEach(visit);
        return;
      }
      const item = asObject(value);
      const ref = firstString(item.evidence_id, item.evidenceId, item.ref, item.uri, item.id);
      if (ref) {
        refs.push(ref);
      }
    };
    Array.from(arguments).forEach(visit);
    return Array.from(new Set(refs));
  }

  function normalizeRequestedStatus(value) {
    const lowered = normalizeToken(value);
    if (["approved", "approve", "publication_ready", "publish_ready", "ready_to_publish"].includes(lowered)) {
      return "approved";
    }
    if (["provisional", "unverified", "draft"].includes(lowered)) {
      return "provisional";
    }
    if (["rejected", "deferred"].includes(lowered)) {
      return lowered;
    }
    return "provisional";
  }

  function normalizeDraftMode(value, requestedStatus) {
    const lowered = normalizeToken(value);
    if (["publication_ready", "publish_ready", "approved"].includes(lowered)) {
      return "publication_ready";
    }
    if (["provisional", "unverified", "draft"].includes(lowered)) {
      return "provisional";
    }
    return requestedStatus === "approved" ? "publication_ready" : "provisional";
  }

  function normalizeReviewDecision(value) {
    const lowered = normalizeToken(value);
    if (["approved", "approve", "ready_to_continue", "ready", "accepted"].includes(lowered)) {
      return "approved";
    }
    if (["rejected", "reject", "blocked"].includes(lowered)) {
      return "rejected";
    }
    if (["deferred", "defer", "usable_with_revision", "needs_revision"].includes(lowered)) {
      return "deferred";
    }
    return lowered;
  }

  function sourceTextFromIntake(intake) {
    return [
      ["source notes", "sourceNotes"],
      ["important fragments", "importantFragments"],
      ["existing structure", "existingStructure"],
    ]
      .map(([label, key]) => {
        const value = stringValue(intake[key]).trim();
        return value ? `${label}: ${value}` : "";
      })
      .filter(Boolean)
      .join("\n\n");
  }

  function stableStringify(value) {
    if (Array.isArray(value)) {
      return `[${value.map(stableStringify).join(",")}]`;
    }
    if (value && Object.prototype.toString.call(value) === "[object Object]") {
      return `{${Object.keys(value)
        .sort()
        .map((key) => `${JSON.stringify(key)}:${stableStringify(value[key])}`)
        .join(",")}}`;
    }
    return JSON.stringify(value);
  }

  function shortHash(value) {
    const text = stableStringify(value);
    let hash = 2166136261;
    for (let index = 0; index < text.length; index += 1) {
      hash ^= text.charCodeAt(index);
      hash = Math.imul(hash, 16777619);
    }
    return (hash >>> 0).toString(16).padStart(8, "0").slice(0, 8);
  }

  function evidenceRefsFromPrototype(packet) {
    const intake = asObject(packet.intake);
    const evidence = asObject(packet.evidence);
    const governance = asObject(packet.governance);
    const refs = cleanRefs(
      packet.evidence_refs,
      packet.evidenceRefs,
      packet.evidenceReferences,
      intake.evidence_refs,
      intake.evidenceRefs,
      evidence.refs,
      evidence.evidence_refs,
      evidence.evidenceRefs,
      evidence.references,
      governance.evidence_refs,
      governance.evidenceRefs,
    );
    asArray(packet.source_material).forEach((source) => {
      refs.push(...cleanRefs(asObject(source).evidence_refs, asObject(source).evidenceRefs));
    });
    asArray(packet.sourceMaterial).forEach((source) => {
      refs.push(...cleanRefs(asObject(source).evidence_refs, asObject(source).evidenceRefs));
    });
    asArray(packet.claims).forEach((claim) => {
      refs.push(...cleanRefs(asObject(claim).evidence_refs, asObject(claim).evidenceRefs));
    });
    return Array.from(new Set(refs));
  }

  function sourceMaterialFromPrototype(packet, evidenceRefs) {
    const explicit = asArray(packet.source_material).length ? asArray(packet.source_material) : asArray(packet.sourceMaterial);
    if (explicit.length) {
      return explicit.map((item) => {
        const source = asObject(item);
        const sourceRefs = cleanRefs(source.evidence_refs, source.evidenceRefs);
        return {
          source_id: firstString(source.source_id, source.sourceId, source.id) || `prototype.source.${shortHash(source)}`,
          text: stringValue(source.text),
          uri: firstString(source.uri, source.source_uri, source.sourceUri),
          content_hash: firstString(source.content_hash, source.contentHash),
          evidence_refs: sourceRefs.length ? sourceRefs : evidenceRefs.slice(),
        };
      });
    }

    const intake = asObject(packet.intake);
    const text = sourceTextFromIntake(intake);
    const uri = firstString(intake.sourceUri, intake.source_uri, packet.source_uri, packet.sourceUri);
    if (!text && !uri) {
      return [];
    }
    const sourceId = firstString(intake.sourceId, intake.source_id, packet.source_packet_id);
    return [
      {
        source_id: sourceId || `prototype.source.${shortHash({ text, uri })}`,
        text,
        uri,
        content_hash: "",
        evidence_refs: evidenceRefs.slice(),
      },
    ];
  }

  function claimsFromPrototype(packet, evidenceRefs, requestedStatus) {
    const explicit = asArray(packet.claims);
    if (explicit.length) {
      return explicit.map((item) => {
        const claim = asObject(item);
        const statement = firstString(claim.statement, claim.core_assertion, claim.coreAssertion);
        const claimRefs = cleanRefs(claim.evidence_refs, claim.evidenceRefs);
        return {
          claim_id: firstString(claim.claim_id, claim.claimId, claim.id) || `prototype.claim.${shortHash(statement)}`,
          statement,
          evidence_refs: claimRefs.length ? claimRefs : evidenceRefs.slice(),
          status: firstString(claim.status) || (requestedStatus === "approved" ? "publication_ready" : "provisional"),
        };
      });
    }

    const intake = asObject(packet.intake);
    const sourceText = sourceTextFromIntake(intake);
    const statement = firstString(intake.desiredOutput, intake.whyItMatters, sourceText, packet.title);
    if (!statement) {
      return [];
    }
    return [
      {
        claim_id: `prototype.claim.${shortHash({ statement, source: sourceText })}`,
        statement,
        evidence_refs: evidenceRefs.slice(),
        status: requestedStatus === "approved" ? "publication_ready" : "provisional",
      },
    ];
  }

  function normalizeTension(item) {
    const tension = asObject(item);
    return {
      tension_id: firstString(tension.tension_id, tension.tensionId, tension.id) || `prototype.tension.${shortHash(tension)}`,
      description: firstString(tension.description, tension.note, tension.message),
      blocking: booleanValue(tension.blocking),
      severity: firstString(tension.severity) || "medium",
    };
  }

  function tensionsFromPrototype(packet) {
    const governance = asObject(packet.governance);
    const review = asObject(packet.review);
    const raw =
      asArray(packet.unresolved_tensions).length ? asArray(packet.unresolved_tensions) :
      asArray(packet.unresolvedTensions).length ? asArray(packet.unresolvedTensions) :
      asArray(packet.tensions).length ? asArray(packet.tensions) :
      asArray(governance.unresolved_tensions).length ? asArray(governance.unresolved_tensions) :
      asArray(governance.unresolvedTensions).length ? asArray(governance.unresolvedTensions) :
      asArray(review.unresolved_tensions).length ? asArray(review.unresolved_tensions) :
      asArray(review.unresolvedTensions);
    return raw.map(normalizeTension);
  }

  function reviewSource(packet) {
    const review = asObject(packet.review);
    for (const value of [
      packet.review_decision,
      packet.reviewDecision,
      packet.human_review,
      packet.humanReview,
      review.review_decision,
      review.reviewDecision,
      review.human_review,
      review.humanReview,
    ]) {
      const source = asObject(value);
      if (Object.keys(source).length) {
        return source;
      }
    }
    if (["actor_id", "actorId", "actor_type", "actorType", "decision", "self_certified", "selfCertified"].some((key) => key in review)) {
      return review;
    }
    return {};
  }

  function reviewDecisionFromPrototype(packet) {
    const source = reviewSource(packet);
    if (!Object.keys(source).length) {
      return null;
    }
    const review = asObject(packet.review);
    return {
      review_decision_id:
        firstString(source.review_decision_id, source.reviewDecisionId, source.id) || `prototype.review.${shortHash(source)}`,
      actor_id: firstString(source.actor_id, source.actorId, source.reviewer_id, source.reviewerId),
      actor_type: firstString(source.actor_type, source.actorType, source.reviewer_type, source.reviewerType),
      role: firstString(source.role) || "authoring_reviewer",
      scope: firstString(source.scope) || "governed_authoring_output",
      decision: normalizeReviewDecision(firstString(source.decision, source.status, review.status)),
      timestamp: firstString(source.timestamp, source.reviewed_at, source.reviewedAt, source.reviewTimestamp),
      self_certified: booleanValue(source.self_certified) || booleanValue(source.selfCertified),
    };
  }

  function buildSourcePacket(prototypePacket) {
    const packet = asObject(prototypePacket);
    const intake = asObject(packet.intake);
    const governance = asObject(packet.governance);
    const requestedStatus = normalizeRequestedStatus(
      firstString(
        governance.requested_output_status,
        governance.requestedOutputStatus,
        packet.requested_output_status,
        packet.requestedOutputStatus,
        packet.output_status,
        packet.outputStatus,
      ),
    );
    const draftMode = normalizeDraftMode(
      firstString(governance.draft_mode, governance.draftMode, packet.draft_mode, packet.draftMode),
      requestedStatus,
    );
    const evidenceRefs = evidenceRefsFromPrototype(packet);
    return {
      schema_version: SOURCE_PACKET_SCHEMA_VERSION,
      source_packet_id:
        firstString(packet.source_packet_id, packet.sourcePacketId, packet.id) ||
        `prototype.source_packet.${shortHash(packet)}`,
      requested_output_status: requestedStatus,
      draft_mode: draftMode,
      title: firstString(intake.projectTitle, packet.title),
      source_material: sourceMaterialFromPrototype(packet, evidenceRefs),
      claims: claimsFromPrototype(packet, evidenceRefs, requestedStatus),
      evidence_refs: evidenceRefs,
      unresolved_tensions: tensionsFromPrototype(packet),
      review_decision: reviewDecisionFromPrototype(packet),
    };
  }

  function hasSourceMaterial(sourcePacket) {
    return asArray(sourcePacket.source_material).some((source) => {
      const item = asObject(source);
      return Boolean(stringValue(item.text).trim() || stringValue(item.uri).trim());
    });
  }

  function allEvidenceRefs(sourcePacket) {
    const refs = cleanRefs(sourcePacket.evidence_refs);
    asArray(sourcePacket.source_material).forEach((source) => refs.push(...cleanRefs(asObject(source).evidence_refs)));
    asArray(sourcePacket.claims).forEach((claim) => refs.push(...cleanRefs(asObject(claim).evidence_refs)));
    return Array.from(new Set(refs));
  }

  function isSelfApproval(reviewDecision) {
    const review = asObject(reviewDecision);
    if (!Object.keys(review).length) {
      return false;
    }
    const actorType = normalizeToken(review.actor_type || review.actorType || review.reviewer_type || review.reviewerType);
    const decision = normalizeReviewDecision(firstString(review.decision, review.status));
    return (
      decision === "approved" &&
      (actorType === "generator" || actorType === "model" || booleanValue(review.self_certified) || booleanValue(review.selfCertified))
    );
  }

  function validateSourcePacket(sourcePacket, prototypePacket) {
    const packet = asObject(sourcePacket);
    const issues = [];
    if (!hasSourceMaterial(packet)) {
      issues.push({
        severity: "error",
        code: "missing_source_material",
        message: "Prototype packet lacks source material for backend authoring.",
      });
    }
    if (packet.requested_output_status === "approved" && !allEvidenceRefs(packet).length) {
      issues.push({
        severity: "error",
        code: "missing_evidence_refs",
        message: "Publication-ready prototype packet lacks evidence references.",
      });
    }
    if (isSelfApproval(packet.review_decision)) {
      issues.push({
        severity: "error",
        code: "generator_self_approval",
        message: "Generator/model/self-certified review cannot satisfy human approval.",
      });
    }
    const intake = asObject(asObject(prototypePacket).intake);
    if (Object.keys(intake).length && !booleanValue(intake.privacyAck)) {
      issues.push({
        severity: "warning",
        code: "privacy_ack_missing",
        message: "Prototype intake privacy acknowledgement is not present.",
      });
    }
    return issues;
  }

  function buildBridgePacket(prototypePacket) {
    const sourcePacket = buildSourcePacket(prototypePacket);
    return {
      schema_version: PROTOTYPE_BRIDGE_SCHEMA_VERSION,
      source_packet: sourcePacket,
      bridge_issues: validateSourcePacket(sourcePacket, prototypePacket),
    };
  }

  function reviewStatusForOutput(outputStatus) {
    if (outputStatus === "approved") {
      return "Approved by backend review";
    }
    if (outputStatus === "deferred") {
      return "Deferred by backend review";
    }
    if (outputStatus === "rejected") {
      return "Rejected by backend review";
    }
    if (outputStatus === "provisional") {
      return "Provisional backend draft";
    }
    return "Unknown backend result";
  }

  function backendManifestFromPacket(packet) {
    const value = asObject(packet);
    if (asObject(value.prototype_result).schema_version === PROTOTYPE_RESULT_SCHEMA_VERSION) {
      return asObject(value.prototype_result);
    }
    if (value.schema_version === PROTOTYPE_RESULT_SCHEMA_VERSION) {
      return value;
    }
    if (Object.keys(asObject(value.output_manifest)).length) {
      return asObject(value.output_manifest);
    }
    if (Object.keys(asObject(asObject(value.backend_result).output_manifest)).length) {
      return asObject(asObject(value.backend_result).output_manifest);
    }
    return value;
  }

  function importBackendResultPacket(resultPacket) {
    const manifest = backendManifestFromPacket(resultPacket);
    const outputStatus = normalizeRequestedStatus(firstString(manifest.output_status, manifest.outputStatus));
    return {
      schema_version: PROTOTYPE_RESULT_SCHEMA_VERSION,
      backend_output_manifest_id: stringValue(manifest.output_manifest_id),
      source_packet_id: stringValue(manifest.source_packet_id),
      draft_candidate_id: stringValue(manifest.draft_candidate_id),
      review_decision_id: stringValue(manifest.review_decision_id),
      output_status: outputStatus,
      decision: stringValue(manifest.decision),
      decision_reason: stringValue(manifest.decision_reason),
      review_status: firstString(manifest.review_status, manifest.reviewStatus) || reviewStatusForOutput(outputStatus),
      evidence_refs: cleanRefs(manifest.evidence_refs, manifest.evidenceRefs),
      unresolved_tensions: asArray(manifest.unresolved_tensions).length
        ? asArray(manifest.unresolved_tensions).map(normalizeTension)
        : asArray(manifest.unresolvedTensions).map(normalizeTension),
      messages: asArray(manifest.messages).map((message) => String(message)),
      canonical_ledger_entry_id: stringValue(manifest.canonical_ledger_entry_id),
    };
  }

  function parseJsonText(text) {
    try {
      return { ok: true, payload: JSON.parse(text) };
    } catch (error) {
      return { ok: false, error: error instanceof Error ? error.message : String(error) };
    }
  }

  function toPrettyJson(value) {
    return JSON.stringify(value, null, 2);
  }

  const api = {
    PROTOTYPE_BRIDGE_SCHEMA_VERSION,
    PROTOTYPE_RESULT_SCHEMA_VERSION,
    SOURCE_PACKET_SCHEMA_VERSION,
    buildSourcePacket,
    buildBridgePacket,
    importBackendResultPacket,
    parseJsonText,
    toPrettyJson,
    validateSourcePacket,
  };

  root.GovernedAuthoringPrototypeBridge = api;
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
})(typeof window !== "undefined" ? window : globalThis);
