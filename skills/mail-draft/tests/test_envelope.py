"""Recipients, the .eml, the hand-off to a client, validation, the CLI."""

from __future__ import annotations

import contextlib
import io
import subprocess
import unittest
from pathlib import Path
from unittest import mock

from tests.support import BridgeCase


def fake_osascript(script_answer: str, verify_answers: list[str], calls: list | None = None):
    """A stand-in for subprocess.run: the creating script gets `script_answer`,
    each read-back of Drafts gets the next of `verify_answers` (before, after)."""
    verify = iter(verify_answers)

    def run(cmd, **kw):
        script = kw.get("input", "")
        if calls is not None:
            calls.append((cmd, script))
        is_create = "make new outgoing message" in script
        out = script_answer if is_create else next(verify)
        return subprocess.CompletedProcess(cmd, 0, out, "")
    return run


class Recipients(BridgeCase):
    def resolve(self, *tokens):
        from engine import recipients
        return recipients.resolve(self.root, list(tokens))

    def test_forms(self):
        self.assertEqual(self.resolve("acme/anna")[0].address, "anna@acme.example")
        self.assertEqual(self.resolve("sam")[0].address, "sam@example.org")
        self.assertEqual(len(self.resolve("mandant:acme")), 2)

    def test_known_address_brings_name_and_language(self):
        r = self.resolve("anna@acme.example")[0]
        self.assertEqual((r.name, r.language), ("Anna Schmidt", "de"))

    def test_duplicates_collapse(self):
        self.assertEqual(len(self.resolve("acme/anna", "anna@acme.example", "mandant:acme")), 2)

    def test_errors_name_the_problem(self):
        from engine.config import ConfigError
        for bad, words in (("nobody", "neither an address"), ("acme/zed", "no person"),
                           ("mandant:none", "not defined"), ("x@", "not an email")):
            with self.subTest(bad=bad), self.assertRaisesRegex(ConfigError, words):
                self.resolve(bad)


class Eml(BridgeCase):
    def test_eml_is_an_unsent_multipart_with_attachment(self):
        from engine import mime
        d = self.build(to=["acme/ben"], attachments=[str(self.root / "cv.pdf")])
        raw = bytes(mime.build(d)).decode("utf-8", "replace")
        self.assertIn("X-Unsent: 1", raw)
        self.assertIn("text/plain", raw)
        self.assertIn("text/html", raw)
        self.assertIn('filename="cv.pdf"', raw)
        self.assertIn("From: alex@example.com", raw)


class ClientHandoff(BridgeCase):
    """The body must never travel in argv, and nothing may call send."""

    def run_client(self, module_name):
        import importlib
        client = importlib.import_module(f"engine.clients.{module_name}")
        d = self.build(to=["family/sam"], body="SECRET-BODY-MARKER " * 50)
        calls = []
        script_answer = ("OK|sender=yes|to=1|attachments=0|closed=yes|from=alex@example.com"
                         if module_name == "apple_mail" else "OK|attachments=0")
        fake_run = fake_osascript(script_answer, ["0", "1"], calls)
        with mock.patch("engine.clients.subprocess.run", side_effect=fake_run):
            result = client.handoff(d, Path(self._tmp) / "handoff", show=True)
        return d, calls, result

    def test_apple_mail_body_is_a_file_not_an_argument(self):
        d, calls, result = self.run_client("apple_mail")
        for cmd, script in calls:
            self.assertNotIn("SECRET-BODY-MARKER", " ".join(cmd))
            self.assertNotIn("SECRET-BODY-MARKER", script)
        self.assertIn("SECRET-BODY-MARKER", (Path(self._tmp) / "handoff" / "body.html").read_text())
        self.assertTrue(result.verified)

    def test_apple_mail_gets_no_dark_rules(self):
        """Mail freezes computed colours under the CURRENT appearance; dark rules
        on a Mac in dark mode froze pale text into a light recipient's mail."""
        self.run_client("apple_mail")
        sent = (Path(self._tmp) / "handoff" / "body.html").read_text()
        self.assertNotIn("prefers-color-scheme", sent)
        self.assertNotIn("#191e24", sent)                      # fixture colorsDark.surface-raised

    def test_full_html_keeps_dark_rules(self):
        d = self.build(to=["family/sam"])
        self.assertIn("prefers-color-scheme: dark", d.html)

    def test_attachment_missing_from_saved_draft_is_not_ok(self):
        from engine.clients import apple_mail
        d = self.build(to=["family/sam"], attachments=[str(self.root / "cv.pdf")])
        source = "From: a@b.example\nSubject: x\nContent-Type: text/plain\n\nbody\n"
        with mock.patch("engine.clients.subprocess.run",
                        side_effect=fake_osascript("OK|sender=yes|to=1|attachments=1|from=alex@example.com",
                                                   ["0", "1\n" + source])):
            result = apple_mail.handoff(d, Path(self._tmp) / "h", show=False)
        self.assertFalse(result.ok)
        self.assertIn("attach them by hand", result.detail)

    def test_sender_that_did_not_stick_is_reported(self):
        from engine.clients import apple_mail
        d = self.build(to=["someone@else.example"])
        with mock.patch("engine.clients.subprocess.run",
                        side_effect=fake_osascript("OK|sender=yes|to=1|attachments=0|from=Default <default@example.org>",
                                                   ["0", "1"])):
            result = apple_mail.handoff(d, Path(self._tmp) / "h", show=False)
        self.assertIn("sender NOT alex@example.com", result.detail)

    def test_outlook_body_is_a_file_not_an_argument(self):
        d, calls, result = self.run_client("outlook")
        for cmd, script in calls:
            self.assertNotIn("SECRET-BODY-MARKER", " ".join(cmd))
        self.assertIn("switch 'From'", result.detail)

    def test_apple_mail_never_leaves_an_invisible_message(self):
        """An invisible outgoing message outlives save and re-saves itself into
        Drafts until Mail quits; a deleted test draft came back within 5 s."""
        from engine.clients import apple_mail
        self.assertNotIn("visible:false", apple_mail.SCRIPT)
        self.assertIn("visible:true", apple_mail.SCRIPT)
        self.assertIn("close (every window whose name is theSubject) saving no", apple_mail.SCRIPT)

    def test_outlook_refuses_hide(self):
        from engine.clients import outlook
        d = self.build(to=["family/sam"])
        with mock.patch("engine.clients.subprocess.run") as run:
            result = outlook.handoff(d, Path(self._tmp) / "h", show=False)
        self.assertFalse(result.ok)
        run.assert_not_called()

    def test_outlook_window_not_in_drafts_says_so(self):
        from engine.clients import outlook
        d = self.build(to=["family/sam"])
        with mock.patch("engine.clients.subprocess.run",
                        side_effect=fake_osascript("OK|attachments=0", ["0", "0"])):
            result = outlook.handoff(d, Path(self._tmp) / "h", show=True)
        self.assertFalse(result.verified)
        self.assertIn("Cmd+S", result.detail)

    def test_no_client_script_can_send(self):
        from engine.clients import apple_mail, outlook
        for script in (apple_mail.SCRIPT, outlook.SCRIPT, apple_mail.VERIFY, outlook.VERIFY):
            self.assertNotRegex(script.lower(), r"\bsend\b")

    def test_a_draft_missing_from_drafts_is_not_ok(self):
        from engine.clients import apple_mail
        d = self.build(to=["family/sam"])
        with mock.patch("engine.clients.subprocess.run",
                        side_effect=fake_osascript("OK|sender=yes|to=1|attachments=0", ["0", "0"])):
            result = apple_mail.handoff(d, Path(self._tmp) / "h", show=False)
        self.assertFalse(result.ok)
        self.assertFalse(result.verified)

    def test_an_older_draft_with_the_same_subject_does_not_confirm(self):
        from engine.clients import apple_mail
        d = self.build(to=["family/sam"])
        with mock.patch("engine.clients.subprocess.run",
                        side_effect=fake_osascript("OK|sender=yes|to=1|attachments=0", ["1", "1"])):
            result = apple_mail.handoff(d, Path(self._tmp) / "h", show=False)
        self.assertFalse(result.ok)


