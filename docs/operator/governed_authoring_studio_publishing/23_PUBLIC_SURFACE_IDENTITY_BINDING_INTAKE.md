# Public Surface Identity Binding Intake

Purpose: structured operator intake for binding real public identities to already configured destination surfaces.

Scope boundary: this document is for documentation and validation preparation only. It does not create accounts, domains, OAuth credentials, adapters, release targets, schedules, exports, approvals, queues, platform actions, or publications. It does not change campaign state, approval state, release eligibility, website state, social platform state, GitHub, or Zenodo.

Source configuration read:

- `config/brands/brendon_r_coleman.json`
- `config/brands/clarity_systems_group.json`
- `docs/operator/governed_authoring_studio_publishing/22_PUBLIC_SURFACE_ACTIVATION_MODEL.md`

Operator rule: prepopulate only facts already present in configuration. Leave unknown identity fields blank until a real account, page, profile, or domain is verified.

## Brendon R. Coleman

### Personal Site

| Field | Value |
| --- | --- |
| Surface ref | `site` |
| Canonical public URL | `https://brendonrcoleman.com` |
| Account/profile handle or page identifier |  |
| Ownership confirmed: yes/no |  |
| Intended publication mode | Existing gated site release flow |
| Current system configuration state | `publish_enabled` |
| Adapter present: yes/no | yes, `release_site` |
| Credential state | `not_required` |
| Direct publication allowed: yes/no | yes, only through existing release, approval, adapter, and gate behavior |
| Manual publication allowed: yes/no | yes |
| Verification date |  |
| Notes | Existing site behavior is unchanged. |

### X

| Field | Value |
| --- | --- |
| Surface ref | `x` |
| Canonical public URL |  |
| Account/profile handle or page identifier |  |
| Ownership confirmed: yes/no |  |
| Intended publication mode | Manual-only initially |
| Current system configuration state | `configured_manual_publish` |
| Adapter present: yes/no | no |
| Credential state | `none` |
| Direct publication allowed: yes/no | no |
| Manual publication allowed: yes/no | yes |
| Verification date |  |
| Notes | Existing X planning behavior is unchanged; no direct platform posting is configured. |

### Facebook

| Field | Value |
| --- | --- |
| Surface ref | `facebook` |
| Canonical public URL |  |
| Account/profile handle or page identifier |  |
| Ownership confirmed: yes/no |  |
| Intended publication mode | Manual-only initially |
| Current system configuration state | `configured_manual_publish` |
| Adapter present: yes/no | no |
| Credential state | `none` |
| Direct publication allowed: yes/no | no |
| Manual publication allowed: yes/no | yes |
| Verification date |  |
| Notes | Longer text post or link post. No OAuth state, platform account ID, or direct publishing permission is configured. |

### LinkedIn

| Field | Value |
| --- | --- |
| Surface ref | `linkedin` |
| Canonical public URL |  |
| Account/profile handle or page identifier |  |
| Ownership confirmed: yes/no |  |
| Intended publication mode | Manual-only initially |
| Current system configuration state | `configured_manual_publish` |
| Adapter present: yes/no | no |
| Credential state | `none` |
| Direct publication allowed: yes/no | no |
| Manual publication allowed: yes/no | yes |
| Verification date |  |
| Notes | Professional post or document-style note. No OAuth state, platform account ID, or direct publishing permission is configured. |

### Threads

| Field | Value |
| --- | --- |
| Surface ref | `threads` |
| Canonical public URL |  |
| Account/profile handle or page identifier |  |
| Ownership confirmed: yes/no |  |
| Intended publication mode | Manual-only initially |
| Current system configuration state | `configured_manual_publish` |
| Adapter present: yes/no | no |
| Credential state | `none` |
| Direct publication allowed: yes/no | no |
| Manual publication allowed: yes/no | yes |
| Verification date |  |
| Notes | Short-form conversational post or thread. No OAuth state, platform account ID, or direct publishing permission is configured. |

## Clarity Systems Group

### CSG Site

