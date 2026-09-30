"""Validate project skills under .cursor/skills (stdlib only, ASCII-only).

Checks: SKILL.md exists, YAML frontmatter with required fields,
name == dirname, kebab-case, nonempty description, local refs exist,
no absolute Helios/qira-os/user-machine paths, no employer skill terms,
no duplicate names, disable-model-invocation true, size guideline.
Exit 0 = pass, 1 = fail.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILLS_DIR = ROOT / ".cursor" / "skills"

REQUIRED_FIELDS = ("name", "description", "disable-model-invocation")
REQUIRED_SECTIONS = (
    "## Purpose",
    "## Preconditions",
    "## Allowed",
    "## Prohibited",
    "## Required inputs",
    "## Workflow",
    "## Validation gates",
    "## Required outputs",
    "## Stop conditions",
)
KEBAB = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
ABS_WIN = re.compile(r"[A-Za-z]:\\")
ABS_NIX = re.compile(r"(^|[\s\"'(`])/home/")

FORBIDDEN_SUBSTRINGS = (
    "helios",
    "qira",
    "qira-os",
    "lenovo",
    "kmp",
    "qnn",
    "android",
)
# Case-sensitive: "Linear" the issue tracker (lowercase "linear" as in
# linear model is legitimate), "FFI" the foreign-function seam.
FORBIDDEN_CASE_SENSITIVE = ("Linear", "FFI")
SIZE_GUIDELINE_LINES = 500
# Pre-existing skills that predate the section standard. Their missing
# sections are reported as WARN (grandfathered), not FAIL. New skills
# must carry all REQUIRED_SECTIONS. Recorded in docs/agent/skills-catalog.md.
GRANDFATHERED_SECTIONS = {"repo-quality-passthrough"}
ERRORS = []
WARNINGS = []


def parse_frontmatter(text):
    if not text.startswith("---"):
        return None, "missing frontmatter fence"
    end = text.find("\n---", 3)
    if end == -1:
        return None, "unterminated frontmatter"
    raw = text[3:end].strip().strip("-").strip()
    data = {}
    for line in raw.splitlines():
        if not line.strip() or line.strip().startswith("#"):
            continue
        if ":" not in line:
            return None, "bad frontmatter line: %r" % line
        key, value = line.split(":", 1)
        data[key.strip()] = value.strip()
    return data, None


def check_skill(skill_dir, seen_names):
    name = skill_dir.name
    skill_file = skill_dir / "SKILL.md"
    if not skill_file.is_file():
        ERRORS.append("%s: SKILL.md missing" % name)
        return
    text = skill_file.read_text(encoding="utf-8")
    lines = text.splitlines()
    if len(lines) > SIZE_GUIDELINE_LINES:
        WARNINGS.append(
            "%s: %d lines exceeds %d guideline"
            % (name, len(lines), SIZE_GUIDELINE_LINES)
        )
    meta, err = parse_frontmatter(text)
    if err:
        ERRORS.append("%s: %s" % (name, err))
        return
    for field in REQUIRED_FIELDS:
        if field not in meta or not meta[field]:
            ERRORS.append("%s: frontmatter field %r missing/empty" % (name, field))
    if meta.get("name") != name:
        ERRORS.append(
            "%s: frontmatter name %r != dirname" % (name, meta.get("name"))
        )
    if not KEBAB.match(name):
        ERRORS.append("%s: not kebab-case" % name)
    if not meta.get("description", "").strip():
        ERRORS.append("%s: empty description" % name)
    if meta.get("name") in seen_names:
        ERRORS.append("%s: duplicate skill name" % name)
    seen_names.add(meta.get("name"))
    if meta.get("disable-model-invocation") != "true":
        ERRORS.append("%s: disable-model-invocation must be true" % name)
    for section in REQUIRED_SECTIONS:
        if section not in text:
            msg = "%s: section %r missing" % (name, section)
            if name in GRANDFATHERED_SECTIONS:
                WARNINGS.append(msg + " (grandfathered)")
            else:
                ERRORS.append(msg)
    lowered = text.lower()
    if ABS_WIN.search(text) or "c:/users" in lowered or ABS_NIX.search(text):
        ERRORS.append("%s: absolute user-machine path found" % name)
    for term in FORBIDDEN_SUBSTRINGS:
        if term in lowered:
            ERRORS.append(
                "%s: forbidden term %r (employer/third-party coupling)" % (name, term)
            )
    for term in FORBIDDEN_CASE_SENSITIVE:
        if term in text:
            ERRORS.append(
                "%s: forbidden term %r (employer/third-party coupling)" % (name, term)
            )
    for match in re.finditer(r"\]\(([^)#][^)]*)\)", text):
        ref = match.group(1).strip()
        if re.match(r"https?://", ref) or ref.startswith("mailto:"):
            continue
        target = (skill_dir / ref).resolve()
        try:
            target.relative_to(ROOT)
        except ValueError:
            ERRORS.append("%s: link escapes repo: %s" % (name, ref))
            continue
        if not target.exists():
            ERRORS.append("%s: local ref missing: %s" % (name, ref))


def main():
    if not SKILLS_DIR.is_dir():
        print("SKILLS_DIR missing: %s" % SKILLS_DIR)
        return 1
    seen = set()
    skills = sorted(p for p in SKILLS_DIR.iterdir() if p.is_dir())
    if not skills:
        print("no skills found")
        return 1
    for skill_dir in skills:
        check_skill(skill_dir, seen)
    print("checked %d skills" % len(skills))
    for warning in WARNINGS:
        print("WARN: %s" % warning)
    for error in ERRORS:
        print("FAIL: %s" % error)
    if ERRORS:
        print("VALIDATE: FAIL (%d)" % len(ERRORS))
        return 1
    print("VALIDATE: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
