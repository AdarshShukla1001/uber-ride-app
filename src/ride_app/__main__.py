"""Process entry point; each mode owns an independent in-memory context."""

import argparse
import sys

from ride_app.bootstrap import create_application
from ride_app.domain.errors import DomainError
from ride_app.infrastructure.configuration import load_configuration


def main(argv: list[str] | None = None) -> int:
    """Select a runtime mode and return a shell-compatible exit code."""
    parser = argparse.ArgumentParser(prog="ride-app", description="Ride-hailing backend")
    modes = parser.add_subparsers(dest="mode", required=True)
    cli = modes.add_parser("cli", help="Start a standalone interactive CLI")
    cli.add_argument("--config", help="Path to a TOML configuration file")
    modes.add_parser("demo", help="Run the deterministic end-to-end demonstration")
    serve = modes.add_parser("serve", help="Start the single-worker HTTP API")
    serve.add_argument("--config", help="Path to a TOML configuration file")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", default=8000, type=int)
    args = parser.parse_args(argv)

    try:
        application = None
        if args.mode in {"cli", "serve"}:
            if args.config:
                try:
                    settings, cards = load_configuration(args.config)
                except (OSError, ValueError) as exc:
                    print(f"CONFIGURATION_ERROR: {exc}", file=sys.stderr)
                    return 2
                application = create_application(settings, rate_cards=cards)
            else:
                application = create_application()
        if args.mode == "cli":
            from ride_app.interfaces.cli import run_cli

            return run_cli(application)
        if args.mode == "serve":
            # Lazy imports keep CLI startup independent of the HTTP server adapter.
            import uvicorn

            from ride_app.interfaces.api import create_api

            # Multiple workers would own isolated dictionaries and unrelated locks.
            uvicorn.run(create_api(application), host=args.host, port=args.port, workers=1)
            return 0
        from ride_app.interfaces.demo import run_demo

        return run_demo()
    except DomainError as exc:
        print(f"{exc.code}: {exc.message}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
