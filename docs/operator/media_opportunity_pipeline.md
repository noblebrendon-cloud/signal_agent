# Media Opportunity Pipeline

This is a private-first intake and independent-coverage review path. It does not send email, post publicly, edit the website, deploy GitHub Pages, change DNS, or update social profiles.

## Create An Opportunity

Use the local CLI:

```powershell
python -m signal_agent.media_opportunities.cli create-opportunity --type podcast_or_interview --invitation-text "Paste the email, DM, phone-call summary, or spoken request here." --url "https://example.com/context" --outlet "Example Outlet" --contact "Producer name" --deadline "2026-07-15" --topic "Runtime governance"
```

The command writes private state under `data/state/media_opportunities/` and creates a per-opportunity folder containing:

- `opportunity.md`
- `response_draft.md`
- `facts_and_links.md`
- `evidence_checklist.md`
- `record.json`

For an email, paste the message body into `--invitation-text`. For a DM or text message, paste the visible message and describe the channel in `--notes`. For a phone call or spoken conversation, write a faithful summary such as `Phone call summary: ...`. For a podcast invitation, select `--type podcast_or_interview` and include the proposed topic and deadline if known.

## State Model

Core states:

- `captured`
- `qualified`
- `response_ready`
- `awaiting_outcome`
- `published_candidate`
- `independently_verified`
- `approved_for_public_reference`

Terminal or non-public states:

- `declined`
- `private`
- `self_published`
- `insufficient_independence`
- `unverified`
- `archived`

Move records with:

```powershell
python -m signal_agent.media_opportunities.cli transition --opportunity-id opp_... --state qualified --reason operator_qualified
```

Expected route for successful independent coverage:

`captured -> qualified -> response_ready -> awaiting_outcome -> published_candidate -> independently_verified -> approved_for_public_reference`

## Response Drafts

The intake command creates a deterministic draft for the opportunity type. Drafts are always marked `DRAFT - DO NOT SEND AUTOMATICALLY`. The operator must review, edit, and send manually outside this system.

## Independent Coverage Rules

Approved public-reference exports require:

- Publicly reachable published URL.
- Outlet, title, coverage type, and short neutral description.
- Author and date when publicly available.
- Relationship classification of `independent`.
- Coverage substantially about Brendon R. Coleman or a clearly identified work.
- Verification note or captured evidence.
- Explicit human approval.

The gate rejects Brendon's own website or own profile posts, reposts without original reporting or review, paid placement without clear independent editorial control, generic directory entries, self-published announcements, and unverified screenshots without a public URL.

## Approve A Public-Reference Export

First move the opportunity to `awaiting_outcome`. When coverage is published, run:

```powershell
python -m signal_agent.media_opportunities.cli approve-public-reference --opportunity-id opp_... --published-url "https://example.com/story" --title "Story title" --outlet "Example Outlet" --author "Reporter Name" --date "2026-07-20" --coverage-type article --description "Neutral factual description." --substantially-about --verification-note "Reviewed public URL and outlet page." --approved-by "Brendon R. Coleman" --human-approved --relationship independent
```

If the gate passes, the system writes sanitized handoff artifacts:

- `media_reference_candidate.json`
- `media_reference_candidate.md`

These export only title, outlet, public author, date, type, public URL, short neutral description, verification status, and approval timestamp. They exclude private contacts, original messages, strategy notes, and unverified claims.

## Private Storage

Private operational records and generated packets live under `data/state/media_opportunities/`, which follows the repo's local state convention. The editable public-safe identity packet lives at `config/media_opportunities/canonical_identity_packet.json`.

No public Media & References page is created by this pipeline. That remains a later manual website task after at least one approved independent reference exists.
