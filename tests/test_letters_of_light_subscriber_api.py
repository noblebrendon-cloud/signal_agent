from __future__ import annotations

import json
import logging
import os
import shutil
import socket
import tempfile
from pathlib import Path
from urllib.parse import quote, urlsplit

import pytest

from app.letters_of_light import subscribers
from services.letters_of_light_subscriber_api import app as subscriber_api


APP_ORIGIN = "https://brendonrcoleman.com"
CONFIRMED_URL = "https://brendonrcoleman.com/letters-of-light/confirmed/"
UNSUBSCRIBED_URL = "https://brendonrcoleman.com/letters-of-light/unsubscribed/"


class FakeConfirmationNotifier:
    def __init__(self) -> None:
        self.deliveries: list[dict[str, str]] = []

    def send_confirmation(self, *, email: str, token: str) -> None:
        self.deliveries.append({"email": email, "token": token})


def _external_temp_parent() -> Path:
    candidates = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Temp",
        Path(os.environ.get("USERPROFILE", "")) / "AppData" / "Local" / "Temp",
        Path.home() / ".codex_tmp",
    ]
    blocked_root = Path("E:/signal_agent").resolve(strict=False)
    for candidate in candidates:
        if not str(candidate).strip():
            continue
        resolved = candidate.resolve(strict=False)
        try:
            resolved.relative_to(blocked_root)
            continue
        except ValueError:
            resolved.mkdir(parents=True, exist_ok=True)
            return resolved
    raise RuntimeError("external temp parent unavailable")


@pytest.fixture
def external_tmp_path() -> Path:
    root = Path(tempfile.mkdtemp(prefix="lol_subscriber_api_tests_", dir=str(_external_temp_parent())))
    try:
        yield root
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _env(root: Path) -> dict[str, str]:
    data_root = root / "private_subscriber_data"
    return {
        subscribers.core.DATA_ROOT_ENV: str(data_root),
        subscribers.core.SUBSCRIBER_DB_ENV: str(data_root / "subscribers.sqlite3"),
        subscriber_api.RETENTION_ROOT_ENV: str(root / "retention_repo"),
        subscriber_api.ALLOWED_ORIGINS_ENV: f"{APP_ORIGIN},https://www.brendonrcoleman.com",
        subscriber_api.CONFIRMED_STATUS_URL_ENV: CONFIRMED_URL,
        subscriber_api.UNSUBSCRIBED_STATUS_URL_ENV: UNSUBSCRIBED_URL,
        subscriber_api.MAX_REQUEST_BYTES_ENV: "512",
        subscriber_api.RATE_LIMIT_COUNT_ENV: "100",
        subscriber_api.RATE_LIMIT_WINDOW_ENV: "60",
    }


def _service(root: Path) -> tuple[subscriber_api.SubscriberAPI, FakeConfirmationNotifier, dict[str, str]]:
    fake = FakeConfirmationNotifier()
    env = _env(root)
    service = subscriber_api.create_app(
        notifier=fake,
        env=env,
        rate_limiter=subscriber_api.InMemoryRateLimiter(max_requests=100, window_seconds=60),
        logger=logging.getLogger("letters_of_light_subscriber_api_tests"),
    )
    return service, fake, env


def _json_body(payload: dict) -> bytes:
    return json.dumps(payload).encode("utf-8")


def _headers(origin: str = APP_ORIGIN) -> dict[str, str]:
    return {"Content-Type": "application/json", "Origin": origin}


def _header(response: subscriber_api.APIResponse, name: str) -> str | None:
    lowered = name.lower()
    for key, value in response.headers:
        if key.lower() == lowered:
            return value
    return None


def _ledger_rows(root: Path, ledger_name: str) -> list[dict]:
    path = root / "retention_repo" / "data" / "state" / ledger_name
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_valid_signup_returns_generic_success_and_invokes_test_notifier_only(external_tmp_path: Path) -> None:
    service, fake, _ = _service(external_tmp_path)

    response = service.handle(
        method="POST",
        target="/api/letters-of-light/signup",
        headers=_headers(),
        body=_json_body({"email": " Reader@Example.COM "}),
    )

    assert response.status_code == 202
    assert response.json() == {"status": "accepted"}
    assert _header(response, "Access-Control-Allow-Origin") == APP_ORIGIN
    assert len(fake.deliveries) == 1
    assert fake.deliveries[0]["email"] == "reader@example.com"
    assert fake.deliveries[0]["token"]
    assert not (external_tmp_path / "retention_repo" / "data" / "state").exists()


