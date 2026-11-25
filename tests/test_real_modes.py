"""The "real" model switches (CLAUDE.md): without the optional packages every real mode
falls back to its MOCK and says so in its label. (LLM_MODE: tests/test_llm.py.)"""
import tempfile
import unittest

from bookorbit.app_context import build_context
from bookorbit.config import DEFAULTS


class RealModeFallbackTests(unittest.TestCase):
    def test_biometric_and_cover_real_modes_fall_back_to_labelled_mocks(self):
        ctx = build_context(dict(DEFAULTS, DATA_DIR=tempfile.mkdtemp(prefix="bookorbit_real_"),
                                 BIOMETRIC_MODE="real", COVER_MODE="real"))
        self.assertTrue(ctx.bio.is_mock)
        self.assertIn("MOCK biometrics (real models unavailable", ctx.bio.mode_label)
        self.assertTrue(ctx.covers.is_mock)
        self.assertIn("MOCK cover search (OpenCLIP unavailable", ctx.covers.mode_label)


if __name__ == "__main__":
    unittest.main()
