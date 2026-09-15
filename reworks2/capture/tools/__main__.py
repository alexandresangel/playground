"""Run from the Capture root: python -m tools --help."""
import argparse
import json

from tools.configuration import ROOT, load_offline, state_dir


def main():
    parser = argparse.ArgumentParser(description="Capture local development with Azurite and HTTP stubs")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init", help="Preserve/create the offline key and upload catalog/prompts to Azurite")
    commands.add_parser("storage", help="Run the pinned Azurite Blob emulator")
    commands.add_parser("sync-config", help="Upload catalog/prompts to running Azurite")
    for name, port in (("serve", 8010), ("stubs", 8011)):
        command = commands.add_parser(name)
        command.add_argument("--port", type=int, default=port)
        command.add_argument("--reload", action="store_true")
    commands.add_parser("headers", help="Print a fresh offline JWT and dummy request headers as JSON")
    smoke = commands.add_parser("smoke", help="Upload a PDF over real HTTP")
    smoke.add_argument("--url", default="http://127.0.0.1:8010")
    smoke.add_argument("--headers", dest="headers_file", help="JSON headers file for connected mode")
    smoke.add_argument("--pdf")
    smoke.add_argument("--trade-type", default="iamLoan")
    smoke.add_argument("--session-id")
    smoke.add_argument("--debug", action="store_true")
    args = parser.parse_args()
    if args.command in ("init", "sync-config"):
        from tools.bootstrap import initialize, sync_config
        config = load_offline()
        (initialize if args.command == "init" else sync_config)(config)
        print("Offline catalog/prompts uploaded to Azurite.")
    elif args.command in ("serve", "stubs", "storage"):
        from tools.bootstrap import azurite_command, offline_environment, run_process, server_command
        config = load_offline()
        if args.command == "storage":
            command, cwd = azurite_command(config), ROOT
        else:
            command = server_command(args.command, args.port, reload=args.reload)
            cwd = state_dir(config) if args.command == "serve" else ROOT
            if args.command == "serve" and not (cwd / "VERSION").is_file():
                raise SystemExit("Start storage and run python -m tools init first")
        raise SystemExit(run_process(command, cwd=cwd, env=offline_environment(config)))
    elif args.command == "headers":
        from tools.smoke import offline_headers

        print(json.dumps(offline_headers(), indent=2))
    else:
        from tools.smoke import run

        kwargs = vars(args)
        kwargs.pop("command")
        run(**kwargs)


if __name__ == "__main__":
    main()
