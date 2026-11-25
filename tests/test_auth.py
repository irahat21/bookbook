"""UC-01 Register, UC-02 Log In, R1, R2, R8 (wallet-only sign-in)."""
from datetime import datetime, timedelta
from pathlib import Path

from bookorbit import rules
from bookorbit.ai.biometrics import FACE, VOICE
from bookorbit.errors import LoginError, NoFaceError, NoVoiceError, RegistrationError, TemplateMissingError
from bookorbit.services.auth import AuthService
from tests.helpers import TempStoreCase


class FakeClock:
    def __init__(self):
        self.t = datetime(2026, 11, 20, 12, 0, 0)

    def __call__(self):
        return self.t

    def advance(self, minutes):
        self.t += timedelta(minutes=minutes)


class RegisterTests(TempStoreCase):
    def test_register_creates_active_rc_with_templates(self):           # UC-01 normal
        u = self.ctx.auth.register("Pat Lee", "Pat_01", "pat@example.com", self.face("pat"), self.voice(220))
        self.assertEqual((u["role"], u["status"], u["balance"], u["warnings"]), (rules.RC, rules.ACTIVE, 0.0, 0))
        self.assertEqual(u["username"], "pat_01")
        methods = {t["method"] for t in self.fs.load("biometrics")}
        self.assertEqual(methods, {FACE, VOICE})
        self.assertTrue(Path(self.tmp, "biometrics", f"{u['user_id']}_face.npy").exists())

    def test_username_taken_case_insensitive(self):                     # UC-01 E1
        self.ctx.auth.register("Pat", "pat", "p@x.com", self.face("pat"))
        with self.assertRaises(RegistrationError) as cm:
            self.ctx.auth.register("Pat 2", "PAT", "p2@x.com", self.face("pat2"))
        self.assertIn("already in use", cm.exception.problems["username"])

    def test_invalid_fields_save_nothing(self):                          # UC-01 E2
        with self.assertRaises(RegistrationError) as cm:
            self.ctx.auth.register("", "ab", "not-an-email", None, None)
        self.assertEqual(set(cm.exception.problems), {"full_name", "username", "email", "biometric"})
        self.assertEqual(self.fs.load("users"), [])

    def test_no_face_or_two_faces_rejected_and_nothing_kept(self):       # UC-01 E3 + E5 rollback
        for bad in (self.face(None, faces=0), self.face("crowd", faces=2), b"not an image"):
            with self.assertRaises(NoFaceError):
                self.ctx.auth.register("Pat", "pat", "p@x.com", bad)
        self.assertEqual(self.fs.load("users"), [])
        self.assertEqual(self.fs.load("biometrics"), [])

    def test_voice_only_allowed(self):                                   # UC-01 E4
        u = self.ctx.auth.register("Pat", "pat", "p@x.com", None, self.voice(220))
        self.assertEqual(u["role"], rules.RC)

    def test_bad_voice_rolls_back_face_template(self):                   # UC-01 E5 (no half account)
        with self.assertRaises(NoVoiceError):
            self.ctx.auth.register("Pat", "pat", "p@x.com", self.face("pat"), self.voice(220, seconds=1.0))
        self.assertEqual(self.fs.load("biometrics"), [])
        self.assertEqual(list(Path(self.tmp, "biometrics").glob("*.npy")), [])