def test_duplicate_signup_returns_same_generic_result(external_tmp_path: Path) -> None:
    service, fake, _ = _service(external_tmp_path)
    body = _json_body({"email": "duplicate@example.com"})

    first = service.handle(method="POST", target="/api/letters-of-light/signup", headers=_headers(), body=body)
    second = service.handle(method="POST", target="/api/letters-of-light/signup", headers=_headers(), body=body)

    assert first.status_code == 202
    assert second.status_code == 202
    assert first.body == second.body == b'{"status":"accepted"}'
    assert len(fake.deliveries) == 1


def test_responses_and_logs_do_not_reveal_private_material(
    external_tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING, logger="letters_of_light_subscriber_api_tests")
    service, fake, env = _service(external_tmp_path)
    raw_email = "private-api-check@example.com"

    signup_response = service.handle(
        method="POST",
        target="/api/letters-of-light/signup",
        headers=_headers(),
        body=_json_body({"email": raw_email}),
    )
    token = fake.deliveries[0]["token"]
    token_hash = subscribers.hash_token(token)
    confirm_response = service.handle(
        method="GET",
        target=f"/api/letters-of-light/confirm?token={quote(token)}",
        headers={"Origin": APP_ORIGIN},
    )
    invalid_response = service.handle(
        method="GET",
        target="/api/letters-of-light/confirm?token=definitely-invalid-token",
        headers={"Origin": APP_ORIGIN},
    )

    combined = "\n".join(
        [
            signup_response.body.decode("utf-8"),
            str(signup_response.headers),
            str(confirm_response.headers),
            invalid_response.body.decode("utf-8"),
            caplog.text,
        ]
    )
    assert raw_email not in combined
    assert token not in combined
    assert token_hash not in combined
    assert env[subscribers.core.DATA_ROOT_ENV] not in combined
    assert env[subscribers.core.SUBSCRIBER_DB_ENV] not in combined
    assert "subscriber exists" not in combined.lower()
    assert confirm_response.status_code == 303
    assert urlsplit(_header(confirm_response, "Location") or "").query == ""


def test_missing_or_invalid_configuration_fails_closed(external_tmp_path: Path) -> None:
    with pytest.raises(subscribers.SubscriberCoreError, match="subscriber_data_root_required"):
        subscriber_api.APIConfig.from_env({})

    missing_retention = _env(external_tmp_path)
    missing_retention.pop(subscriber_api.RETENTION_ROOT_ENV)
    with pytest.raises(subscriber_api.APIConfigError, match="api_retention_root_required"):
        subscriber_api.APIConfig.from_env(missing_retention)

    invalid_status = _env(external_tmp_path)
    invalid_status[subscriber_api.CONFIRMED_STATUS_URL_ENV] = f"{CONFIRMED_URL}?token=leak"
    with pytest.raises(subscriber_api.APIConfigError, match="api_confirmed_status_url_invalid"):
        subscriber_api.APIConfig.from_env(invalid_status)

    invalid_origin = _env(external_tmp_path)
    invalid_origin[subscriber_api.ALLOWED_ORIGINS_ENV] = "https://brendonrcoleman.com/path"
    with pytest.raises(subscriber_api.APIConfigError, match="api_allowed_origin_invalid"):
        subscriber_api.APIConfig.from_env(invalid_origin)


def test_oversized_and_malformed_requests_fail_safely(external_tmp_path: Path) -> None:
    service, fake, _ = _service(external_tmp_path)

    oversized = service.handle(
        method="POST",
        target="/api/letters-of-light/signup",
        headers=_headers(),
        body=b"{" + b'"email":"' + (b"a" * 700) + b'@example.com"}',
    )
    malformed = service.handle(
        method="POST",
        target="/api/letters-of-light/signup",
        headers=_headers(),
        body=b"{not-json",
    )
    extra_field = service.handle(
        method="POST",
        target="/api/letters-of-light/signup",
        headers=_headers(),
        body=_json_body({"email": "reader@example.com", "name": "Reader"}),
    )

    assert oversized.status_code == 413
    assert malformed.status_code == 400
    assert extra_field.status_code == 400
    assert fake.deliveries == []


