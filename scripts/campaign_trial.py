"""Run a bounded local campaign cycle with explicitly synthetic observations."""
from __future__ import annotations

import copy
import hashlib
import http.client
import json
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from signal_agent.campaigns.server import create_server  # noqa: E402

EVALUATED_AT = "2026-11-10T00:00:00Z"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> None:
    campaign = json.loads((ROOT / "examples/campaigns/exploratory_campaign.json").read_text(encoding="utf-8"))
    initial = copy.deepcopy(campaign)
    server = create_server(port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def request(route: str, payload: dict) -> tuple[int, dict]:
        client = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
        try:
            client.request("POST", route, json.dumps({"campaign": payload, "evaluated_at": EVALUATED_AT}),
                           {"Content-Type": "application/json"})
            response = client.getresponse()
            return response.status, json.loads(response.read())
        finally:
            client.close()

    try:
        status, decision = request("/api/campaigns/evaluate", campaign)
        require(status == 200 and decision["proposed_action"] == "run_small_test", "Initial test proposal failed.")
        status, handoff = request("/api/campaigns/handoff", campaign)
        require(status == 200, "Provisional handoff failed.")
        require(handoff["authoring_result"]["formal_decision"]["decision"] == "EMIT_PROVISIONAL_DRAFT", "Existing governance was not used.")
        require(handoff["authoring_result"]["canonical_ledger_entry"] is None, "Unexpected ledger entry.")
        require(all(task["status"] == "pending" for task in handoff["production_packet"]["tasks"]), "Unexpected production completion.")

        with tempfile.TemporaryDirectory(prefix="signal-campaign-trial-") as temporary:
            root = Path(temporary)
            context_file = root / "campaign.json"
            context_file.write_text(json.dumps(campaign), encoding="utf-8")
            result = subprocess.run([
                sys.executable, "-m", "signal_agent.campaigns", "handoff",
                "--campaign", str(context_file), "--at", EVALUATED_AT,
                "--workspace", str(root / "new-handoff"),
            ], cwd=ROOT, text=True, capture_output=True, check=True, timeout=20)
            receipt = json.loads(result.stdout)
            require(receipt["handoff_id"] == handoff["handoff_id"], "CLI/API handoff identities differ.")
            for relative, path in receipt["files"].items():
                require(hashlib.sha256(Path(path).read_bytes()).hexdigest() == receipt["sha256"][relative], "Export checksum mismatch.")
            source = json.loads(Path(receipt["files"]["inputs/source_packet.json"]).read_text(encoding="utf-8"))
            require(source["source_material"][0]["text"] == initial["sources"][0]["text"], "Source text changed.")
            checked_files = len(receipt["files"])

        campaign["phase"] = "testing"
        status, waiting = request("/api/campaigns/evaluate", campaign)
        require(status == 200 and waiting["proposed_action"] == "observe_more", "Missing results started more production.")
        campaign["phase"] = "reviewing"
        campaign["evaluation_plan"] = {
            "window_start": "2026-11-07T00:00:00Z", "window_end": "2026-11-09T00:00:00Z",
            "platform": "synthetic", "format": "short_post", "minimum_observations": 2,
            "minimum_exposures": 300, "minimum_independent_variants": 2,
        }
        campaign["observations"] = [{
            "observation_id": f"synthetic.observation.{i}", "variant_id": f"synthetic.variant.{i}",
            "kind": "repeat_value", "summary": "Synthetic local trial only; not observed audience feedback.",
            "source_ref": f"example:synthetic-trial/{i}", "observed_at": "2026-11-08T12:00:00Z",
            "platform": "synthetic", "format": "short_post", "verification": "reported", "verified_by": "",
            "exposures": 200, "metric": {"name": "example_response", "numerator": 10, "denominator": 200},
        } for i in (1, 2)]
        status, insufficient = request("/api/campaigns/evaluate", campaign)
        require(status == 200 and insufficient["proposed_action"] == "observe_more", "Unverified evidence established repeatability.")
        for row in campaign["observations"]:
            row.update(verification="verified", verified_by="synthetic-fixture")
        status, repeated = request("/api/campaigns/evaluate", campaign)
        require(status == 200 and repeated["proposed_action"] == "repeat_theme", "Comparable repeated fixture did not support a bounded repeat.")
        require(repeated["evidence_quality"]["causal_effect_established"] is False, "Observations were mislabeled as causal evidence.")
        campaign["phase"] = "paused"
        status, closed = request("/api/campaigns/handoff", campaign)
        require(status == 409 and closed["error"]["decision"]["proposed_action"] == "pause", "Paused campaign escaped its handoff boundary.")
        print(json.dumps({
            "schema_version": "campaign_trial.v1", "status": "passed", "mode": "synthetic_local_trial",
            "transport": "real loopback HTTP and CLI subprocess",
            "actions": [decision["proposed_action"], waiting["proposed_action"], insufficient["proposed_action"], repeated["proposed_action"], "pause"],
            "initial_decision_id": decision["decision_id"], "handoff_id": handoff["handoff_id"],
            "export_files_hash_verified": checked_files, "source_text_preserved": True,
            "governed_authoring_result": "EMIT_PROVISIONAL_DRAFT",
            "production_tasks": "pending_external_executor", "publication_authorized": False,
            "scope": "No social delivery, real audience observations, paid generation, or deployed API. Temporary exports were removed after verification.",
        }, indent=2))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


if __name__ == "__main__":
    main()
