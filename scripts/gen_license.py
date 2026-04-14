#!/usr/bin/env python3
"""Generate KDM offline license keys (must match kdm/licensing.py secret)."""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import os
import sys
from pathlib import Path

# Repo root (scripts/..)
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from kdm.licensing import LICENSE_HMAC_SECRET  # noqa: E402


def sign_key(email: str, expiry: str) -> str:
    payload = f"{email.strip()}|{expiry.strip()}".encode("utf-8")
    data_b64 = base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
    sig = hmac.new(LICENSE_HMAC_SECRET, payload, hashlib.sha256).hexdigest()[:24]
    return f"{data_b64}--{sig}"


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate a KDM license key.")
    ap.add_argument("email", help="Customer email (stored in key payload)")
    ap.add_argument(
        "expiry",
        nargs="?",
        default="perpetual",
        help='Expiry: "perpetual" or end date YYYY-MM-DD',
    )
    args = ap.parse_args()
    exp = args.expiry.strip().lower()
    if exp != "perpetual":
        from datetime import datetime

        datetime.strptime(exp, "%Y-%m-%d")
    key = sign_key(args.email, exp)
    print(key)
    if not os.environ.get("KDM_LICENSE_SECRET"):
        print(
            "(dev default secret; set KDM_LICENSE_SECRET for production builds)",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
