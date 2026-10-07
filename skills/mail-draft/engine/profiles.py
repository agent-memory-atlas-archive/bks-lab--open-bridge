"""Occasions: which profile a draft uses, and what that profile says.

Profiles live in workflow/mail-profiles/<id>.yaml (USER, or org when a team
shares one). They may `extends` each other. The choice is deterministic and
explainable, because a draft dressed for the wrong occasion (the family
footer on a customer mail) is the failure this file exists to prevent:

    1. --profile <id>
    2. the person's `mail_profile`
    3. the mandant's `mail_profile`
    4. a profile whose `applies_to` names the mandant, its type or one of its tags
    5. bridge-config.yaml `mail.default_profile`, then the profile marked `default: true`
    6. the built-in neutral profile

With several recipients the first one decides, and `explain()` says so.
"""

from __future__ import annotations

from pathlib import Path

from .config import ConfigError, load_yaml

FAMILY = ("workflow", "mail-profiles")
MAX_EXTENDS = 5

BUILTIN = {
    "id": "builtin",
    "title": "Built-in neutral profile",
    "theme": "design",
    "masthead": False,
    "greeting": {},
    "sign_off": {},
}


class ProfileError(ConfigError):
    pass


def available(root: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    d = root.joinpath(*FAMILY)
    if d.is_dir():
        for path in sorted(d.glob("*.yaml")):
            if not path.name.startswith("_"):
                out[path.stem] = load_yaml(path)
    return out


def _deep(base: dict, own: dict) -> dict:
    out = dict(base)
    for k, v in own.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep(out[k], v)
        else:
            out[k] = v
    return out


def resolve(files: dict, pid: str, chain: list[str] | None = None) -> dict:
    chain = chain or []
    if pid in chain:
        raise ProfileError(f"profile '{pid}': extends loops back ({' -> '.join(chain + [pid])})")
    if len(chain) >= MAX_EXTENDS:
        raise ProfileError(f"profile '{pid}': extends is nested deeper than {MAX_EXTENDS}")
    if pid not in files:
        where = f"profile '{chain[-1]}' extends '{pid}'" if chain else f"profile '{pid}'"
        known = ", ".join(sorted(files)) or "none"
        raise ProfileError(f"{where}, which is not defined (defined: {known})")
    own = dict(files[pid] or {})
    parent = own.pop("extends", None)
    merged = _deep(resolve(files, parent, chain + [pid]), own) if parent else own
    merged["id"] = pid
    # `default` and `applies_to` describe THIS file's selection, they are not inherited.
    for key in ("default", "applies_to"):
        if key in files[pid]:
            merged[key] = files[pid][key]
        else:
            merged.pop(key, None)
    return merged


def select(files: dict, recipient, requested: str = "", config_default: str = "") -> tuple[dict, str]:
    """(profile, the reason it was chosen)."""
    if requested:
        return resolve(files, requested), f"--profile {requested}"
    if recipient is not None:
        if recipient.profile:
            return resolve(files, recipient.profile), (
                f"person {recipient.mandant_id}/{recipient.person_id} sets mail_profile: {recipient.profile}")
        if recipient.mandant_profile:
            return resolve(files, recipient.mandant_profile), (
                f"mandant {recipient.mandant_id} sets mail_profile: {recipient.mandant_profile}")
        if recipient.mandant_id:
            for pid in sorted(files):
                rule = (files[pid] or {}).get("applies_to") or {}
                if recipient.mandant_id in (rule.get("mandants") or []):
                    return resolve(files, pid), f"profile {pid} applies_to mandant {recipient.mandant_id}"
            for pid in sorted(files):
                rule = (files[pid] or {}).get("applies_to") or {}
                if recipient.mandant_type and recipient.mandant_type in (rule.get("types") or []):
                    return resolve(files, pid), f"profile {pid} applies_to type {recipient.mandant_type}"
            for pid in sorted(files):
                rule = (files[pid] or {}).get("applies_to") or {}
                common = set(recipient.tags) & set(rule.get("tags") or [])
                if common:
                    return resolve(files, pid), f"profile {pid} applies_to tag {sorted(common)[0]}"
    if config_default:
        return resolve(files, config_default), f"bridge-config.yaml mail.default_profile: {config_default}"
    defaults = [pid for pid in sorted(files) if (files[pid] or {}).get("default")]
    if len(defaults) > 1:
        raise ProfileError(f"more than one profile says default: true ({', '.join(defaults)})")
    if defaults:
        return resolve(files, defaults[0]), f"profile {defaults[0]} is marked default: true"
    return dict(BUILTIN), "no profile matched, built-in neutral profile"
