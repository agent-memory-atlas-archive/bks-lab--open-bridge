"""The mutation battery: proof that this suite notices when a guard is softened.

Each entry softens ONE literal in one engine source and names the ONE test that
has to turn red. `scripts/tests/mutate.py` applies each to a scratch copy, never
to the working tree. A needle that stays green means the suite does not examine
that behaviour, whatever the test's name promises.

Every guard here is a mail that went wrong, or would have: the body in argv and
nothing created, a draft that was only a window, a stale "away until" notice, a
footer field that rendered markup, a customer mail dressed with the family
profile, an attachment named in the text and missing from the mail.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Mutation:
    """One softening, and the single test that has to notice it."""

    name: str
    file: str
    search: str
    replace: str
    test: str
    scar: str


APPLE = "engine/clients/apple_mail.py"
OUTLOOK = "engine/clients/outlook.py"
FOOTER = "engine/footer.py"
MARKDOWN = "engine/markdown.py"
PROFILES = "engine/profiles.py"
LINT = "engine/lint.py"
DRAFT = "engine/draft.py"
THEME = "engine/theme.py"
MIME = "engine/mime.py"
VALIDATE = "engine/validate.py"
CLI = "engine/cli.py"

MUTATIONS = (
    Mutation(
        name="invisible-outgoing-message",
        file=APPLE,
        search="set m to make new outgoing message with properties {subject:theSubject, visible:true}",
        replace="set m to make new outgoing message with properties {subject:theSubject, visible:false}",
        test="tests.test_envelope.ClientHandoff.test_apple_mail_never_leaves_an_invisible_message",
        scar="seven invisible test messages kept re-saving a deleted draft into Drafts until Mail quit",
    ),
    Mutation(
        name="apple-mail-gets-dark-rules",
        file=APPLE,
        search="    write_inputs(d, workdir, html=d.html_static)",
        replace="    write_inputs(d, workdir, html=d.html)",
        test="tests.test_envelope.ClientHandoff.test_apple_mail_gets_no_dark_rules",
        scar="Mail rendered the draft once under the Mac's dark appearance and froze pale text into it",
    ),
    Mutation(
        name="dark-switch-ignored",
        file=MARKDOWN,
        search='        dark_block, ogsc, scheme = "", "", "light"',
        replace='        pass',
        test="tests.test_envelope.ClientHandoff.test_apple_mail_gets_no_dark_rules",
        scar="a shadowed parameter kept the dark rules in the static copy; found only by reading the saved draft",
    ),
    Mutation(
        name="sender-claimed-without-read-back",
        file=APPLE,
        search="        if d.sender.lower() in actual.lower():",
        replace="        if True:",
        test="tests.test_envelope.ClientHandoff.test_sender_that_did_not_stick_is_reported",
        scar="Mail accepts any sender silently and keeps its default account; the report said 'set'",
    ),
    Mutation(
        name="apple-mail-body-travels-in-argv",
        file=APPLE,
        search='done = osascript(SCRIPT, [str(workdir), "show" if show else "hide"])',
        replace='done = osascript(SCRIPT, [str(workdir), "show" if show else "hide", d.html])',
        test="tests.test_envelope.ClientHandoff.test_apple_mail_body_is_a_file_not_an_argument",
        scar="a long HTML body in argv made the mail client create nothing while the script reported success",
    ),
    Mutation(
        name="outlook-body-travels-in-argv",
        file=OUTLOOK,
        search='done = osascript(SCRIPT, [str(workdir), "show" if show else "hide", d.priority or "normal"])',
        replace='done = osascript(SCRIPT, [str(workdir), "show" if show else "hide", d.priority or "normal", d.text])',
        test="tests.test_envelope.ClientHandoff.test_outlook_body_is_a_file_not_an_argument",
        scar="Outlook created no draft at all for a 26 KB body in argv; the summary claimed three attachments",
    ),
    Mutation(
        name="a-window-counts-as-a-draft",
        file=APPLE,
        search="    if count <= before_count:",
        replace="    if False:",
        test="tests.test_envelope.ClientHandoff.test_an_older_draft_with_the_same_subject_does_not_confirm",
        scar="a message that is only an open window disappears with the next restart of the client",
    ),
    Mutation(
        name="script-count-trusted-over-saved-draft",
        file=APPLE,
        search="    if sorted(saved[\"attachments\"]) != expected:",
        replace="    if False:",
        test="tests.test_envelope.ClientHandoff.test_attachment_missing_from_saved_draft_is_not_ok",
        scar="the creating script counted one attachment; the saved draft held none",
    ),
    Mutation(
        name="stale-notice-ships",
        file=FOOTER,
        search="    if end and today > end:\n        return False",
        replace="    if False:\n        return False",
        test="tests.test_render.Footer.test_notice_only_inside_its_window",
        scar="an 'away until' line outlives its date and tells a customer you are on holiday",
    ),
    Mutation(
        name="footer-field-renders-markup",
        file=FOOTER,
        search='''lines.append(f'<div class="e-muted" style="{small}">{e(cfg["role"])}</div>')''',
        replace='''lines.append(f'<div class="e-muted" style="{small}">{cfg["role"]}</div>')''',
        test="tests.test_render.Footer.test_field_markup_is_escaped",
        scar="a footer value is data from a YAML file and must never become markup in a recipient's client",
    ),
    Mutation(
        name="any-string-becomes-a-visitor-name",
        file=FOOTER,
        search="    if not name or not PLAIN_NAME.match(name):",
        replace="    if not name:",
        test="tests.test_render.Footer.test_visitor_query_only_for_a_plain_name",
        scar="an address or markup put into a link a stranger's page then greets them with",
    ),
    Mutation(
        name="javascript-links-pass",
        file=MARKDOWN,
        search='''        if not SAFE_SCHEME.match(href.replace("&amp;", "&")):
            return text''',
        replace='''        if False:
            return text''',
        test="tests.test_render.Links.test_javascript_link_is_not_linked",
        scar="a javascript: or file: link from pasted text reaches the recipient as a live link",
    ),
    Mutation(
        name="person-profile-ignored",
        file=PROFILES,
        search="        if recipient.profile:",
        replace="        if False:",
        test="tests.test_selection.ProfileSelectionOrder.test_person_profile_beats_mandant_profile",
        scar="the one person in a group who needs a different tone gets the group's profile",
    ),
    Mutation(
        name="mandant-profile-ignored",
        file=PROFILES,
        search="        if recipient.mandant_profile:",
        replace="        if False:",
        test="tests.test_selection.ProfileSelectionOrder.test_mandant_profile_beats_type_rule",
        scar="the family gets the default business profile, footer, legal line and all",
    ),
    Mutation(
        name="missing-attachment-is-only-a-warning",
        file=LINT,
        search='            d.errors.append(f"attachment not found: {path}")',
        replace='            d.warnings.append(f"attachment not found: {path}")',
        test="tests.test_words.Preflight.test_missing_file_is_an_error",
        scar="a client dropped an attachment path that did not exist, and the mail went without it",
    ),
    Mutation(
        name="required-attachment-not-enforced",
        file=LINT,
        search='    if require.get("attachments") and not d.attachments:',
        replace='    if False:',
        test="tests.test_words.Preflight.test_required_attachment_missing_is_an_error",
        scar="an application sent without the CV it announces",
    ),
    Mutation(
        name="greeting-doubled",
        file=DRAFT,
        search="        if line and not already:",
        replace="        if line:",
        test="tests.test_words.GreetingAndSignOff.test_body_that_already_greets_is_left_alone",
        scar="'Hi Sam, Hello Sam,' at the top of a mail",
    ),
    Mutation(
        name="unreadable-link-colour-accepted",
        file=THEME,
        search='if role in TEXT_ROLES and contrast(value, colors.get("surface-raised", colors.get("surface", "#ffffff"))) < 4.5:',
        replace='if role in TEXT_ROLES and contrast(value, colors.get("surface-raised", colors.get("surface", "#ffffff"))) < 1.0:',
        test="tests.test_render.Theme.test_link_skips_an_unreadable_accent",
        scar="a brand accent fine for a 72px headline is 2.7:1 as 15px link text",
    ),
    Mutation(
        name="eml-not-marked-unsent",
        file=MIME,
        search='    msg["X-Unsent"] = "1"\n',
        replace="",
        test="tests.test_envelope.Eml.test_eml_is_an_unsent_multipart_with_attachment",
        scar="without X-Unsent the .eml opens as a received mail with no Send button",
    ),
    Mutation(
        name="core-footer-accepted",
        file=VALIDATE,
        search='        if data.get("scope") == "core":',
        replace='        if data.get("scope") == "never":',
        test="tests.test_envelope.Validate.test_core_scope_footer_is_refused",
        scar="a footer holds a name, a phone and an address; scope core would route it to the public upstream",
    ),
    Mutation(
        name="errors-do-not-stop-compose",
        file=CLI,
        search="    if d.errors and not args.force:",
        replace="    if False:",
        test="tests.test_envelope.Cli.test_compose_with_errors_creates_no_draft",
        scar="a draft with a missing attachment or a leftover placeholder lands in the client looking finished",
    ),
    Mutation(
        name="footer-javascript-link-passes",
        file=FOOTER,
        search='    return value if SAFE_URL.match(value) else "#"',
        replace='    return value',
        test="tests.test_review.UntrustedFooterValues.test_javascript_website_is_not_a_link",
        scar="a footer shipped by an org overlay is data; a javascript: website became a live link",
    ),
    Mutation(
        name="badge-colour-escapes-attribute",
        file=FOOTER,
        search='        return value if HEX.match(value) else str(theme.get("primary"))',
        replace='        return value',
        test="tests.test_review.UntrustedFooterValues.test_badge_colour_cannot_leave_its_attribute",
        scar="a colour value closed the style attribute and added an event handler",
    ),
    Mutation(
        name="font-quote-breaks-html",
        file=THEME,
        search="""    family = str(family).strip().replace('"', "'")""",
        replace="""    family = str(family).strip()""",
        test="tests.test_review.DesignValues.test_font_with_double_quotes_stays_inside_the_attribute",
        scar='"Open Sans" in DESIGN.md ended every style attribute of the mail',
    ),
    Mutation(
        name="grey-link-accepted",
        file=THEME,
        search='            if role == "link" and role not in overrides and saturation(value) < 0.2:',
        replace='            if False:',
        test="tests.test_review.DesignValues.test_grey_is_never_the_link_colour",
        scar="open-bridge's own DESIGN.md gave links the grey of muted text",
    ),
    Mutation(
        name="sign-off-phrase-ignored",
        file=DRAFT,
        search="        if first and line.startswith(first):",
        replace="        if False:",
        test="tests.test_review.Words.test_sign_off_without_footer_is_not_doubled",
        scar="'Love, Alex' followed by a second 'Love,' when the profile had no footer",
    ),
    Mutation(
        name="greeting-prefix-match",
        file=DRAFT,
        search='        already = any(re.match(rf"{re.escape(w)}(?![\\w])", opening) for w in words)',
        replace='        already = any(opening.startswith(w) for w in words)',
        test="tests.test_review.Words.test_greeting_word_must_be_a_whole_word",
        scar="'Historically, ...' counted as greeted by 'Hi', so no greeting was added",
    ),
    Mutation(
        name="pipe-in-code-splits-cell",
        file=MARKDOWN,
        search="            if ch == \"|\" and not in_code:",
        replace="            if ch == \"|\":",
        test="tests.test_review.Markdown.test_pipe_inside_code_stays_in_its_cell",
        scar="a | inside a code span split the cell and the last column vanished",
    ),
    Mutation(
        name="root-from-cwd",
        file="engine/config.py",
        search="    return Path(__file__).resolve().parents[3]",
        replace="    return Path.cwd()",
        test="tests.test_review.Root.test_root_is_the_skills_own_tree_not_the_cwd",
        scar="run from inside another instance, the engine read that instance's mandants and footers",
    ),
)
