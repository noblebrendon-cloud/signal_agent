"""Bounded, loopback-only HTTP transport for provisional campaign decisions.

This service evaluates supplied JSON and returns in-memory handoff packets. It
does not expose filesystem writes, approval, publication, or media generation.
"""

from __future__ import annotations

import json
import math
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .core import CampaignValidationError, evaluate_campaign, load_principles
from .service import CampaignNotReadyError, build_handoff


MAX_BODY_BYTES = 2 * 1024 * 1024
REQUEST_TIMEOUT_SECONDS = 5.0
LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost"})


class TransportError(ValueError):
    """A client input error with a stable JSON code and HTTP status."""

    def __init__(self, code: str, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


def error_packet(code: str, message: str, **details: Any) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, **details}}


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise TransportError("duplicate_json_key", f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise TransportError("invalid_json_number", f"Non-finite JSON number: {value}")


def _finite_float(value: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise TransportError("invalid_json_number", "JSON numbers must be finite.")
    return result


def decode_json_document(raw: bytes) -> Any:
    """Decode bounded UTF-8 JSON without duplicate keys or non-finite numbers.

    Both CLI files and HTTP bodies use the same strict input contract. Timestamp
    semantics remain the responsibility of the campaign evaluator.
    """
    if len(raw) > MAX_BODY_BYTES:
        raise TransportError("body_too_large", "JSON input exceeds the 2 MiB limit.", 413)
    try:
        return json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
            parse_float=_finite_float,
        )
    except TransportError:
        raise
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise TransportError("invalid_json", "Input must be a valid UTF-8 JSON document.") from exc


class CampaignRequestHandler(BaseHTTPRequestHandler):
    """Serve one bounded request per connection without browser cross-origin access."""

    server_version = "CampaignLocalAPI"
    sys_version = ""

    def setup(self) -> None:
        self.request.settimeout(REQUEST_TIMEOUT_SECONDS)
        super().setup()

    def log_message(self, format: str, *args: Any) -> None:
        # Request paths and user content are not copied into process output.
        return

    def _send_json(self, status: int, payload: Any, *, allow: str | None = None) -> None:
        body = json.dumps(payload, ensure_ascii=True, allow_nan=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Connection", "close")
        if allow is not None:
            self.send_header("Allow", allow)
        self.close_connection = True
        try:
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            # A disconnected caller cannot receive an additional error response.
            return

    def send_error(self, code: int, message: str | None = None, explain: str | None = None) -> None:
        # BaseHTTPRequestHandler otherwise emits HTML for malformed requests or
        # unsupported methods. Keep those errors machine-readable as well.
        try:
            status = HTTPStatus(code)
            description = status.phrase
        except ValueError:
            description = "Request rejected"
        self._send_json(code, error_packet("http_error", description))

    def _validate_origin(self) -> None:
        hosts = self.headers.get_all("Host", [])
        port = self.server.server_address[1]
        allowed = {f"{host}:{port}" for host in LOCAL_HOSTS}
        if port == 80:
            allowed.update(LOCAL_HOSTS)
        if len(hosts) != 1 or hosts[0].lower() not in allowed:
            raise TransportError("invalid_host", "Host must name this loopback server and port.", 403)

        origins = self.headers.get_all("Origin", [])
        accepted_origins = {f"http://{hosts[0].lower()}"}
        if port == 80:
            hostname = hosts[0].lower().split(":", 1)[0]
            accepted_origins = {f"http://{hostname}", f"http://{hostname}:80"}
        if origins and (len(origins) != 1 or origins[0].lower() not in accepted_origins):
            raise TransportError("invalid_origin", "Only this server's same-origin requests are accepted.", 403)

        fetch_sites = self.headers.get_all("Sec-Fetch-Site", [])
        if fetch_sites and (len(fetch_sites) != 1 or fetch_sites[0].lower() not in {"same-origin", "none"}):
            raise TransportError("invalid_origin", "Cross-origin browser requests are not accepted.", 403)

    def _read_envelope(self) -> dict[str, Any]:
        if self.headers.get_all("Transfer-Encoding", []):
            raise TransportError("invalid_framing", "Transfer-Encoding is not supported.")
        lengths = self.headers.get_all("Content-Length", [])
        if not lengths:
            raise TransportError("length_required", "Content-Length is required.", 411)
        if len(lengths) != 1 or not lengths[0].isascii() or not lengths[0].isdecimal():
            raise TransportError("invalid_length", "Content-Length must be one non-negative integer.")
        # Bound the numeral itself before conversion as well as its value.
        if len(lengths[0]) > 12:
            raise TransportError("body_too_large", "JSON input exceeds the 2 MiB limit.", 413)
        length = int(lengths[0])
        if length > MAX_BODY_BYTES:
            raise TransportError("body_too_large", "JSON input exceeds the 2 MiB limit.", 413)

        content_types = self.headers.get_all("Content-Type", [])
        if (
            len(content_types) != 1
            or self.headers.get_content_type() != "application/json"
            or self.headers.get_content_charset() not in {None, "utf-8"}
        ):
            raise TransportError("unsupported_media_type", "Content-Type must be application/json with UTF-8 encoding.", 415)

        raw = self.rfile.read(length)
        if len(raw) != length:
            raise TransportError("incomplete_body", "Request body is shorter than Content-Length.")
        envelope = decode_json_document(raw)
        if not isinstance(envelope, dict) or set(envelope) != {"campaign", "evaluated_at"}:
            raise TransportError("invalid_envelope", "Request must contain only 'campaign' and 'evaluated_at'.")
        return envelope

    def _dispatch(self) -> None:
        self._validate_origin()
        routes = {
            "/health": "GET",
            "/api/campaigns/principles": "GET",
            "/api/campaigns/evaluate": "POST",
            "/api/campaigns/handoff": "POST",
        }
        expected_method = routes.get(self.path)
        if expected_method is None:
            self._send_json(404, error_packet("not_found", "Unknown campaign API route."))
            return
        if self.command != expected_method:
            self._send_json(405, error_packet("method_not_allowed", "Method is not allowed for this route."), allow=expected_method)
            return
        if self.path == "/health":
            self._send_json(200, {"status": "ok", "service": "signal-agent-campaigns", "mode": "local_provisional"})
        elif self.path == "/api/campaigns/principles":
            self._send_json(200, load_principles())
        else:
            envelope = self._read_envelope()
            operation = evaluate_campaign if self.path.endswith("/evaluate") else build_handoff
            result = operation(envelope["campaign"], evaluated_at=envelope["evaluated_at"])
            self._send_json(200, result)

    def _handle(self) -> None:
        try:
            self._dispatch()
        except TransportError as exc:
            self._send_json(exc.status, error_packet(exc.code, str(exc)))
        except CampaignNotReadyError as exc:
            self._send_json(409, error_packet("campaign_not_ready", str(exc), decision=exc.decision))
        except CampaignValidationError as exc:
            self._send_json(400, error_packet("invalid_campaign", str(exc)))
        except TimeoutError:
            self._send_json(408, error_packet("request_timeout", "The request body was not received in time."))
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True
        except Exception:
            self._send_json(500, error_packet("internal_error", "The campaign request could not be completed."))

    do_GET = _handle
    do_POST = _handle
    do_HEAD = _handle
    do_OPTIONS = _handle
    do_PUT = _handle
    do_PATCH = _handle
    do_DELETE = _handle


def create_server(host: str = "127.0.0.1", port: int = 8767) -> ThreadingHTTPServer:
    """Create an unstarted local server; port 0 permits an ephemeral test port.

    ``localhost`` always binds the IPv4 loopback address directly, without DNS
    resolution. Host and optional Origin headers are checked against the actual
    listening port for each request. No CORS permission headers are emitted.
    """
    if host not in LOCAL_HOSTS:
        raise ValueError("The campaign API may bind only to 127.0.0.1 or localhost.")
    if isinstance(port, bool) or not isinstance(port, int) or not 0 <= port <= 65535:
        raise ValueError("The port must be an integer from 0 to 65535.")
    return ThreadingHTTPServer(("127.0.0.1", port), CampaignRequestHandler)
