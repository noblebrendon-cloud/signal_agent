# Governed Authoring Studio Publication Integrations

Status: publication integration planning draft

## 1. Purpose

This document defines how finished Governed Authoring Studio artifacts may
later connect to publication, citation, identity, and discoverability systems.

It is a planning document, not an active integration.

It does not publish anything. It does not create GitHub releases, Zenodo
archives, DOIs, ORCID work records, OpenAIRE records, repository deposits, or
live app deployments.

Working distinction:

```text
GitHub = living repo / development history
Zenodo = archived release snapshot / DOI / citation artifact
ORCID = author identity / work record
OpenAIRE = discovery, linking, monitoring, open research graph layer
Domain + hosting = live public app
```

## 2. Integration Boundary

The app may prepare release-ready and identity-ready metadata for external
publication systems.

The app should not automatically publish, archive, submit, deposit, or link
external records without explicit user approval and verified integration access.

The safe near-term boundary:

- prepare metadata
- prepare citation text
- prepare repository/release checklists
- prepare ORCID-ready work packets
- prepare Zenodo-ready release packets
- record evidence back inside the app

The unsafe premature boundary:

- automatically submit to ORCID without confirmed user permission
- automatically archive to Zenodo without release review
- assume OpenAIRE indexing or discoverability
- publish private material
- treat a DOI as proof of quality
- confuse live app hosting with repository/archive systems

## 3. Publication Flow

Future publication flow:

```text
Finished artifact
-> metadata packet
-> release gate
-> GitHub release if relevant
-> Zenodo archive / DOI
-> ORCID-ready work packet
-> OpenAIRE discoverability consideration
-> evidence record inside the app
```

The flow should preserve user control at each external boundary.

The app should record what was prepared, what was approved, what was released,
where it was released, and which identifiers or citation records were created.

## 4. GitHub Role

GitHub is the living development and version-control layer.

It can support:

- development history
- version control
- source release
- issue and project tracking
- release tags
- GitHub release notes
- release assets when intentionally attached

GitHub is appropriate when the artifact includes software, specifications,
source documents, or project files that benefit from visible version history.

GitHub should not be treated as the live app host unless a separate hosting
setup uses it for static pages or deployment infrastructure.

## 5. Zenodo Role

Zenodo is the archive, DOI, and citation snapshot layer.

It can support:

- archived release snapshots
- DOI creation for deposited artifacts
- public citation records
- durable references to planning, design, software, or research artifacts

Zenodo is not:

- live app hosting
- user data storage
- private draft storage
- active project management
- internal operator storage
- proof that an artifact is high quality

Zenodo releases should be treated as public, durable, and citable.

## 6. ORCID Role

ORCID is the author identity and work-record layer.

The app may later help prepare ORCID-ready metadata for user-approved works.

V1A should not promise automatic ORCID submission.

The safe first step is an ORCID-ready work packet containing:

- title
- creators
- ORCID iD if provided
- artifact type
- publication date
- version
- DOI if available
- repository URL if available
- citation text
- abstract/description

Any future ORCID connection must require user permission and verified API/access
behavior before the app writes to an ORCID record.

## 7. OpenAIRE Role

OpenAIRE should be treated as an external discoverability and research
infrastructure layer.

It may matter later for:

- discoverability of research outputs
- linking research outputs and repositories
- monitoring and open research graph context
- repository ecosystem alignment
- metadata quality considerations

OpenAIRE is not the app host.

The app should not promise automatic OpenAIRE indexing or submission. The safer
V1A posture is to consider whether released artifacts and metadata are
compatible with external discovery systems after they have been deposited in an
appropriate repository or archive.

## 8. User Approval Gate

No external publication action should happen without explicit user approval.

Approval must be required before:

- creating a GitHub release
- uploading to Zenodo
- minting or reserving a DOI
- preparing a public citation record
- connecting to ORCID
- writing an ORCID work record
- making release metadata public
- sharing a repository URL publicly
- exposing source files or generated outputs

The app should distinguish:

- prepared metadata
- approved metadata
- released artifact
- archived artifact
- externally discoverable artifact

## 9. Metadata Packet

The publication metadata packet should include:

- `title`
- `subtitle`
- `creator`
- `orcid_id_if_provided`
- `artifact_type`
- `description_or_abstract`
- `keywords`
- `version`
- `date`
- `license`
- `repository_url`
- `doi`
- `citation_text`
- `bibtex_ready_block`
- `source_artifact_refs`

Optional later fields:

- funder
- related identifiers
- language
- contributors
- rights statement
- release notes
- file manifest
- external repository target

`source_artifact_refs` should point back to the internal artifact records that
produced the release packet, such as source material, spine, draft, review
gate, generated output, export record, and release approval.

## 10. Release Gate Checks

Before any external publication or archive action, confirm:

- artifact reviewed
- metadata complete
- private material excluded
- license selected
- author identity confirmed
- release target selected
- user approval recorded
- DOI status known
- repository URL checked
- citation text prepared
- generated local outputs excluded unless intentionally released
- internal HQ material excluded
- Dust artifacts excluded
- secrets/tokens absent

The release gate should prevent accidental public exposure. It should also
prevent overclaiming maturity or scholarly status.

## 11. V1A Scope

V1A only prepares publication-ready metadata manually.

V1A does not include:

- automatic Zenodo submission
- automatic DOI creation
- automatic ORCID submission
- automatic OpenAIRE submission or indexing
- automatic GitHub release creation
- public repository publishing
- live app deployment
- citation metadata files unless explicitly requested later

V1A may prepare:

- metadata packet
- citation text
- BibTeX-ready block
- release checklist
- ORCID-ready work packet
- Zenodo-ready release notes
- user approval checklist

## 12. Future Scope

Potential future integrations:

- Zenodo API support
- GitHub release automation
- ORCID connection with user permission if API access allows
- OpenAIRE metadata/discoverability checks
- citation export formats
- DOI status tracking
- release manifest generation
- `CITATION.cff` generation
- `.zenodo.json` generation
- BibTeX and RIS export
- evidence record back into project dashboard

Future integrations should be gated by:

- user permission
- verified API behavior
- release readiness
- privacy review
- clear rollback/error handling
- no hidden publication actions

## 13. Risks

Main risks:

- accidental public release
- private material leakage
- overclaiming scholarly status
- confusing DOI with quality approval
- automatic submission without consent
- API access assumptions
- mixing live app hosting with archive systems
- linking the wrong identity or creator record
- publishing incomplete metadata
- archiving generated local outputs unintentionally
- exposing internal HQ or Dust material
- assuming OpenAIRE discoverability before repository/archive behavior is known

The integration layer should increase legitimacy and traceability. It should
not create pressure to publish prematurely.

## 14. Next Action

Keep this as a planning artifact until the V1A operating packet is committed.

Next likely artifacts after this document:

- release metadata packet template
- citation metadata plan
- GitHub release checklist
- Zenodo release checklist
- ORCID-ready work packet template

Do not implement external publication integrations until the V1A workflow has
been tested and the access/permission model is known.
