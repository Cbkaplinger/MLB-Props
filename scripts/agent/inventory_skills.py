"""Dry-run inventory of agent skills (stdlib only, ASCII-only).

Lists .cursor/skills, .agents/skills, and .cursor/rules as a table:
Skill | Location | Scope | Auto | Slash | Relevant | Conflict.
Read-only; writes nothing. Exit 0 always (inventory never fails).
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def frontmatter_description(skill_file):
    try:
        text = skill_file.read_text(encoding="utf-8")
    except OSError:
        return "(unreadable)"
    if not text.startswith("---"):
        return "(no frontmatter)"
    end = text.find("\n---", 3)
    if end == -1:
        return "(unterminated frontmatter)"
    for line in text[3:end].splitlines():
        if line.strip().startswith("description:"):
            return line.split(":", 1)[1].strip()[:100]
    return "(no description)"


def main():
    rows = []
    for base, scope in ((".cursor/skills", "project"), (".agents/skills", "project-legacy")):
        base_dir = ROOT / base
        if not base_dir.is_dir():
            continue
        for skill_dir in sorted(p for p in base_dir.iterdir() if p.is_dir()):
            skill_file = skill_dir / "SKILL.md"
            desc = frontmatter_description(skill_file) if skill_file.is_file() else "(no SKILL.md)"
            rows.append((skill_dir.name, base, scope, "no", "/" + skill_dir.name, desc, "none"))
    rules_dir = ROOT / ".cursor" / "rules"
    if rules_dir.is_dir():
        for rule in sorted(rules_dir.glob("*.mdc")):
            rows.append((rule.stem, ".cursor/rules", "always-on/custom", "n/a", "n/a", "rule", "none"))
    print("| Skill | Location | Scope | Auto | Slash | Relevant | Conflict |")
    print("| --- | --- | --- | --- | --- | --- | --- |")
    for row in rows:
        print("| %s |" % " | ".join(row))
    print("")
    print("total: %d entries" % len(rows))


if __name__ == "__main__":
    main()