def test_unapproved_cors_origins_are_rejected(external_tmp_path: Path) -> None:
    service, fake, _ = _service(external_tmp_path)

    response = service.handle(
        method="POST",
        target="/api/letters-of-light/signup",
        headers=_headers("https://not-owned.example"),
        body=_json_body({"email": "cors@example.com"}),
    )

    assert response.status_code == 403
    assert _header(response, "Access-Control-Allow-Origin") is None
    assert fake.deliveries == []


def test_confirmation_and_unsubscribe_redirect_without_query_parameters(external_tmp_path: Path) -> None:
    service, fake, env = _service(external_tmp_path)

    signup_response = service.handle(
        method="POST",
        target="/api/letters-of-light/signup",
        headers=_headers(),
        body=_json_body({"email": "confirm-api@example.com"}),
    )
    assert signup_response.status_code == 202
    confirmation_token = fake.deliveries[0]["token"]

    confirm_response = service.handle(
        method="GET",
        target=f"/api/letters-of-light/confirm?token={quote(confirmation_token)}",
        headers={"Origin": APP_ORIGIN},
    )
    assert confirm_response.status_code == 303
    assert _header(confirm_response, "Location") == CONFIRMED_URL
    assert urlsplit(_header(confirm_response, "Location") or "").query == ""
    assert _header(confirm_response, "Referrer-Policy") == "no-referrer"
    assert len(_ledger_rows(external_tmp_path, "events.jsonl")) == 1

    repeated_confirm = service.handle(
        method="GET",
        target=f"/api/letters-of-light/confirm?token={quote(confirmation_token)}",
        headers={"Origin": APP_ORIGIN},
    )
    assert repeated_confirm.status_code == 400
    assert len(_ledger_rows(external_tmp_path, "events.jsonl")) == 1

    subscriber_config = subscribers.resolve_subscriber_config(env)
    signup = subscribers.request_signup("unsubscribe-api@example.com", config=subscriber_config)
    assert signup.token is not None
    confirmed = subscribers.confirm_signup(
        signup.token,
        retention_repo_root=Path(env[subscriber_api.RETENTION_ROOT_ENV]),
        config=subscriber_config,
    )

    unsubscribe_response = service.handle(
        method="GET",
        target=f"/api/letters-of-light/unsubscribe?token={quote(confirmed.unsubscribe_token)}",
        headers={"Origin": APP_ORIGIN},
    )
    assert unsubscribe_response.status_code == 303
    assert _header(unsubscribe_response, "Location") == UNSUBSCRIBED_URL
    assert urlsplit(_header(unsubscribe_response, "Location") or "").query == ""
    assert _header(unsubscribe_response, "Referrer-Policy") == "no-referrer"
    assert _ledger_rows(external_tmp_path, "contacts.jsonl")[-1]["current_state"] == "suppressed"

    repeated_unsubscribe = service.handle(
        method="GET",
        target=f"/api/letters-of-light/unsubscribe?token={quote(confirmed.unsubscribe_token)}",
        headers={"Origin": APP_ORIGIN},
    )
    assert repeated_unsubscribe.status_code == 400


def test_health_endpoint_reveals_no_private_details(external_tmp_path: Path) -> None:
    service, _, env = _service(external_tmp_path)

    response = service.handle(method="GET", target="/health")

    body = response.body.decode("utf-8")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert env[subscribers.core.DATA_ROOT_ENV] not in body
    assert env[subscribers.core.SUBSCRIBER_DB_ENV] not in body
    assert env[subscriber_api.RETENTION_ROOT_ENV] not in body


def test_no_network_calls_occur_during_signup(
    external_tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[object, ...]] = []

    def deny_network(*args: object, **kwargs: object) -> None:
        calls.append(args)
        raise AssertionError("network call attempted")

    monkeypatch.setattr(socket, "create_connection", deny_network)
    service, fake, _ = _service(external_tmp_path)

    response = service.handle(
        method="POST",
        target="/api/letters-of-light/signup",
        headers=_headers(),
        body=_json_body({"email": "network-free@example.com"}),
    )

    assert response.status_code == 202
    assert len(fake.deliveries) == 1
    assert calls == []
