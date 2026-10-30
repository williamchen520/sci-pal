"""Create a local SciPal administrator and attach it to the default workspace."""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.tenancy import add_member, create_user
from services.tenancy.service import DEFAULT_WORKSPACE_ID


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("username")
    parser.add_argument("--email", default=None)
    parser.add_argument("--password", default=None, help="omit to read from prompt or SCIPAL_ADMIN_PASSWORD")
    args = parser.parse_args()
    password = args.password or os.environ.get("SCIPAL_ADMIN_PASSWORD") or getpass.getpass("Password: ")
    user = create_user(args.username, password, email=args.email, is_admin=True)
    add_member(DEFAULT_WORKSPACE_ID, user["user_id"], "owner", actor_user_id=user["user_id"])
    print(f"created admin {user['username']} ({user['user_id']})")


if __name__ == "__main__":
    main()
