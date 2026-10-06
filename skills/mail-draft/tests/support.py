"""A throwaway copy of the fixture Bridge per test, so no test writes into the tree."""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from pathlib import Path

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "bridge"


class BridgeCase(unittest.TestCase):
    """setUp copies the fixture and points MAIL_DRAFT_ROOT at the copy."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="mail-draft-test-")
        self.root = Path(self._tmp) / "bridge"
        shutil.copytree(FIXTURE, self.root)
        (self.root / "skills").mkdir(exist_ok=True)
        self._old = os.environ.get("MAIL_DRAFT_ROOT")
        os.environ["MAIL_DRAFT_ROOT"] = str(self.root)

    def tearDown(self):
        if self._old is None:
            os.environ.pop("MAIL_DRAFT_ROOT", None)
        else:
            os.environ["MAIL_DRAFT_ROOT"] = self._old
        shutil.rmtree(self._tmp, ignore_errors=True)

    def write(self, rel: str, text: str) -> Path:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def cfg(self):
        from engine.config import load
        return load(self.root)

    def build(self, **kw):
        from engine.draft import Request, build
        kw.setdefault("subject", "Hello")
        kw.setdefault("body", "Body text.")
        return build(Request(**kw), self.cfg())
