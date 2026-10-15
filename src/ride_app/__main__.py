"""Process entry point; each mode owns an independent in-memory context."""

import argparse
import sys

from ride_app.bootstrap import create_application
from ride_app.domain.errors import FeatureNotImplemented


def main(argv: list[str] | None = None) -> int:
    """Select a runtime mode and return a shell-compatible exit code."""
    parser = argparse.ArgumentParser(prog="ride-app", description="Ride-hailing backend scaffold")
    modes = parser.add_subparsers(dest="mode", required=True)
    modes.add_parser("cli", help="Start a standalone interactive CLI")
    modes.add_parser("demo", help="Reserved for the upcoming end-to-end demonstration")
    serve = modes.add_parser("serve", help="Start the single-worker HTTP API")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", default=8000, type=int)
    args = parser.parse_args(argv)

    try:
        if args.mode == "cli":
            from ride_app.interfaces.cli import run_cli

            return run_cli(create_application())
        if args.mode == "serve":
            # Lazy imports keep CLI startup independent of the HTTP server adapter.
            import uvicorn

            from ride_app.interfaces.api import create_api

            # Multiple workers would own isolated dictionaries and unrelated locks.
            uvicorn.run(create_api(), host=args.host, port=args.port, workers=1)
            return 0
        raise FeatureNotImplemented("End-to-end ride demo")
    except FeatureNotImplemented as exc:
        print(f"NOT_IMPLEMENTED: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
