# Demotion List

The mandatory demotions from the adversarial pass have been applied.

## Demotions resolved by this patch set

| prior claim | source occurrences | prior problem | current state |
| --- | --- | --- | --- |
| Atomic append and atomic overwrite primitives already exist and are used on state and operator ledger surfaces. | `docs/publications/deterministic_governance/README.md`; `docs/publications/deterministic_governance/deterministic_governance.md`; `docs/publications/deterministic_governance/implementation_evidence.md` | Operator ledger append previously used local plain append. | Repaired. `signal_agent/operator/runtime.py::_append_jsonl` now routes through `app/utils/io_contract.py::append_jsonl_atomic`, and the source claim remains `repo-proven`. |
| Observed effects match declared effects. | `docs/publications/deterministic_governance/deterministic_governance.md`; `docs/publications/deterministic_governance/invariant_mapping.md`; `docs/publications/deterministic_governance/control_illusion_test.md` | Runtime previously recorded mismatch without rejecting. | Repaired on declared operator surfaces. The source claim is now stated as match-or-reject and remains `repo-proven` only on that bounded surface. |
| No mutation occurs outside the declaration. | `docs/publications/deterministic_governance/deterministic_governance.md`; `docs/publications/deterministic_governance/invariant_mapping.md` | Zero-write tools previously had a blind spot. | Further repaired. Zero-write and declared-write tools now reject in-scope mutation outside the declared write set, and the source claim remains downgraded to `repo-supported` because observation scope is still bounded. |
| Boundary enforcement. | `docs/publications/deterministic_governance/deterministic_governance.md`; `docs/publications/deterministic_governance/control_illusion_test.md` | The source claim previously overreached beyond actual fail-closed behavior. | Demoted and narrowed. Boundary enforcement is now labeled `repo-supported` and explicitly scope-bounded. |
| The control-illusion test passes on the governed operator write path. | `docs/publications/deterministic_governance/deterministic_governance.md`; `docs/publications/deterministic_governance/control_illusion_test.md` | The old full-pass claim failed when verification was record-only. | Rewritten. The source claim now states that verification is fail-closed but boundary enforcement remains scope-bounded, labeled `repo-supported`. |
| The repo proves actual pre-mutation control on the governed operator write path. | `docs/publications/deterministic_governance/control_illusion_test.md` | The old wording implied a stronger invariant than the repo proved. | Rewritten. The source claim now says fail-closed verification is proven on declared operator surfaces while boundary enforcement remains scope-bounded. |
| Routing contract resolution exists, but inference still remains an allowed authority source. | `docs/publications/deterministic_governance/README.md`; `docs/publications/deterministic_governance/deterministic_governance.md`; `docs/publications/deterministic_governance/implementation_evidence.md` | `member_inference` previously remained routable authority. | Repaired. `shared/contract.py` now marks `member_inference` non-authoritative and `app/hq/capture/router.py` fails closed when stronger contract evidence is absent. |

## Remaining required demotions

None beyond the source labels already present in the bundle.

The remaining partial claims are already marked `repo-supported` or `theoretical`, including:

- undeclared-mutation prevention beyond explicit operator observation scopes
- routing contract-resolution exception handling and source precedence
- publication and release surfaces that do not yet prove the same boundary-verification discipline