try:
    import jsonschema  # noqa: F401
    HAVE_JSONSCHEMA = True
except ImportError:
    HAVE_JSONSCHEMA = False


class Validate(BridgeCase):
    def run_validate(self):
        from engine import validate
        return validate.run(self.root)

    def test_fixture_is_valid(self):
        self.assertEqual(self.run_validate(), [])

    def test_dangling_footer_reference(self):
        self.write("workflow/mail-profiles/bad.yaml", "schema_version: 1\nscope: user\nid: bad\nfooter: gone\n")
        self.assertTrue(any("footer 'gone'" in p for p in self.run_validate()))

    def test_dangling_mandant_reference(self):
        text = (self.root / "identity/mandants/family.yaml").read_text().replace(
            "mail_profile: family", "mail_profile: gone")
        self.write("identity/mandants/family.yaml", text)
        self.assertTrue(any("mail_profile 'gone'" in p for p in self.run_validate()))

    def test_core_scope_footer_is_refused(self):
        text = (self.root / "identity/mail-footers/team.yaml").read_text().replace("scope: org", "scope: core")
        self.write("identity/mail-footers/team.yaml", text)
        self.assertTrue(any("team.yaml" in p and "never scope core" in p for p in self.run_validate()))

    @unittest.skipUnless(HAVE_JSONSCHEMA, "schema checks need jsonschema")
    def test_unknown_field_is_refused(self):
        self.write("identity/mail-footers/odd.yaml", "schema_version: 1\nscope: user\nid: odd\ncolour: red\n")
        self.assertTrue(any("odd.yaml" in p for p in self.run_validate()))

    @unittest.skipUnless(HAVE_JSONSCHEMA, "schema checks need jsonschema")
    def test_shipped_templates_are_valid(self):
        """The CORE _template.yaml files must pass their own schema."""
        from engine import validate
        from engine.config import load_yaml
        repo = Path(__file__).resolve().parents[3]
        for kind, (_, folder) in validate.SCHEMAS.items():
            data = load_yaml(repo / folder / "_template.yaml")
            with self.subTest(kind=kind):
                self.assertEqual(validate.schema_errors(repo, kind, data), [])


class Cli(BridgeCase):
    def cli(self, *argv):
        from engine import cli
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = cli.main(list(argv))
        return code, out.getvalue()

    def test_compose_none_writes_the_bundle(self):
        code, out = self.cli("compose", "--to", "family/sam", "--subject", "Hi", "--body", "Text", "--client", "none")
        self.assertEqual(code, 0, out)
        bundle = next((self.root / ".bridge" / "mail-drafts").iterdir())
        for name in ("source.md", "mail.html", "mail.txt", "mail.eml", "preview.html", "report.txt"):
            self.assertTrue((bundle / name).is_file(), name)

    def test_compose_with_errors_creates_no_draft(self):
        with mock.patch("engine.clients.subprocess.run") as run:
            code, out = self.cli("compose", "--to", "acme/ben", "--subject", "Hi", "--body", "Text",
                                 "--client", "apple-mail")
        self.assertEqual(code, 1)
        self.assertIn("No draft created", out)
        run.assert_not_called()

    def test_validate_command(self):
        code, out = self.cli("validate")
        self.assertEqual(code, 0, out)


if __name__ == "__main__":
    unittest.main()
