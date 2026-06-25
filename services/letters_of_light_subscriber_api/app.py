from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Protocol
from urllib.parse import parse_qs, urlsplit

from app.letters_of_light import subscribers


ALLOWED_ORIGINS_ENV = "LETTERS_OF_LIGHT_API_ALLOWED_ORIGINS"
CONFIRMED_STATUS_URL_ENV = "LETTERS_OF_LIGHT_CONFIRMED_STATUS_URL"
UNSUBSCRIBED_STATUS_URL_ENV = "LETTERS_OF_LIGHT_UNSUBSCRIBED_STATUS_URL"
MAX_REQUEST_BYTES_ENV = "LETTERS_OF_LIGHT_API_MAX_REQUEST_BYTES"
RATE_LIMIT_COUNT_ENV = "LETTERS_OF_LIGHT_API_RATE_LIMIT_COUNT"
RATE_LIMIT_WINDOW_ENV = "LETTERS_OF_LIGHT_API_RATE_LIMIT_WINDOW_SECONDS"
RETENTION_ROOT_ENV = "SIGNAL_AGENT_ROOT"
DEFAULT_MAX_REQUEST_BYTES = 2048
DEFAULT_RATE_LIMIT_COUNT = 20
DEFAULT_RATE_LIMIT_WINDOW_SECONDS = 60
JSON_CONTENT_TYPE = "application/json; charset=utf-8"
NO_REFERRER = "no-referrer"


class APIConfigError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class ConfirmationNotifier(Protocol):
    def send_confirmation(self, *, email: str, token: str) -> None:
        ...


class RateLimiter(Protocol):
    def allow(self, *, key: str, route: str) -> bool:
        ...


@dataclass(frozen=True)
class APIConfig:
    subscriber_config: subscribers.core.SubscriberConfig
    retention_repo_root: Path
    allowed_origins: tuple[str, ...]
    confirmed_status_url: str
    unsubscribed_status_url: str
    max_request_bytes: int = DEFAULT_MAX_REQUEST_BYTES
    rate_limit_count: int = DEFAULT_RATE_LIMIT_COUNT
    rate_limit_window_seconds: int = DEFAULT_RATE_LIMIT_WINDOW_SECONDS

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "APIConfig":
        source = env or os.environ
        subscriber_config = subscribers.resolve_subscriber_config(source)
        retention_root_value = str(source.get(RETENTION_ROOT_ENV) or "").strip()
        if not retention_root_value:
            raise APIConfigError("api_retention_root_required")

        max_request_bytes = _positive_int(
            source.get(MAX_REQUEST_BYTES_ENV),
            default=DEFAULT_MAX_REQUEST_BYTES,
            code="api_max_request_bytes_invalid",
        )
        rate_limit_count = _positive_int(
            source.get(RATE_LIMIT_COUNT_ENV),
            default=DEFAULT_RATE_LIMIT_COUNT,
            code="api_rate_limit_count_invalid",
        )
        rate_limit_window_seconds = _positive_int(
            source.get(RATE_LIMIT_WINDOW_ENV),
            default=DEFAULT_RATE_LIMIT_WINDOW_SECONDS,
            code="api_rate_limit_window_invalid",
        )
        allowed_origins = _parse_allowed_origins(str(source.get(ALLOWED_ORIGINS_ENV) or ""))
        return cls(
            subscriber_config=subscriber_config,
            retention_repo_root=Path(retention_root_value).expanduser().resolve(strict=False),
            allowed_origins=allowed_origins,
            confirmed_status_url=_validate_status_url(
                source.get(CONFIRMED_STATUS_URL_ENV),
                code="api_confirmed_status_url_invalid",
            ),
            unsubscribed_status_url=_validate_status_url(
                source.get(UNSUBSCRIBED_STATUS_URL_ENV),
                code="api_unsubscribed_status_url_invalid",
            ),
            max_request_bytes=max_request_bytes,
            rate_limit_count=rate_limit_count,
            rate_limit_window_seconds=rate_limit_window_seconds,
        )


@dataclass(frozen=True)
class APIResponse:
    status_code: int
    body: bytes = b""
    headers: tuple[tuple[str, str], ...] = ()

    def json(self) -> dict:
        if not self.body:
            return {}
        return json.loads(self.body.decode("utf-8"))


