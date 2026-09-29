"""CLI entry point for explicit live evaluation and offline response grading."""

from __future__ import annotations

import argparse
from pathlib import Path

from evals.dataset import load_dataset
from evals.runner import run_dataset, score_saved


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate", help="Check dataset and ground truth without network access")
    validate.add_argument("dataset", type=Path)
    for name in ("run", "score"):
        command = commands.add_parser(name, help="Call the configured Capture API" if name == "run" else "Grade saved responses; no network or API config")
        command.add_argument("dataset", type=Path)
        command.add_argument("--output", type=Path, required=True, help="New output directory; existing directories are never overwritten")
        command.add_argument("--split", help="Only this split, e.g. dev or holdout")
        command.add_argument("--tag", action="append", help="Require a tag; repeat to require multiple tags")
        command.add_argument("--label", default="", help="Experiment description, e.g. baseline or prompt-v2")
        command.add_argument("--baseline", type=Path, help="Prior report.json with identical dataset/rules/selection")
        if name == "run":
            command.add_argument("--config", type=Path, help="Capture API client config (same keys as tests/test.api.example.json)")
            command.add_argument("--repeat", type=int, default=1)
            command.add_argument("--timeout", type=float, default=600)
        else:
            command.add_argument("--responses", type=Path, required=True, help="Prior evaluation run, or directory containing case-id/response.json")
    args = parser.parse_args(argv)
    try:
        dataset = load_dataset(args.dataset)
        if args.command == "validate":
            print(f"Valid dataset: {len(dataset.cases)} cases; fingerprint={dataset.fingerprint}")
            return 0
        common = dict(split=args.split, tags=args.tag, label=args.label, baseline=args.baseline)
        if args.command == "score":
            report = score_saved(dataset, args.responses, args.output, **common)
        else:
            # Offline commands do not import authentication/configuration or instantiate an HTTP client.
            from evals.client import CaptureClient, load_api_config
            with CaptureClient(load_api_config(args.config), timeout=args.timeout) as client:
                report = run_dataset(dataset, args.output, client, repeat=args.repeat,
                                     progress=lambda message: print(message, flush=True), **common)
        summary = report["summary"]
        print(f"{'PASS' if report['passed'] else 'FAIL'}: {summary['passed_attempts']}/{summary['attempts']} attempts; report: {args.output / 'report.html'}")
        return 0 if report["passed"] else 1
    except FileExistsError:
        print("Output directory already exists; choose a new --output directory")
        return 2
    except ValueError as exc:
        # These are curated dataset/rule/client configuration diagnostics, not HTTP errors.
        print(f"Evaluation configuration error: {exc}")
        return 2
    except OSError as exc:
        print(f"Evaluation artifact error ({type(exc).__name__}); check file paths and permissions")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