| Field | Value |
| --- | --- |
| Surface ref | `csg_site` |
| Whether this public surface should exist |  |
| Canonical URL once created |  |
| Account/page identifier once created |  |
| Ownership confirmation |  |
| Intended role of this surface |  |
| Provisioning state | `provisioning_required` |
| Adapter status | none configured |
| Credential status | `none` |
| Whether manual publishing is allowed | no |
| Whether direct publication is allowed | no |
| Activation prerequisites | Verify a real domain and public URL before treating this as a live destination. |
| Notes | Candidate surface only; no public URL, account, OAuth state, adapter, or direct publishing permission is configured. |

### CSG LinkedIn

| Field | Value |
| --- | --- |
| Surface ref | `csg_linkedin` |
| Whether this public surface should exist |  |
| Canonical URL once created |  |
| Account/page identifier once created |  |
| Ownership confirmation |  |
| Intended role of this surface |  |
| Provisioning state | `provisioning_required` |
| Adapter status | none configured |
| Credential status | `none` |
| Whether manual publishing is allowed | no |
| Whether direct publication is allowed | no |
| Activation prerequisites | Verify a real organization account before treating this as a live destination. |
| Notes | Candidate surface only; no public URL, account, OAuth state, adapter, or direct publishing permission is configured. |

### CSG Facebook

| Field | Value |
| --- | --- |
| Surface ref | `csg_facebook` |
| Whether this public surface should exist |  |
| Canonical URL once created |  |
| Account/page identifier once created |  |
| Ownership confirmation |  |
| Intended role of this surface |  |
| Provisioning state | `provisioning_required` |
| Adapter status | none configured |
| Credential status | `none` |
| Whether manual publishing is allowed | no |
| Whether direct publication is allowed | no |
| Activation prerequisites | Verify a real page or account before treating this as a live destination. |
| Notes | Candidate surface only; no public URL, account, OAuth state, adapter, or direct publishing permission is configured. |

### CSG X

| Field | Value |
| --- | --- |
| Surface ref | `csg_x` |
| Whether this public surface should exist |  |
| Canonical URL once created |  |
| Account/page identifier once created |  |
| Ownership confirmation |  |
| Intended role of this surface |  |
| Provisioning state | `provisioning_required` |
| Adapter status | none configured |
| Credential status | `none` |
| Whether manual publishing is allowed | no |
| Whether direct publication is allowed | no |
| Activation prerequisites | Verify a real account before treating this as a live destination. |
| Notes | Candidate surface only; no public URL, account, OAuth state, adapter, or direct publishing permission is configured. |

### CSG Threads

| Field | Value |
| --- | --- |
| Surface ref | `csg_threads` |
| Whether this public surface should exist |  |
| Canonical URL once created |  |
| Account/page identifier once created |  |
| Ownership confirmation |  |
| Intended role of this surface |  |
| Provisioning state | `provisioning_required` |
| Adapter status | none configured |
| Credential status | `none` |
| Whether manual publishing is allowed | no |
| Whether direct publication is allowed | no |
| Activation prerequisites | Verify a real account before treating this as a live destination. |
| Notes | Candidate surface only; no public URL, account, OAuth state, adapter, or direct publishing permission is configured. |

## Clarity Systems Group Surface Decision Table

| Surface | Create now / defer / do not create | Reason | Required next action | Owner confirmation required |
| --- | --- | --- | --- | --- |
| `csg_site` |  |  | Verify real domain ownership and canonical URL before configuration activation. | yes |
| `csg_linkedin` |  |  | Verify real organization account and canonical profile URL before configuration activation. | yes |
| `csg_facebook` |  |  | Verify real page or account and canonical URL before configuration activation. | yes |
| `csg_x` |  |  | Verify real account and canonical profile URL before configuration activation. | yes |
| `csg_threads` |  |  | Verify real account and canonical profile URL before configuration activation. | yes |

## Safe Activation Sequence

1. Confirm real account or domain ownership.
2. Enter canonical URL and account identity.
3. Validate configuration.
4. Keep manual-only initially.
5. Test content routing without publication.
6. Complete OAuth only after explicit approval.
7. Enable direct publication only after separate release-gate review.

## Non-Action Confirmation

- No account, page, profile, domain, OAuth credential, adapter, release target, queue, export, schedule, approval, or publication action is created by this intake.
- No existing campaign, derivative, release eligibility, approval, publication, website, GitHub, Zenodo, social platform, or OAuth state is changed by this intake.
