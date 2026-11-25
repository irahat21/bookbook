"""Session - who is using the application (SRS 4.5).

A Visitor session has user = None and role VS. wallet_only is True when a
suspended customer signs in (R8): they may only use the wallet.
"""
import uuid

from bookorbit import rules


class Session:
    def __init__(self, fs):
        self.fs = fs
        self.user = None
        self.role = rules.VISITOR
        self.wallet_only = False
        self.session_id = str(uuid.uuid4())

    def start(self, user: dict) -> None:
        self.user = user
        self.role = user["role"]
        self.wallet_only = user["status"] == rules.SUSPENDED
        self.session_id = str(uuid.uuid4())

    def end(self) -> None:
        self.user = None
        self.role = rules.VISITOR
        self.wallet_only = False
        self.session_id = str(uuid.uuid4())

    def refresh(self) -> None:
        """Re-read the user so role/status changes made elsewhere are visible."""
        if self.user is not None:
            fresh = self.fs.find("users", "user_id", self.user["user_id"])
            if fresh is None:  # account vanished: fall back to Visitor
                self.end()
                return
            self.user = fresh
            self.role = fresh["role"]
            self.wallet_only = fresh["status"] == rules.SUSPENDED

    def require(self, *roles, active: bool = True) -> None:
        """Guard for role-only actions; always re-reads the user first (SRS 4.1)."""
        self.refresh()
        if self.role not in roles:
            raise PermissionError("Not available for your account type")
        if active and self.wallet_only:
            raise PermissionError("Your account is suspended")

    @property
    def is_customer(self) -> bool:
        return self.role in rules.CUSTOMER_ROLES
