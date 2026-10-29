"""Users, their domains and their groups. Passwords are hashed with PBKDF2-SHA256 (standard
library), so no plain or reversible password is ever stored.

- `domains`: the knowledge bases a user may ask (hr, it, cloudops).
- `groups`: the document groups a user belongs to; a document restricted to a group is only
  retrieved for its members. Every user is implicitly in the `all` group.
"""
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from app.services.db import connect

PUBLIC_GROUP = "all"
PBKDF2_ITERATIONS = 200_000


@dataclass(frozen=True)
class User:
    username: str
    display_name: str
    role: str  # "employee" or "admin"
    domains: tuple[str, ...]
    groups: tuple[str, ...]

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    @property
    def access_groups(self) -> list[str]:
        """Groups whose documents this user may retrieve, `all` included."""
        return sorted({PUBLIC_GROUP, *self.groups})

    def public(self) -> dict:
        return {"username": self.username, "display_name": self.display_name, "role": self.role,
                "domains": list(self.domains), "groups": list(self.groups)}


# One-click accounts of the public demo: same password-less login for everyone, different rights.
DEMO_ACCOUNTS = {
    "employee": User("alex", "Alex Martin (employee)", "employee", ("hr", "it"), ()),
    "hr-manager": User("sam", "Sam Laurent (HR manager)", "employee", ("hr", "it"), ("hr-managers",)),
    "admin": User("admin", "Demo admin", "admin", ("hr", "it", "cloudops"), ("hr-managers",)),
}


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iterations, salt, digest = stored.split("$")
    except ValueError:
        return False
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iterations))
    return hmac.compare_digest(candidate.hex(), digest)


def init_users() -> None:
    con = connect()
    con.execute(
        """CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            display_name TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL,
            domains TEXT NOT NULL,
            groups TEXT NOT NULL
        )"""
    )
    con.commit()
    con.close()


def _user(row) -> User:
    return User(row["username"], row["display_name"], row["role"],
                tuple(json.loads(row["domains"])), tuple(json.loads(row["groups"])))


def save_user(user: User, password: str) -> None:
    con = connect()
    con.execute(
        """INSERT INTO users(username, display_name, password_hash, role, domains, groups)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(username) DO UPDATE SET display_name = excluded.display_name,
             password_hash = excluded.password_hash, role = excluded.role,
             domains = excluded.domains, groups = excluded.groups""",
        (user.username, user.display_name, hash_password(password), user.role,
         json.dumps(list(user.domains)), json.dumps(list(user.groups))),
    )
    con.commit()
    con.close()


def get_user(username: str, include_demo: bool = False) -> User | None:
    con = connect()
    row = con.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    con.close()
    if row:
        return _user(row)
    if include_demo:
        return next((u for u in DEMO_ACCOUNTS.values() if u.username == username), None)
    return None


def authenticate(username: str, password: str) -> User | None:
    con = connect()
    row = con.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    con.close()
    if row is None:
        verify_password(password, hash_password("timing"))  # same cost for unknown users
        return None
    return _user(row) if verify_password(password, row["password_hash"]) else None
