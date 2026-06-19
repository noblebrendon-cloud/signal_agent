from __future__ import annotations

import pytest

from app.letters_of_light import cli as lol_cli


def test_branch_ownership_is_explicit():
    assert lol_cli.BRANCH_OWNERSHIP == {
        "create": "letters_of_light_pipeline_core",
        "merch-candidate": "letters_of_light_merch_bridge",
        "merch-approve": "letters_of_light_merch_bridge",
        "weekly-diagnostic": "letters_of_light_diagnostic_loop",
        "release-scan": "letters_of_light_release_gate",
        "release-candidate": "letters_of_light_release_gate",
        "release-approve": "letters_of_light_release_gate",
        "release-export": "letters_of_light_release_gate",
        "release-site": "letters_of_light_release_gate",
        "release-youtube": "letters_of_light_release_gate",
    }


@pytest.mark.parametrize(
    ("argv", "expected_handler"),
    [
        (["create", "--theme", "release"], "_cmd_create"),
        (["merch-candidate", "--letter-id", "abc123"], "_cmd_merch_candidate"),
        (["merch-approve", "--candidate-id", "cand123"], "_cmd_merch_approve"),
        (["weekly-diagnostic"], "_cmd_weekly_diagnostic"),
        (["release-scan"], "_cmd_release_scan"),
        (["release-candidate", "--letter-id", "abc123"], "_cmd_release_candidate"),
        (["release-approve", "--letter-id", "abc123"], "_cmd_release_approve"),
        (["release-export", "--letter-id", "abc123"], "_cmd_release_export"),
        (["release-site", "--letter-id", "abc123"], "_cmd_release_site"),
        (["release-youtube", "--letter-id", "abc123"], "_cmd_release_youtube"),
    ],
)
def test_main_dispatches_to_single_owned_branch(monkeypatch, argv, expected_handler):
    calls = []

    def make_handler(name):
        def handler(args):
            calls.append(name)
            return 17

        return handler

    for handler_name in (
        "_cmd_create",
        "_cmd_merch_candidate",
        "_cmd_merch_approve",
        "_cmd_weekly_diagnostic",
        "_cmd_release_scan",
        "_cmd_release_candidate",
        "_cmd_release_approve",
        "_cmd_release_export",
        "_cmd_release_site",
        "_cmd_release_youtube",
    ):
        monkeypatch.setattr(lol_cli, handler_name, make_handler(handler_name))

    rc = lol_cli.main(argv)

    assert rc == 17
    assert calls == [expected_handler]
