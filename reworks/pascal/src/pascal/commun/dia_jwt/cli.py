#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys

from dia_jwt.auth import JwtAuth


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="dia_jwt — keystore and token CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    ck = sub.add_parser("create-keystore")
    ck.add_argument("--path", default="jwt_keystore.p12")
    ck.add_argument("--password-env", default="JWT_KEYSTORE_PASSWORD")

    mt = sub.add_parser("mint")
    mt.add_argument("--path", default="jwt_keystore.p12")
    mt.add_argument("--password-env", default="JWT_KEYSTORE_PASSWORD")
    mt.add_argument("--issuer", default="diapason-agent")
    mt.add_argument("--sub", required=True)
    mt.add_argument("--role", action="append", required=True)
    mt.add_argument("--customer-id", type=int)
    mt.add_argument("--days", type=int)
    mt.add_argument("--seconds", type=int)

    args = p.parse_args(argv)
    password = os.environ.get(args.password_env)
    if not password:
        print(f"Set {args.password_env}", file=sys.stderr)
        return 1

    if args.cmd == "create-keystore":
        JwtAuth.create_keystore(args.path, password)
        print(f"Keystore: {args.path}")
        return 0

    auth = JwtAuth(args.path, password, issuer=args.issuer)
    out = auth.mint(
        sub=args.sub,
        roles=args.role,
        customer_id=args.customer_id,
        ttl_days=args.days,
        ttl_seconds=args.seconds,
    )
    print(json.dumps(out, indent=2))
    print("\nAuthorization: Bearer", out["access_token"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())