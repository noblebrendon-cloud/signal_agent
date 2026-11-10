"""JSON CLI for local, provisional campaign evaluation and handoff.

Evaluation time is always supplied with ``--at``. No implicit clock, approval,
publication, or media-generation command is provided.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence, TextIO

from .core import CampaignValidationError, evaluate_campaign, load_principles
from .server import MAX_BODY_BYTES, TransportError, create_server, decode_json_document, error_packet
from .service import CampaignNotReadyError, write_handoff


class CommandLineError(ValueError):
    pass


def _print_json(payload: Any, stream: TextIO | None = None) -> None:
    print(json.dumps(payload, ensure_ascii=True, allow_nan=False, sort_keys=True), file=stream or sys.stdout, flush=True)


class JSONArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise CommandLineError(message)

    def print_help(self, file: TextIO | None = None) -> None:
        _print_json({"help": self.format_help()}, file)


def _parser() -> argparse.ArgumentParser:
    parser = JSONArgumentParser(
        prog="python -m signal_agent.campaigns",
        description="Evaluate local campaign proposals and prepare provisional handoffs.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("catalog", help="Read the versioned campaign principle catalog.")
    for command in ("evaluate", "handoff"):
        command_parser = commands.add_parser(
            command,
            help="Evaluate a campaign." if command == "evaluate" else "Write a provisional handoff into a guarded local workspace.",
        )
        command_parser.add_argument("--campaign", type=Path, required=True, help="UTF-8 campaign JSON file, at most 2 MiB.")
        command_parser.add_argument("--at", required=True, help="Explicit ISO 8601 evaluation timestamp with timezone; no current-time default.")
        if command == "handoff":
            command_parser.add_argument("--workspace", type=Path, required=True, help="Explicit local output workspace, checked by the guarded handoff service.")
    serve = commands.add_parser("serve", help="Run the loopback-only in-memory JSON API.")
    serve.add_argument("--host", default="127.0.0.1", choices=("127.0.0.1", "localhost"))
    serve.add_argument("--port", type=int, default=8767)
    return parser


def _read_campaign(path: Path) -> Any:
    with path.open("rb") as source:
        raw = source.read(MAX_BODY_BYTES + 1)
    return decode_json_document(raw)


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        if args.command == "catalog":
            result = load_principles()
        elif args.command == "serve":
            with create_server(args.host, args.port) as server:
                _print_json({
                    "status": "listening",
                    "url": f"http://127.0.0.1:{server.server_address[1]}",
                    "mode": "local_provisional",
                })
                try:
                    server.serve_forever()
                except KeyboardInterrupt:
                    pass
            return 0
        else:
            campaign = _read_campaign(args.campaign)
            if args.command == "evaluate":
                result = evaluate_campaign(campaign, evaluated_at=args.at)
            else:
                result = write_handoff(campaign, evaluated_at=args.at, output_dir=args.workspace)
        _print_json(result)
        return 0
    except CommandLineError as exc:
        error = error_packet("invalid_arguments", str(exc))
        code = 2
    except TransportError as exc:
        error = error_packet(exc.code, str(exc))
        code = 2
    except CampaignNotReadyError as exc:
        error = error_packet("campaign_not_ready", str(exc), decision=exc.decision)
        code = 3
    except CampaignValidationError as exc:
        error = error_packet("invalid_campaign", str(exc))
        code = 2
    except ValueError as exc:
        error = error_packet("invalid_request", str(exc))
        code = 2
    except OSError as exc:
        error = error_packet("io_error", str(exc))
        code = 2
    except Exception:
        error = error_packet("internal_error", "The campaign command could not be completed.")
        code = 1
    _print_json(error, sys.stderr)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
