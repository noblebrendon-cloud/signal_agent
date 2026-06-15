# Governed Authoring Prototype Packet Contract

This contract documents the packet shapes supported by the Phase 7 bridge. It is intentionally permissive because the static prototype stores local browser state, not formal backend records.

## Prototype Input Shape

The bridge accepts a dictionary shaped like the static prototype localStorage state or a smaller export packet with equivalent fields.

Common top-level fields:

```json
{
  "sourcePacketId": "prototype.packet.001",
  "governance": {
    "requestedOutputStatus": "provisional",
    "draftMode": "provisional"
  },
  "intake": {
    "projectTitle": "Prototype bridge packet",
    "sourceNotes": "Source text...",
    "importantFragments": "Source anchors...",
    "existingStructure": "Existing outline...",
    "desiredOutput": "Requested output...",
    "audience": "Target audience",
    "privacyAck": true
  },
  "evidenceRefs": ["evidence:prototype.source.001"],
  "unresolvedTensions": [],
  "reviewDecision": null
}
```

The bridge also accepts snake_case variants for key fields, such as `source_packet_id`, `requested_output_status`, `draft_mode`, `evidence_refs`, `unresolved_tensions`, and `review_decision`.

## Backend Source Packet Output

`prototype_to_source_packet(packet)` emits:

```json
{
  "schema_version": "governed_authoring.source_packet.v1",
  "source_packet_id": "prototype.packet.001",
  "requested_output_status": "provisional",
  "draft_mode": "provisional",
  "title": "Prototype bridge packet",
  "source_material": [],
  "claims": [],
  "evidence_refs": [],
  "unresolved_tensions": [],
  "review_decision": null
}
```

This output is compatible with `GovernedAuthoringRuntime.run(...)`.

## Supported Field Mappings

| Prototype field | Backend field |
| --- | --- |
| `sourcePacketId`, `source_packet_id`, `id` | `source_packet_id` |
| `governance.requestedOutputStatus`, `requestedOutputStatus` | `requested_output_status` |
| `governance.draftMode`, `draftMode` | `draft_mode` |
| `intake.projectTitle`, `title` | `title` |
| `intake.sourceNotes`, `intake.importantFragments`, `intake.existingStructure` | `source_material[].text` |
| `sourceMaterial`, `source_material` | `source_material` |
| `claims` | `claims` |
| `evidenceRefs`, `evidence_refs`, `evidence.references` | `evidence_refs` |
| `unresolvedTensions`, `unresolved_tensions`, `governance.unresolvedTensions` | `unresolved_tensions` |
| `reviewDecision`, `review_decision`, `humanReview` | `review_decision` |

## Status Normalization

Requested output status:

- `approved`, `approve`, `publication_ready`, `publish_ready`, `ready_to_publish` -> `approved`
- `provisional`, `unverified`, `draft` -> `provisional`
- `rejected` -> `rejected`
- `deferred` -> `deferred`

Draft mode:

- `publication_ready`, `publish_ready`, `approved` -> `publication_ready`
- `provisional`, `unverified`, `draft` -> `provisional`

Review decision:

- `approved`, `approve`, `ready_to_continue`, `ready`, `accepted` -> `approved`
- `rejected`, `reject`, `blocked` -> `rejected`
- `deferred`, `defer`, `usable_with_revision`, `needs_revision` -> `deferred`

## Bridge Issues

`bridge_prototype_packet(packet)` returns:

```json
{
  "schema_version": "governed_authoring.prototype_bridge.v1",
  "source_packet": {},
  "bridge_issues": []
}
```

Current bridge issue codes:

| Code | Severity | Meaning |
| --- | --- | --- |
| `missing_source_material` | `error` | The packet lacks usable source material. |
| `missing_evidence_refs` | `error` | A publication-ready packet lacks evidence refs. |
| `generator_self_approval` | `error` | Review authority is generator/model/self-certified. |
| `privacy_ack_missing` | `warning` | Prototype intake privacy acknowledgement is missing. |

Passing `strict=True` raises `PrototypeBridgeError` for error-level issues.

## Prototype Result Packet

`output_manifest_to_prototype_result(output_manifest)` emits:

```json
{
  "schema_version": "governed_authoring.prototype_result.v1",
  "backend_output_manifest_id": "output_manifest.example",
  "source_packet_id": "prototype.packet.001",
  "draft_candidate_id": "draft.example",
  "review_decision_id": "review.example",
  "output_status": "approved",
  "decision": "APPROVE_OUTPUT",
  "decision_reason": "approved_output_ready",
  "review_status": "Approved by backend review",
  "evidence_refs": [],
  "unresolved_tensions": [],
  "messages": [],
  "canonical_ledger_entry_id": ""
}
```

## Non-Goals

This contract does not define:

- A browser UI export/import implementation.
- A server API.
- Production authoring artifact writes.
- Production ledger write policy.
- User authentication or durable user identity.
