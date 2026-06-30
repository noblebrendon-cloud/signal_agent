# Public Surface Activation Model

Purpose: define the next governed-publication configuration layer without creating posts, releases, exports, schedules, queues, platform actions, OAuth flows, external accounts, or public artifacts.

## Configuration States

Destination configuration is not publication authority. The system distinguishes:

- `draft_only`: drafts may exist for review, but the surface is not provisioned as a destination.
- `configured_manual_publish`: the surface is a legitimate planning/review destination, but publication is manual and outside the system.
- `configured_uncredentialed`: the surface is configured, but no verified credential or account authorization exists.
- `credentialed_unverified`: credentials exist but are not verified for governed publication.
- `publish_enabled`: direct publication is allowed only through the established release, approval, adapter, and credential gates.
- `disabled`: surface is unavailable.
- `provisioning_required`: the surface is a candidate only; account, URL, credential, and adapter facts still need verification.

## Authority Boundaries

| Concept | Meaning | What it does not mean |
| --- | --- | --- |
| Brand | The identity and voice context for a draft or release candidate. | A brand does not prove a public account, domain, credential, approval, or publication right exists. |
| Destination surface | A named destination where a draft may be planned or reviewed. | A configured destination is not a credentialed, approved, or publish-enabled destination. |
| Adapter capability | Code or provider support that can transform or transmit content for a platform. | Adapter existence does not prove account ownership, OAuth authorization, human approval, or release eligibility. |
| OAuth or account authorization | A verified credential/account binding for a platform. | Credentials alone do not approve content or bypass release gates. |
| Human approval | Explicit human review for a specific artifact, hash, draft, or release decision. | Approval does not create an adapter, credential, URL, schedule, queue, or platform action by itself. |
| Release eligibility | A gate result showing whether an artifact satisfies release requirements. | Eligibility is not publication; it does not post, export, schedule, or queue content. |
| Publication | The actual external or site-facing action after all gates pass. | Configuration, planning, drafting, and review are not publication. |

## BRC Surface Matrix

Brand: Brendon R. Coleman
Brand status: `active`

| Surface | Current configuration state | Public URL exists | Adapter exists | Credentials exist | Manual publication possible | Direct system publication allowed | Next operator action required |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Personal site | `publish_enabled` | Yes: `https://brendonrcoleman.com` | Yes: `release_site` | Not required | Yes | Yes, only after existing approval and release gates | Use the existing approval/release flow before any site publication. |
| X | `configured_manual_publish` | No URL configured | No | No | Yes | No | Keep as manual output until a verified adapter and explicit authorization exist. |
| Facebook | `configured_manual_publish` | No URL configured | No | No | Yes | No | Review manually; add verified account details only after explicit operator approval. |
| LinkedIn | `configured_manual_publish` | No URL configured | No | No | Yes | No | Review manually; add verified account details only after explicit operator approval. |
| Threads | `configured_manual_publish` | No URL configured | No | No | Yes | No | Review manually; add verified account details only after explicit operator approval. |

BRC content constraints:

- Facebook: longer text post or link post.
- LinkedIn: professional post or document-style note.
- Threads: short-form conversational post or thread.
- X: short post or short thread.
- Personal site: canonical personal essay or reviewed public site article.

## CSG Surface Matrix

Brand: Clarity Systems Group
Brand status: `internal_only`

No CSG surface is live. No CSG public URL, platform account ID, OAuth state, adapter, or direct publication permission is configured.

| Surface | Current configuration state | Public URL exists | Adapter exists | Credentials exist | Manual publication possible | Direct system publication allowed | Next operator action required |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Site (`csg_site`) | `provisioning_required` | No | No | No | No | No | Verify a real domain and public URL before treating this as a live destination. |
| LinkedIn (`csg_linkedin`) | `provisioning_required` | No | No | No | No | No | Verify a real organization account before treating this as a live destination. |
| Facebook (`csg_facebook`) | `provisioning_required` | No | No | No | No | No | Verify a real page or account before treating this as a live destination. |
| X (`csg_x`) | `provisioning_required` | No | No | No | No | No | Verify a real account before treating this as a live destination. |
| Threads (`csg_threads`) | `provisioning_required` | No | No | No | No | No | Verify a real account before treating this as a live destination. |

CSG identity boundary:

- CSG is configured as a business/legal operating identity.
- CSG public service offering claims are not configured.
- CSG public domain and public contact information are not configured.
- CSG remains `internal_only`; no campaign may treat a CSG destination as publicly live.

## Safe Activation Checklist

Use this checklist only for a later, explicit activation request:

1. Verify real account or domain ownership.
2. Enter the canonical public URL.
3. Attach a supported platform adapter, if direct system publication is intended.
4. Complete authorization only after explicit operator approval.
5. Test in draft/private mode where available.
6. Verify release gate behavior.
7. Enable direct publication only after review.

## Current Safety Confirmation

- No OAuth flow has been created or authorized.
- No platform account ID has been invented.
- No CSG public URL, domain, or account has been invented.
- No existing Build Evidence Library derivative approval state or `release_eligible` value is changed by this configuration phase.
- No release package, export, schedule, queue, platform action, website change, GitHub change, Zenodo change, or publication action is authorized by this document.

## Verification Scope Note

Scoped verification for this activation-model change passed:

- `tests/test_public_surface_activation_model.py`: 6 passed.
- `tests/test_multi_brand_studio.py`, `tests/test_project_studio_governed_handoff.py`, and `tests/test_project_studio_governed_draft_route.py`: combined 48 passed.
- Governed publishing affected slice, covering drafting brief, content horizon, artifact lifecycle, and package readiness tests: 73 passed.
- Scoped `git diff --check` for the five task files passed.

Full `python -m pytest` was attempted but could not complete collection because of pre-existing repository/environment blockers:

- missing `jsonschema`
- missing `pydantic`
- unrelated `shared.inspect` import failure for `health_status`

Global `git diff --check` is blocked by unrelated pre-existing whitespace in:

- `laviathon/labs/simulator/substack_release_post.md`
- `site_laviathon/labs/simulator/substack_release_post.md`

These unrelated blockers were not modified by this task. The scoped verification above should not be described as equivalent to a clean full-suite run.
