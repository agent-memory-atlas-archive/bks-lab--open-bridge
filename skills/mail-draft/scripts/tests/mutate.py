"""Apply the mutation battery to a scratch copy and demand that each one goes red.

Same contract as skills/secrets/scripts/tests/mutate.py: copy the skill, soften
one literal, run only the named test, and count it red only when a test RAN and
failed. A test that cannot be loaded, or an anchor that no longer matches
exactly once, is a survivor, because it has stopped proving anything.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SKILL = Path(__file__).resolve().parents[2]
REPO = SKILL.parents[1]
SHIPPED = ("identity/mail-footers/_schema.yaml", "identity/mail-footers/_template.yaml",
           "workflow/mail-profiles/_schema.yaml", "workflow/mail-profiles/_template.yaml")
sys.path.insert(0, str(SKILL))

from tests.mutations import MUTATIONS  # noqa: E402

IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", ".bridge")


def verdict(returncode: int, output: str) -> str:
    if "unittest.loader._FailedTest" in output or "Failed to import test module" in output:
        return "the named test could not be loaded, so its red proves nothing"
    ran = re.search(r"^Ran (\d+) test", output, re.M)
    if ran is None or int(ran.group(1)) == 0:
        return "no test case ran"
    if returncode == 0:
        return "the named test stayed green"
    return "red"


def main() -> int:
    print(f"mutation battery: {len(MUTATIONS)} needle(s), each applied to a scratch copy\n")
    survivors = 0
    for m in MUTATIONS:
        root = Path(tempfile.mkdtemp(prefix="mail-draft-mutate-"))
        # The copy sits at the same depth as in the repo (skills/mail-draft), with
        # the CORE schemas next to it, so a needle is judged by the behaviour it
        # names and not by a schema file the scratch tree happens to lack.
        work = root / "skills" / "mail-draft"
        try:
            shutil.copytree(SKILL, work, ignore=IGNORE)
            for rel in SHIPPED:
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(REPO / rel, root / rel)
            target = work / m.file
            text = target.read_text(encoding="utf-8")
            hits = text.count(m.search)
            if hits != 1:
                print(f"  SURVIVED  {m.name}  (anchor found {hits} times in {m.file})")
                survivors += 1
                continue
            target.write_text(text.replace(m.search, m.replace), encoding="utf-8")
            done = subprocess.run([sys.executable, "-m", "unittest", m.test], cwd=work,
                                  capture_output=True, text=True, timeout=300)
            v = verdict(done.returncode, done.stdout + done.stderr)
            if v == "red":
                print(f"  red       {m.name}")
            else:
                print(f"  SURVIVED  {m.name}\n            {m.test}: {v}\n            lets through: {m.scar}")
                survivors += 1
        finally:
            shutil.rmtree(root, ignore_errors=True)
    print()
    if survivors:
        print(f"{survivors} of {len(MUTATIONS)} mutations SURVIVED the suite")
        return 1
    print(f"{len(MUTATIONS)}/{len(MUTATIONS)} mutations turned their test red")
    return 0


if __name__ == "__main__":
    sys.exit(main())
