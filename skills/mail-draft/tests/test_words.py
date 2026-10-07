"""Greeting, sign-off, snippets and the preflight."""

from __future__ import annotations

import unittest

from tests.support import BridgeCase


class GreetingAndSignOff(BridgeCase):
    def test_greeting_is_added_once(self):
        d = self.build(to=["family/sam"], profile="everyday")
        self.assertTrue(d.markdown.startswith("Hi Sam,"))

    def test_body_that_already_greets_is_left_alone(self):
        d = self.build(to=["family/sam"], profile="everyday", body="Hello Sam,\n\nText.")
        self.assertEqual(d.markdown.count("Sam,"), 1)

    def test_sign_off_is_not_doubled(self):
        d = self.build(to=["family/sam"], profile="everyday", body="Text.\n\nBest,\nAlex")
        self.assertEqual(d.markdown.count("Best,"), 1)

    def test_several_recipients_get_the_fallback(self):
        d = self.build(to=["acme/anna", "acme/ben"], profile="everyday")
        self.assertTrue(d.markdown.startswith("Hello,"))

    def test_no_greeting_flag(self):
        d = self.build(to=["family/sam"], profile="everyday", greeting=False)
        self.assertEqual(d.markdown, "Body text.")


class Snippets(BridgeCase):
    def test_snippet_is_expanded(self):
        d = self.build(to=["acme/ben"], body="{{snippet:availability}}", attachments=[str(self.root / "cv.pdf")])
        self.assertIn("1 November", d.markdown)

    def test_unknown_snippet_is_an_error(self):
        d = self.build(to=["acme/ben"], body="{{snippet:nope}}", attachments=[str(self.root / "cv.pdf")])
        self.assertTrue(any("snippet 'nope'" in e for e in d.errors))


class Preflight(BridgeCase):
    def test_required_attachment_missing_is_an_error(self):
        d = self.build(to=["acme/ben"])
        self.assertTrue(any("requires an attachment" in e for e in d.errors))

    def test_missing_file_is_an_error(self):
        d = self.build(to=["family/sam"], attachments=[str(self.root / "nope.pdf")])
        self.assertTrue(any("attachment not found" in e for e in d.errors))

    def test_promised_attachment_is_a_warning(self):
        d = self.build(to=["family/sam"], body="See the attached report.")
        self.assertTrue(any("nothing is attached" in w for w in d.warnings))

    def test_leftover_placeholder_is_an_error(self):
        d = self.build(to=["family/sam"], body="Dear {customer},")
        self.assertTrue(any("{customer}" in e for e in d.errors))

    def test_deceptive_link_text_is_a_warning(self):
        d = self.build(to=["family/sam"], body="[bank.example](https://evil.example/login)")
        self.assertTrue(any("different host" in w for w in d.warnings))

    def test_tracking_parameters_are_a_warning(self):
        d = self.build(to=["family/sam"], body="https://example.com/?utm_source=mail")
        self.assertTrue(any("tracking" in w for w in d.warnings))

    def test_clean_draft_has_no_errors(self):
        d = self.build(to=["family/sam"])
        self.assertEqual(d.errors, [])


class FooterChoice(BridgeCase):
    def test_footer_false_means_no_footer(self):
        d = self.build(to=["family/sam"])
        self.assertNotIn("Example Studio", d.html)
        self.assertEqual(d.footer_id, "")

    def test_footer_flag_overrides_profile(self):
        d = self.build(to=["family/sam"], footer="team")
        self.assertIn("Example Studio", d.html)

    def test_no_footer_flag(self):
        d = self.build(to=["someone@else.example"], footer="")
        self.assertNotIn("Example Studio", d.html)

    def test_persona_signature_when_profile_has_no_footer(self):
        self.write("workflow/mail-profiles/sig.yaml",
                   "schema_version: 1\nscope: user\nid: sig\npersona_ref: alex\n")
        d = self.build(to=["someone@else.example"], profile="sig")
        self.assertIn("alex@example.com", d.text)

    def test_sender_comes_from_the_footer(self):
        d = self.build(to=["someone@else.example"])
        self.assertEqual(d.sender, "alex@example.com")


if __name__ == "__main__":
    unittest.main()
