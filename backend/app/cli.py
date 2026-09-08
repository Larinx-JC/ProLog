"""Trusted local administration: python -m app.cli bootstrap-admin/recover-admin."""

import argparse
import getpass
from collections.abc import Callable, Sequence
from typing import NoReturn

from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.services.auth import AuthService
from app.services.auth_types import AuthError


class SafeArgumentParser(argparse.ArgumentParser):
    """Keep accidentally supplied credentials out of command-line error output."""

    def error(self, message: str) -> NoReturn:
        """Show usage without echoing rejected argument values, which may be secrets."""
        self.print_usage()
        self.exit(2, "Invalid arguments; use --help. Passwords are accepted only at the prompt.\n")


def main(
    argv: Sequence[str] | None = None,
    auth: AuthService | None = None,
    prompt: Callable[[str], str] | None = None,
) -> int:
    """Prompt locally for a confirmed password; never accept it in process arguments."""
    parser = SafeArgumentParser(description="ProLog trusted local Admin setup/recovery")
    parser.add_argument("command", choices=["bootstrap-admin", "recover-admin"])
    parser.add_argument("--account", required=True)
    parser.add_argument("--name", default="Administrator")
    args = parser.parse_args(argv)
    ask = prompt or getpass.getpass
    password = ask("New password (15–128 characters): ")
    if password != ask("Confirm password: "):
        print("Passwords do not match; no account changed.")
        return 1
    service = auth or AuthService(SessionLocal, get_settings())
    try:
        if args.command == "bootstrap-admin":
            user = service.bootstrap(args.account, args.name, password)
        else:
            user = service.recover_admin(args.account, password)
    except AuthError as error:
        print(f"Account unchanged: {error.code}")
        return 1
    except (ValueError, SQLAlchemyError):
        print("Account unchanged: invalid input or unavailable database.")
        return 1
    print(f"Completed {args.command} for {user.account}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
