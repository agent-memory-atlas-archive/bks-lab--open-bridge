"""Findings of the independent review, each pinned by a test."""

from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest import mock

from tests.support import BridgeCase


class UntrustedFooterValues(BridgeCase):
    """A footer is a YAML file, perhaps from an org overlay; compose does not trust it."""

    def footer_with(self, **fields):
        import yaml
        path = self.root / "identity/mail-footers/contact.yaml"
        data = yaml.safe_load(path.read_text())
        data.update(fields)
        path.write_text(yaml.safe_dump(data, allow_unicode=True))

    def test_javascript_website_is_not_a_link(self):
        self.footer_with(website="javascript:alert(1)")
        d = self.build(to=["someone@else.example"])
        self.assertNotIn('href="javascript:', d.html)
        self.assertTrue(any("is not http(s)" in e for e in d.errors))

    def test_badge_colour_cannot_leave_its_attribute(self):
        self.footer_with(links=[{"badge": "x", "label": "x", "url": "https://example.com",
                                 "color": '#000;" onmouseover="alert(3)'}])
        d = self.build(to=["someone@else.example"], footer_style="card")
        self.assertIn(">x</a>", d.html)                      # the badge really rendered
        self.assertNotIn("onmouseover", d.html)

    def test_child_notice_keeps_the_parent_window(self):
        from engine import footer
        self.write("identity/mail-footers/child.yaml",
                   "schema_version: 1\nscope: user\nid: child\nextends: contact\nnotice: {text: Changed.}\n")
        cfg = footer.load(self.root, "child")
        self.assertEqual(str(cfg["notice"]["until"]), "2026-08-14")


class DesignValues(unittest.TestCase):
    def test_font_with_double_quotes_stays_inside_the_attribute(self):
        from engine.theme import build_design
        t = build_design({"colors": {}, "typography": {"body-md": {"fontFamily": '"Open Sans", Arial'}}})
        self.assertNotIn('"', t["font_body"])

    def test_grey_is_never_the_link_colour(self):
        from engine.theme import build_design, contrast, saturation
        t = build_design({"colors": {"secondary": "#6B7280", "accent": "#6366F1", "surface": "#FFFFFF"}})
        self.assertGreater(saturation(t["link"]), 0.2)
        self.assertGreaterEqual(contrast(t["link"], "#ffffff"), 4.5)


class Words(BridgeCase):
    def test_sign_off_without_footer_is_not_doubled(self):
        d = self.build(to=["family/sam"], body="Text.\n\nLove,\nAlex")
        self.assertEqual(d.markdown.count("Love,"), 1)

    def test_one_line_sign_off_is_recognised(self):
        d = self.build(to=["family/sam"], profile="everyday", body="Text.\n\nBest, Alex")
        self.assertEqual(d.markdown.count("Best"), 1)

    def test_greeting_word_must_be_a_whole_word(self):
        d = self.build(to=["family/sam"], profile="everyday", body="Historically, this worked.")
        self.assertTrue(d.markdown.startswith("Hi Sam,"))

    def test_placeholder_in_code_is_not_an_error(self):
        d = self.build(to=["family/sam"], body="Use `{name}` in the template.")
        self.assertEqual(d.errors, [])

    def test_multiline_subject_is_refused(self):
        from engine.config import ConfigError
        with self.assertRaises(ConfigError):
            self.build(to=["family/sam"], subject="a\nBcc: x@y.example")

    def test_empty_body_is_refused(self):
        from engine.config import ConfigError
        with self.assertRaises(ConfigError):
            self.build(to=["family/sam"], body="  \n")


class Markdown(unittest.TestCase):
    def r(self, **kw):
        from engine.markdown import Renderer
        from engine.theme import BUILTIN, NEUTRAL_DARK, Theme
        return Renderer(Theme(dict(BUILTIN["minimal"]), dict(NEUTRAL_DARK), [], "minimal"), **kw)

    def test_pipe_inside_code_stays_in_its_cell(self):
        html = self.r().render("| a | b |\n|---|---|\n| `x|y` | z |")
        self.assertIn("x|y", html)
        self.assertIn(">z<", html)

    def test_extra_cells_are_kept(self):
        html = self.r().render("| a | b |\n|---|---|\n| 1 | 2 | 3 |")
        self.assertIn("2 | 3", html)

    def test_nul_byte_neither_hangs_nor_crashes(self):
        self.assertIn("ab", self.r().render("a\x00b \x009\x00"))

    def test_alias_to_unknown_badge_is_ignored(self):
        self.assertIn("[x+]", self.r(aliases={"x+": "nope"}).render("[x+]"))

    def test_bold_inside_link_text(self):
        self.assertIn("<strong>b</strong>", self.r().render("[**b**](https://example.com)"))

    def test_rule_survives_in_text_part(self):
        from engine.markdown import to_text
        self.assertIn("-" * 40, to_text("a\n\n---\n\nb"))


class Root(unittest.TestCase):
    def test_root_is_the_skills_own_tree_not_the_cwd(self):
        from engine import config
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("MAIL_DRAFT_ROOT", None)
            with mock.patch("pathlib.Path.cwd", return_value=Path("/tmp")):
                self.assertEqual(config.find_root(), Path(config.__file__).resolve().parents[3])


class ValidateClaims(BridgeCase):
    def test_two_profiles_claiming_one_type(self):
        from engine import validate
        self.write("workflow/mail-profiles/other.yaml",
                   "schema_version: 1\nscope: user\nid: other\napplies_to: {types: [company]}\n")
        self.assertTrue(any("claimed by" in p for p in validate.run(self.root)))


if __name__ == "__main__":
    unittest.main()
