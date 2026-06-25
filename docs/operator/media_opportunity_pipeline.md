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

## Gmail Label Intake

Create a Gmail label named `Media Opportunity` in Gmail, then apply it manually to any email or thread that might become an interview, podcast, guest essay, review, local reporting, citation, speaking invitation, organizational feature, or similar opportunity.

Run the local read-only intake:

```powershell
python -m signal_agent.media_opportunities.cli ingest-gmail-label --label "Media Opportunity"
```

For live Gmail access, set `MEDIA_OPPORTUNITIES_GMAIL_CLIENT_SECRETS` to a local Google OAuth client secrets JSON file. `MEDIA_OPPORTUNITIES_GMAIL_TOKEN_FILE` may point to a token file outside the repository; if unset, the command stores the token under the local OS user config area. The command uses Gmail readonly scope only.

After labeling an email, the command reads labeled messages, creates one private `captured` opportunity per unique Gmail thread or message, writes the same private artifact set as manual intake, and reports created, skipped, manual-review, and error counts. It does not send a reply, archive, delete, relabel, mark read, or otherwise mutate the source email.

Duplicate prevention uses a stable private source fingerprint derived from the Gmail thread ID when available, otherwise the message ID, otherwise a body hash. The fingerprint and hashed metadata are stored in the private ledgers; repeat runs skip already-ingested conversations instead of creating separate opportunity records.

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

## Manual Fallbacks

DMs, calls, texts, and in-person opportunities still use `create-opportunity`. Paste the message text or write a faithful summary, set `--type other` when uncertain, and keep relationship classification as `unknown` until human review supports something stronger. Gmail intake is only a convenience trigger, not an approval path.