class InMemoryRateLimiter:
    def __init__(self, *, max_requests: int, window_seconds: int, clock: Callable[[], float] | None = None):
        self.max_requests = int(max_requests)
        self.window_seconds = int(window_seconds)
        self.clock = clock or time.monotonic
        self._buckets: dict[tuple[str, str], list[float]] = {}

    def allow(self, *, key: str, route: str) -> bool:
        now = self.clock()
        bucket_key = (str(key or "anonymous"), str(route or "unknown"))
        cutoff = now - self.window_seconds
        bucket = [timestamp for timestamp in self._buckets.get(bucket_key, []) if timestamp > cutoff]
        if len(bucket) >= self.max_requests:
            self._buckets[bucket_key] = bucket
            return False
        bucket.append(now)
        self._buckets[bucket_key] = bucket
        return True


class SubscriberAPI:
    def __init__(
        self,
        *,
        config: APIConfig,
        notifier: ConfirmationNotifier,
        rate_limiter: RateLimiter | None = None,
        logger: logging.Logger | None = None,
    ):
        self.config = config
        self.notifier = notifier
        self.rate_limiter = rate_limiter or InMemoryRateLimiter(
            max_requests=config.rate_limit_count,
            window_seconds=config.rate_limit_window_seconds,
        )
        self.logger = logger or logging.getLogger(__name__)

    def handle(
        self,
        *,
        method: str,
        target: str,
        headers: Mapping[str, str] | None = None,
        body: bytes = b"",
        remote_addr: str = "unknown",
    ) -> APIResponse:
        normalized_headers = _normalize_headers(headers or {})
        parsed = urlsplit(target)
        path = parsed.path
        route = f"{method.upper()} {path}"

        cors_error = self._cors_error(normalized_headers, route=route)
        if cors_error is not None:
            return cors_error

        if method.upper() == "OPTIONS":
            return self._response(204, route=route, headers=self._cors_headers(normalized_headers))

        if not self.rate_limiter.allow(key=str(remote_addr or "unknown"), route=route):
            return self._error(429, "rate_limited", route=route, headers=self._cors_headers(normalized_headers))

        if path == "/health" and method.upper() == "GET":
            return self._json({"status": "ok"}, route=route, headers=self._cors_headers(normalized_headers))

        if path == "/api/letters-of-light/signup" and method.upper() == "POST":
            return self._signup(normalized_headers, body, route=route)

        if path == "/api/letters-of-light/confirm" and method.upper() == "GET":
            return self._confirm(parsed.query, normalized_headers, route=route)

        if path == "/api/letters-of-light/unsubscribe" and method.upper() == "GET":
            return self._unsubscribe(parsed.query, normalized_headers, route=route)

        return self._error(404, "not_found", route=route, headers=self._cors_headers(normalized_headers))

    def _signup(self, headers: Mapping[str, str], body: bytes, *, route: str) -> APIResponse:
        cors_headers = self._cors_headers(headers)
        payload = self._parse_signup_payload(headers, body, route=route)
        if isinstance(payload, APIResponse):
            return payload

        try:
            email = subscribers.normalize_email(payload["email"])
            signup = subscribers.request_signup(
                email,
                config=self.config.subscriber_config,
            )
            if signup.token is not None:
                self.notifier.send_confirmation(email=email, token=signup.token)
        except subscribers.SubscriberCoreError as exc:
            return self._error(400, _subscriber_error_code(exc), route=route, headers=cors_headers)
        except Exception:
            return self._error(503, "confirmation_notification_failed", route=route, headers=cors_headers)

        return self._json({"status": "accepted"}, status_code=202, route=route, headers=cors_headers)

    def _confirm(self, query: str, headers: Mapping[str, str], *, route: str) -> APIResponse:
        cors_headers = self._cors_headers(headers)
        token = _single_query_value(query, "token")
        if not _valid_token_param(token):
            return self._error(400, "invalid_token", route=route, headers=cors_headers)
        try:
            subscribers.confirm_signup(
                token,
                retention_repo_root=self.config.retention_repo_root,
                config=self.config.subscriber_config,
            )
        except subscribers.SubscriberCoreError as exc:
            return self._error(400, _subscriber_error_code(exc), route=route, headers=cors_headers)
        return self._redirect(self.config.confirmed_status_url, route=route, headers=cors_headers)

    def _unsubscribe(self, query: str, headers: Mapping[str, str], *, route: str) -> APIResponse:
        cors_headers = self._cors_headers(headers)
        token = _single_query_value(query, "token")
        if not _valid_token_param(token):
            return self._error(400, "invalid_token", route=route, headers=cors_headers)
        try:
            subscribers.unsubscribe(
                token,
                retention_repo_root=self.config.retention_repo_root,
                config=self.config.subscriber_config,
            )
        except subscribers.SubscriberCoreError as exc:
            return self._error(400, _subscriber_error_code(exc), route=route, headers=cors_headers)
        return self._redirect(self.config.unsubscribed_status_url, route=route, headers=cors_headers)

    def _parse_signup_payload(self, headers: Mapping[str, str], body: bytes, *, route: str) -> dict | APIResponse:
        cors_headers = self._cors_headers(headers)
        if len(body) > self.config.max_request_bytes:
            return self._error(413, "request_too_large", route=route, headers=cors_headers)
        content_type = headers.get("content-type", "")
        if content_type and "application/json" not in content_type.lower():
            return self._error(415, "unsupported_media_type", route=route, headers=cors_headers)
        try:
            payload = json.loads(body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return self._error(400, "malformed_json", route=route, headers=cors_headers)
        if not isinstance(payload, dict) or set(payload) != {"email"} or not isinstance(payload.get("email"), str):
            return self._error(400, "invalid_signup_payload", route=route, headers=cors_headers)
        if len(payload["email"]) > 254:
            return self._error(400, "invalid_signup_payload", route=route, headers=cors_headers)
        return payload

    def _cors_error(self, headers: Mapping[str, str], *, route: str) -> APIResponse | None:
        origin = headers.get("origin", "").strip()
        if origin and origin not in self.config.allowed_origins:
            return self._error(403, "origin_not_allowed", route=route)
        return None

    def _cors_headers(self, headers: Mapping[str, str]) -> tuple[tuple[str, str], ...]:
        origin = headers.get("origin", "").strip()
        if not origin or origin not in self.config.allowed_origins:
            return ()
        return (
            ("Access-Control-Allow-Origin", origin),
            ("Access-Control-Allow-Methods", "GET, POST, OPTIONS"),
            ("Access-Control-Allow-Headers", "Content-Type"),
            ("Vary", "Origin"),
        )

    def _json(
        self,
        payload: dict,
        *,
        status_code: int = 200,
        route: str,
        headers: tuple[tuple[str, str], ...] = (),
    ) -> APIResponse:
        body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return self._response(
            status_code,
            body=body,
            route=route,
            headers=(("Content-Type", JSON_CONTENT_TYPE), *headers),
        )

    def _redirect(self, location: str, *, route: str, headers: tuple[tuple[str, str], ...]) -> APIResponse:
        return self._response(303, route=route, headers=(("Location", location), *headers))

    def _error(
        self,
        status_code: int,
        code: str,
        *,
        route: str,
        headers: tuple[tuple[str, str], ...] = (),
    ) -> APIResponse:
        self._log_error(code=code, route=route, status_code=status_code)
        return self._json({"error": code}, status_code=status_code, route=route, headers=headers)

    def _response(
        self,
        status_code: int,
        *,
        body: bytes = b"",
        route: str,
        headers: tuple[tuple[str, str], ...] = (),
    ) -> APIResponse:
        base_headers = (
            ("Referrer-Policy", NO_REFERRER),
            ("Cache-Control", "no-store"),
        )
        return APIResponse(status_code=status_code, body=body, headers=(*base_headers, *headers))

    def _log_error(self, *, code: str, route: str, status_code: int) -> None:
        self.logger.warning(
            "letters_of_light_subscriber_api_error",
            extra={
                "error_code": code,
                "route": route,
                "status_code": status_code,
            },
        )


def create_app(
    *,
    notifier: ConfirmationNotifier,
    env: Mapping[str, str] | None = None,
    rate_limiter: RateLimiter | None = None,
    logger: logging.Logger | None = None,
) -> SubscriberAPI:
    config = APIConfig.from_env(env)
    return SubscriberAPI(config=config, notifier=notifier, rate_limiter=rate_limiter, logger=logger)


def create_wsgi_app(
    *,
    notifier: ConfirmationNotifier,
    env: Mapping[str, str] | None = None,
    rate_limiter: RateLimiter | None = None,
    logger: logging.Logger | None = None,
) -> Callable:
    service = create_app(notifier=notifier, env=env, rate_limiter=rate_limiter, logger=logger)

    def _wsgi_app(environ: dict, start_response: Callable) -> list[bytes]:
        method = str(environ.get("REQUEST_METHOD") or "GET")
        path = str(environ.get("PATH_INFO") or "/")
        query = str(environ.get("QUERY_STRING") or "")
        target = f"{path}?{query}" if query else path
        content_length = int(str(environ.get("CONTENT_LENGTH") or "0") or 0)
        body = environ.get("wsgi.input").read(content_length) if content_length else b""
        headers = _headers_from_wsgi_environ(environ)
        response = service.handle(
            method=method,
            target=target,
            headers=headers,
            body=body,
            remote_addr=str(environ.get("REMOTE_ADDR") or "unknown"),
        )
        status = f"{response.status_code} {_reason_phrase(response.status_code)}"
        start_response(status, list(response.headers))
        return [response.body]

    return _wsgi_app


def _positive_int(value: str | None, *, default: int, code: str) -> int:
    if value is None or not str(value).strip():
        return default
    try:
        parsed = int(str(value))
    except ValueError as exc:
        raise APIConfigError(code) from exc
    if parsed <= 0:
        raise APIConfigError(code)
    return parsed


def _parse_allowed_origins(value: str) -> tuple[str, ...]:
    origins: list[str] = []
    for raw in value.split(","):
        origin = raw.strip().rstrip("/")
        if not origin:
            continue
        parsed = urlsplit(origin)
        if parsed.scheme not in {"https", "http"} or not parsed.netloc or parsed.path not in {"", "/"}:
            raise APIConfigError("api_allowed_origin_invalid")
        origins.append(f"{parsed.scheme}://{parsed.netloc}")
    return tuple(dict.fromkeys(origins))


def _validate_status_url(value: str | None, *, code: str) -> str:
    url = str(value or "").strip()
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.netloc or parsed.query or parsed.fragment:
        raise APIConfigError(code)
    return url


def _normalize_headers(headers: Mapping[str, str]) -> dict[str, str]:
    return {str(key).lower(): str(value) for key, value in headers.items()}


def _single_query_value(query: str, key: str) -> str | None:
    values = parse_qs(query, keep_blank_values=True).get(key)
    if not values or len(values) != 1:
        return None
    return values[0]


def _valid_token_param(token: str | None) -> bool:
    if token is None:
        return False
    token = token.strip()
    return 16 <= len(token) <= 512 and all(32 < ord(char) < 127 for char in token)


def _subscriber_error_code(exc: subscribers.SubscriberCoreError) -> str:
    if exc.code.startswith("invalid_email"):
        return "invalid_signup_payload"
    if exc.code.startswith("subscriber_"):
        return "subscriber_configuration_failed"
    if exc.code.startswith("retention_"):
        return "retention_write_failed"
    if "token" in exc.code:
        return "invalid_token"
    return "subscriber_request_failed"


def _headers_from_wsgi_environ(environ: Mapping[str, object]) -> dict[str, str]:
    headers: dict[str, str] = {}
    for key, value in environ.items():
        if key.startswith("HTTP_"):
            header = key[5:].replace("_", "-").lower()
            headers[header] = str(value)
    if "CONTENT_TYPE" in environ:
        headers["content-type"] = str(environ["CONTENT_TYPE"])
    return headers


def _reason_phrase(status_code: int) -> str:
    return {
        200: "OK",
        202: "Accepted",
        204: "No Content",
        303: "See Other",
        400: "Bad Request",
        403: "Forbidden",
        404: "Not Found",
        413: "Payload Too Large",
        415: "Unsupported Media Type",
        429: "Too Many Requests",
        503: "Service Unavailable",
    }.get(status_code, "OK")
