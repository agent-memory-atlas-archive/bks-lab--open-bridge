"""Which profile, footer, language and form of address a draft gets."""

from __future__ import annotations

import unittest

from tests.support import BridgeCase


class ProfileSelectionOrder(BridgeCase):
    def test_flag_beats_everything(self):
        d = self.build(to=["family/sam"], profile="everyday")
        self.assertEqual(d.profile_id, "everyday")

    def test_mandant_profile_beats_type_rule(self):
        d = self.build(to=["family/sam"])
        self.assertEqual(d.profile_id, "family")

    def test_person_profile_beats_mandant_profile(self):
        text = (self.root / "identity/mandants/family.yaml").read_text()
        self.write("identity/mandants/family.yaml",
                   text.replace("    display_name: Sam\n", "    display_name: Sam\n    mail_profile: everyday\n"))
        d = self.build(to=["family/sam"])
        self.assertEqual(d.profile_id, "everyday")

    def test_type_rule_picks_application_for_a_company(self):
        d = self.build(to=["acme/ben"], attachments=[str(self.root / "cv.pdf")])
        self.assertEqual(d.profile_id, "application")

    def test_tag_rule(self):
        self.write("workflow/mail-profiles/tagged.yaml",
                   "schema_version: 1\nscope: user\nid: tagged\napplies_to: {tags: [vip]}\n")
        self.write("identity/mandants/club.yaml",
                   "schema_version: 1\nscope: user\nid: club\ntype: friends\ndisplay_name: Club\ntags: [vip]\n"
                   "persons:\n  - {id: kim, display_name: Kim, channels: {email: kim@club.example}}\n")
        d = self.build(to=["club/kim"])
        self.assertEqual(d.profile_id, "tagged")

    def test_unknown_address_falls_to_the_default_profile(self):
        d = self.build(to=["someone@else.example"])
        self.assertEqual(d.profile_id, "everyday")

    def test_config_default_beats_default_flag(self):
        self.write("bridge-config.yaml", "mail:\n  default_profile: family\n")
        d = self.build(to=["someone@else.example"])
        self.assertEqual(d.profile_id, "family")

    def test_no_profiles_means_builtin(self):
        for p in (self.root / "workflow/mail-profiles").glob("*.yaml"):
            p.unlink()
        d = self.build(to=["someone@else.example"])
        self.assertEqual(d.profile_id, "builtin")

    def test_two_defaults_are_refused(self):
        from engine.config import ConfigError
        self.write("workflow/mail-profiles/other.yaml",
                   "schema_version: 1\nscope: user\nid: other\ndefault: true\n")
        with self.assertRaises(ConfigError):
            self.build(to=["someone@else.example"])

    def test_every_decision_is_explained(self):
        d = self.build(to=["acme/anna"], attachments=[str(self.root / "cv.pdf")])
        text = d.explain()
        self.assertIn("applies_to type company", text)
        self.assertIn("language de: recipient", text)


class ProfileInheritance(BridgeCase):
    def test_extends_merges_maps_and_child_wins(self):
        from engine import profiles
        merged = profiles.resolve(profiles.available(self.root), "application")
        self.assertEqual(merged["footer"], "contact")                  # inherited
        self.assertEqual(merged["footer_style"], "card")               # overridden
        self.assertEqual(merged["greeting"]["fallback"], "Hello,")     # deep-merged map

    def test_default_and_applies_to_are_not_inherited(self):
        from engine import profiles
        merged = profiles.resolve(profiles.available(self.root), "family")
        self.assertNotIn("default", merged)

    def test_extends_loop_is_refused(self):
        from engine import profiles
        from engine.config import ConfigError
        files = {"a": {"extends": "b"}, "b": {"extends": "a"}}
        with self.assertRaises(ConfigError):
            profiles.resolve(files, "a")


class LanguageAndAddress(BridgeCase):
    def test_recipient_language_picks_profile_and_footer_variant(self):
        d = self.build(to=["acme/anna"], attachments=[str(self.root / "cv.pdf")])
        self.assertEqual(d.language, "de")
        self.assertTrue(d.subject.startswith("[de] Application:"))
        self.assertIn("[de] Consultant", d.text)
        self.assertIn("[de] Dear Anna Schmidt,", d.text)

    def test_lang_flag_beats_recipient(self):
        d = self.build(to=["acme/anna"], lang="en", attachments=[str(self.root / "cv.pdf")])
        self.assertEqual(d.subject, "Application: Hello")
        self.assertIn("Independent consultant", d.text)

    def test_missing_variant_is_reported(self):
        d = self.build(to=["acme/anna"], lang="fr", attachments=[str(self.root / "cv.pdf")])
        self.assertTrue(any("no 'fr' variant" in w for w in d.warnings))

    def test_recipient_form_of_address(self):
        d = self.build(to=["family/sam"])
        self.assertEqual(d.address_form, "informal")
        self.assertIn("Hey Sam,", d.text)


if __name__ == "__main__":
    unittest.main()