class LoginTests(TempStoreCase):
    def setUp(self):
        super().setUp()
        self.clock = FakeClock()
        self.auth = AuthService(self.fs, self.ctx.bio, clock=self.clock)
        self.user = self.auth.register("Pat", "pat", "p@x.com", self.face("pat", 0), self.voice(220, variant=0))

    def test_face_login_with_a_different_photo_of_same_person(self):    # UC-02 normal, R2
        s = self.auth.login("PAT", FACE, self.face("pat", 1))
        self.assertEqual((s.role, s.wallet_only), (rules.RC, False))
        att = self.fs.load("login_attempts")[-1]
        self.assertTrue(att["success"])
        self.assertGreaterEqual(att["score"], rules.FACE_THRESHOLD)

    def test_voice_login(self):                                          # UC-02 alternate method
        s = self.auth.login("pat", VOICE, self.voice(220, variant=5))
        self.assertEqual(s.user["user_id"], self.user["user_id"])

    def test_unknown_user_not_counted(self):                             # UC-02 E1
        with self.assertRaises(LoginError) as cm:
            self.auth.login("ghost", FACE, self.face("pat"))
        self.assertEqual(cm.exception.kind, "UNKNOWN_USER")
        self.assertEqual(self.fs.load("login_attempts"), [])

    def test_no_match_counts_down(self):                                 # UC-02 E2
        with self.assertRaises(LoginError) as cm:
            self.auth.login("pat", FACE, self.face("stranger"))
        self.assertEqual((cm.exception.kind, cm.exception.attempts_left), ("NO_MATCH", 2))
        self.assertLess(self.fs.load("login_attempts")[-1]["score"], rules.FACE_THRESHOLD)

    def test_third_failure_locks_for_five_minutes(self):                 # UC-02 E3, R2
        for _ in range(2):
            with self.assertRaises(LoginError):
                self.auth.login("pat", FACE, self.face("stranger"))
        with self.assertRaises(LoginError) as cm:
            self.auth.login("pat", FACE, self.face("stranger"))
        self.assertEqual(cm.exception.kind, "LOCKED")
        with self.assertRaises(LoginError) as cm:                       # even the right face is refused
            self.auth.login("pat", FACE, self.face("pat", 1))
        self.assertEqual(cm.exception.kind, "LOCKED")
        self.clock.advance(rules.LOCK_MINUTES)
        self.assertEqual(self.auth.login("pat", FACE, self.face("pat", 1)).role, rules.RC)

    def test_lock_expiry_gives_three_fresh_tries(self):                  # DEVIATION D-15
        for _ in range(3):
            with self.assertRaises(LoginError):
                self.auth.login("pat", FACE, self.face("stranger"))
        self.clock.advance(rules.LOCK_MINUTES + 1)
        with self.assertRaises(LoginError) as cm:   # SRS pseudo-code would say LOCKED here
            self.auth.login("pat", FACE, self.face("stranger"))
        self.assertEqual((cm.exception.kind, cm.exception.attempts_left), ("NO_MATCH", 2))

    def test_success_resets_failure_count(self):
        for _ in range(2):
            with self.assertRaises(LoginError):
                self.auth.login("pat", FACE, self.face("stranger"))
        self.auth.login("pat", FACE, self.face("pat", 1))
        with self.assertRaises(LoginError) as cm:
            self.auth.login("pat", FACE, self.face("stranger"))
        self.assertEqual(cm.exception.attempts_left, 2)

    def test_no_face_or_short_audio_not_counted(self):                   # UC-02 E5
        with self.assertRaises(NoFaceError):
            self.auth.login("pat", FACE, self.face(None, faces=0))
        with self.assertRaises(NoVoiceError):
            self.auth.login("pat", VOICE, self.voice(220, seconds=1.0))
        self.assertEqual(self.fs.load("login_attempts"), [])

    def test_missing_template(self):                                     # UC-02 E6
        other = self.auth.register("Vox", "vox", "v@x.com", None, self.voice(150))
        with self.assertRaises(TemplateMissingError):
            self.auth.login(other["username"], FACE, self.face("vo"))

    def test_suspended_user_gets_wallet_only_session(self):              # UC-02 E4, R8
        self.fs.update("users", "user_id", self.user["user_id"], {"status": rules.SUSPENDED})
        s = self.auth.login("pat", FACE, self.face("pat", 1))
        self.assertTrue(s.wallet_only)
        with self.assertRaises(PermissionError):
            s.require(rules.RC, rules.VC)                  # active actions refused
        s.require(rules.RC, rules.VC, active=False)        # wallet allowed

    def test_logout_returns_to_visitor(self):
        s = self.auth.login("pat", FACE, self.face("pat", 1))
        self.auth.logout(s)
        self.assertEqual((s.user, s.role), (None, rules.VISITOR))
