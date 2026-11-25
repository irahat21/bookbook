"""AuthService - registration, sign-in and sign-out (SRS 4.6, UC-01, UC-02, R1, R2)."""
import re
from datetime import datetime, timedelta

from bookorbit import rules
from bookorbit.ai.biometrics import FACE, VOICE
from bookorbit.errors import LoginError, RegistrationError
from bookorbit.services.session import Session

TS_FORMAT = "%Y-%m-%d %H:%M:%S"


class AuthService:
    def __init__(self, fs, bio, clock=datetime.now):
        self.fs = fs
        self.bio = bio
        self.clock = clock  # injectable so tests can move time forward (lockout)

    def _now(self) -> str:
        return self.clock().strftime(TS_FORMAT)

    # ------------------------------------------------------------------ UC-01
    def register(self, full_name, username, email, face_img=None, voice_clip=None) -> dict:
        """Create an RC account and enroll its face and/or voice template.

        Raises RegistrationError({field: reason}) for E1/E2, NoFaceError /
        NoVoiceError for a bad sample (E3). On any failure after enrollment has
        started, templates already written are removed again (E5: no half account).
        """
        full_name, username, email = (full_name or "").strip(), (username or "").strip(), (email or "").strip()
        problems = {}
        if not re.match(rules.USERNAME_PATTERN, username):
            problems["username"] = "3-20 letters, digits or underscore"
        elif self.fs.find("users", "username", username.lower()):
            problems["username"] = "This username is already in use"
        if not full_name:
            problems["full_name"] = "Required"
        if not re.match(rules.EMAIL_PATTERN, email):
            problems["email"] = "Enter a valid email (name@domain.tld)"
        if face_img is None and voice_clip is None:
            # E4: voice-only is allowed; with neither the account cannot be created
            problems["biometric"] = "Capture a face photo or record your voice"
        if problems:
            raise RegistrationError(problems)

        uid = self.fs.next_id("users", "U")
        try:
            if face_img is not None:
                self.bio.enroll(uid, FACE, face_img)
            if voice_clip is not None:
                self.bio.enroll(uid, VOICE, voice_clip)
            user = {"user_id": uid, "username": username.lower(), "full_name": full_name,
                    "email": email, "role": rules.RC, "status": rules.ACTIVE, "balance": 0.00,
                    "warnings": 0, "purchase_count": 0, "total_spent": 0.00,
                    "promo_purchases": 0, "promo_spent": 0.00, "created_at": self._now()}
            self.fs.append("users", user)
        except Exception:
            self._remove_templates(uid)
            raise
        return user

    def _remove_templates(self, uid: str) -> None:
        rows = self.fs.load("biometrics")
        for r in rows:
            if r["user_id"] == uid:
                self.fs.resolve(r["vector_path"]).unlink(missing_ok=True)
        self.fs.save_all("biometrics", [r for r in rows if r["user_id"] != uid])

    # ------------------------------------------------------------------ UC-02
    def login(self, username, method, sample) -> Session:
        """Verify a face/voice sample and start a Session.

        NoFaceError / NoVoiceError (E5) and TemplateMissingError (E6) propagate
        before an attempt is recorded, so they never count as failures.
        """
        user = self.fs.find("users", "username", (username or "").strip().lower())
        if user is None:
            raise LoginError("UNKNOWN_USER")                      # E1, not counted
        fails, locked_until = self.lock_state(user["username"])
        if locked_until:
            raise LoginError("LOCKED", minutes_left=self._minutes_left(locked_until))
        ok, score = self.bio.verify(user["user_id"], method, sample)
        self.record_attempt(user["username"], method, ok, score)
        if not ok:
            fails, locked_until = self.lock_state(user["username"])
            if locked_until:                                       # E3: 3rd consecutive failure
                raise LoginError("LOCKED", minutes_left=self._minutes_left(locked_until))
            raise LoginError("NO_MATCH", attempts_left=rules.MAX_LOGIN_FAILS - fails)  # E2
        session = Session(self.fs)
        session.start(user)                                        # wallet_only if SUSPENDED (E4, R8)
        return session

    def logout(self, session: Session) -> None:
        session.end()

    def record_attempt(self, username, method, success, score) -> None:
        self.fs.append("login_attempts", {
            "attempt_id": self.fs.next_id("login_attempts", "LA"), "username": username,
            "method": method, "success": bool(success), "score": round(float(score), 3),
            "timestamp": self._now()})

    def is_locked(self, username) -> bool:
        return self.lock_state(username)[1] is not None

    def lock_state(self, username) -> tuple[int, datetime | None]:
        """(consecutive failures, locked_until or None) for R2.

        DEVIATION from SRS 4.6 is_locked (see docs/ASSUMPTIONS.md, D-15): the
        pseudo-code looks at "the last 3 attempts", so after the 5 minutes
        expire one more failure re-locks at once. Here the attempts are replayed
        in order and the failure counter restarts after a success OR after a
        lock has expired, so the user gets 3 fresh tries.
        """
        fails, locked_until = 0, None
        for a in self.fs.load("login_attempts"):   # file order = chronological
            if a["username"] != username:
                continue
            t = datetime.strptime(a["timestamp"], TS_FORMAT)
            if locked_until and t >= locked_until:
                fails, locked_until = 0, None
            if a["success"]:
                fails = 0
            else:
                fails += 1
                if fails >= rules.MAX_LOGIN_FAILS:
                    locked_until = t + timedelta(minutes=rules.LOCK_MINUTES)
        if locked_until and self.clock() >= locked_until:
            fails, locked_until = 0, None
        return fails, locked_until

    def _minutes_left(self, locked_until: datetime) -> int:
        secs = (locked_until - self.clock()).total_seconds()
        return max(1, int(-(-secs // 60)))  # round up
