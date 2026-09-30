"""Check markdown links inside project skills (stdlib only, ASCII-only).

Verifies every relative link in .cursor/skills/*/SKILL.md resolves to a
file in the repo. External http(s)/mailto links are skipped (reported).
Exit 0 = all resolve, 1 = broken links found.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILLS_DIR = ROOT / ".cursor" / "skills"
LINK = re.compile(r"\]\(([^)]+)\)")


def main():
    broken = []
    external = 0
    checked = 0
    for skill_file in sorted(SKILLS_DIR.glob("*/SKILL.md")):
        text = skill_file.read_text(encoding="utf-8")
        for match in LINK.finditer(text):
            ref = match.group(1).strip()
            if re.match(r"https?://", ref) or ref.startswith("mailto:"):
                external += 1
                continue
            path_part = ref.split("#")[0].strip()
            if not path_part:
                continue
            target = (skill_file.parent / path_part).resolve()
            checked += 1
            try:
                target.relative_to(ROOT)
            except ValueError:
                broken.append((str(skill_file), ref, "escapes repo"))
                continue
            if not target.exists():
                broken.append((str(skill_file), ref, "missing"))
    print("checked %d local links (%d external skipped)" % (checked, external))
    for skill_file, ref, why in broken:
        print("BROKEN: %s -> %s (%s)" % (skill_file, ref, why))
    if broken:
        print("LINKS: FAIL (%d)" % len(broken))
        return 1
    print("LINKS: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
