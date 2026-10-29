"""Create or update a user account.

    python create_user.py jdoe --name "Jane Doe" --domains hr,it --groups hr-managers
    python create_user.py ops-admin --role admin --domains hr,it,cloudops

The password is asked interactively (never on the command line, so it stays out of the shell
history). Domains are the assistants the user may ask; groups give access to restricted documents.
"""
import argparse
import getpass
from app.rag.registry import DOMAINS
from app.services.users import User, init_users, save_user

parser = argparse.ArgumentParser(description="Create or update a user account.")
parser.add_argument("username")
parser.add_argument("--name", help="display name (default: the username)")
parser.add_argument("--role", choices=["employee", "admin"], default="employee")
parser.add_argument("--domains", default="hr", help="comma-separated: " + ", ".join(DOMAINS))
parser.add_argument("--groups", default="", help="comma-separated document groups, e.g. hr-managers")
args = parser.parse_args()

domains = [d.strip() for d in args.domains.split(",") if d.strip()]
unknown = [d for d in domains if d not in DOMAINS]
if unknown:
    raise SystemExit(f"Unknown domain: {', '.join(unknown)}")
password = getpass.getpass("Password: ")
if len(password) < 10 or password != getpass.getpass("Repeat: "):
    raise SystemExit("Passwords differ or are shorter than 10 characters.")

init_users()
groups = tuple(g.strip().lower() for g in args.groups.split(",") if g.strip())
save_user(User(args.username, args.name or args.username, args.role, tuple(domains), groups), password)
print(f"Saved {args.username} ({args.role}): domains {', '.join(domains)}; groups {', '.join(groups) or 'none'}")
