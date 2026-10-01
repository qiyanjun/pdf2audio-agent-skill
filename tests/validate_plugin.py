#!/usr/bin/env python3
"""Validate a Claude Code plugin repo: <root>/.claude-plugin/marketplace.json + <root>/<plugin>/.

The plugin directory comes from the marketplace entry's `source` (here "./", so the
plugin is the repo root). Checks:
  1. every skills/<dir>/SKILL.md has YAML frontmatter with `name` and
     `description`; `name` matches the directory; `description` is within
     the 1024-character limit (longer descriptions are truncated or rejected)
  2. marketplace.json has an entry named like plugin.json, and if that entry
     also states a version it matches plugin.json — a version bump that
     touches only one of them ships a stale cache (plugin.json alone is fine)
  3. every commands/*.md has valid frontmatter with a `description`, and any
     skill it names ("Invoke the `x` skill", "apply the x skill") exists (a
     namespaced skill such as `codebase-schematic:codebase-schematic`
     belongs to another plugin)
  4. every `/<plugin>:<cmd>` mention resolves to commands/<cmd>.md or a skill
     (skills are invocable as slash commands too), and every
     backticked `<plugin>:<skill>` mention resolves to a skill or command
  5. every backticked `references/...` or `scripts/...` path resolves to a
     real file (relative to the skill directory, the referencing file, or the
     plugin root), and so does every ${CLAUDE_PLUGIN_ROOT}/... path
  6. every file name under HANDOFF_DIR matches HANDOFF_FILES — the files
     stages hand to each other; a typo silently breaks resume (only when
     HANDOFF_DIR is set)
  7. every scripts/*.sh file passes `bash -n` and is executable, and every
     scripts/*.py file compiles
  8. <plugin>.plugin, the zip bundle uploaded to claude.ai, matches the
     plugin directory byte for byte — otherwise the web copy is stale (only
     when the bundle exists; for a repo-root plugin it is <root>/<name>.plugin)
"""
import glob
import json
import os
import re
import stat
import subprocess
import sys
import zipfile

try:
    import yaml
except ImportError:
    sys.exit("pyyaml is required: pip install pyyaml")

# ---- per-repo settings -------------------------------------------------------
# Hand-off files under HANDOFF_DIR/ (regexes; rN is a literal revision
# placeholder in the docs). Leave HANDOFF_DIR empty to skip check 6.
HANDOFF_DIR = ""
HANDOFF_FILES = []
# -----------------------------------------------------------------------------

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAX_DESC = 1024
BUNDLE_IGNORE = {".DS_Store"}

# Lines that name a file only to say it no longer exists.
RETIRED_MARKERS = ("Do not look for", "Earlier versions")


def rel(path: str) -> str:
    return os.path.relpath(path, ROOT)


def plugin_dir(errors: list) -> str | None:
    market_json = os.path.join(ROOT, ".claude-plugin", "marketplace.json")
    try:
        market = json.load(open(market_json, encoding="utf-8"))
        source = market["plugins"][0]["source"]
        if isinstance(source, dict):  # e.g. {"source": "git-subdir", "path": "<dir>"}
            source = source.get("path", ".")
    except (OSError, json.JSONDecodeError, KeyError, IndexError) as e:
        errors.append(f"{rel(market_json)}: unreadable or has no plugin entry: {e}")
        return None
    path = os.path.normpath(os.path.join(ROOT, source))
    if not os.path.isdir(path):
        errors.append(f"marketplace source {source!r} is not a directory")
        return None
    return path


def frontmatter(path: str) -> dict | None:
    text = open(path, encoding="utf-8").read()
    match = re.match(r"---\n(.*?)\n---", text, re.S)
    if not match:
        return None
    try:
        data = yaml.safe_load(match.group(1))
    except yaml.YAMLError:
        return None
    return data if isinstance(data, dict) else None


def check_skills(errors: list, plugin: str) -> set:
    names = set()
    for skill_md in sorted(glob.glob(os.path.join(plugin, "skills", "*", "SKILL.md"))):
        dirname = os.path.basename(os.path.dirname(skill_md))
        names.add(dirname)
        fm = frontmatter(skill_md)
        if fm is None:
            errors.append(f"{rel(skill_md)}: frontmatter missing or not valid YAML")
            continue
        if fm.get("name") != dirname:
            errors.append(f"{rel(skill_md)}: name is {fm.get('name')!r} but directory is {dirname!r}")
        desc = " ".join(str(fm.get("description") or "").split())
        if not desc:
            errors.append(f"{rel(skill_md)}: frontmatter missing `description`")
        elif len(desc) > MAX_DESC:
            errors.append(f"{rel(skill_md)}: description is {len(desc)} chars (max {MAX_DESC})")
    if not names:
        errors.append(f"no skills found under {rel(plugin)}/skills")
    return names


def check_manifests(errors: list, plugin: str) -> str | None:
    plugin_json = os.path.join(plugin, ".claude-plugin", "plugin.json")
    market_json = os.path.join(ROOT, ".claude-plugin", "marketplace.json")
    try:
        meta = json.load(open(plugin_json, encoding="utf-8"))
        market = json.load(open(market_json, encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        errors.append(f"manifest unreadable: {e}")
        return None
    entries = [p for p in market.get("plugins", []) if p.get("name") == meta.get("name")]
    if not entries:
        errors.append(f"marketplace.json has no entry named {meta.get('name')!r}")
    elif "version" in entries[0] and entries[0]["version"] != meta.get("version"):
        errors.append(
            f"version mismatch: plugin.json {meta.get('version')} vs "
            f"marketplace.json {entries[0].get('version')}"
        )
    return meta.get("name")


def check_commands(errors: list, plugin: str, skills: set) -> set:
    commands = set()
    for cmd in sorted(glob.glob(os.path.join(plugin, "commands", "*.md"))):
        commands.add(os.path.splitext(os.path.basename(cmd))[0])
        fm = frontmatter(cmd)
        if fm is None:
            errors.append(f"{rel(cmd)}: frontmatter missing or not valid YAML (quote values that start with `[`)")
        elif not fm.get("description"):
            errors.append(f"{rel(cmd)}: frontmatter missing `description`")
        text = open(cmd, encoding="utf-8").read()
        # "Invoke the `x` skill", "Apply the x skill", ...: any named skill must exist.
        for skill in re.findall(r"\bthe `?([a-z][a-z0-9:-]*[a-z0-9])`? skill\b", text):
            if ":" not in skill and skill not in skills:
                errors.append(f"{rel(cmd)}: refers to unknown skill {skill!r}")
    return commands


def check_links(errors: list, plugin: str, name: str, skills: set, commands: set) -> None:
    handoff_re = re.compile(r"^(?:%s)$" % "|".join(HANDOFF_FILES)) if HANDOFF_DIR else None
    ns = re.escape(name)
    docs = sorted(glob.glob(os.path.join(plugin, "**", "*.md"), recursive=True))
    docs += [p for p in (os.path.join(ROOT, "README.md"),) if os.path.exists(p) and p not in docs]
    skills_dir = os.path.join(plugin, "skills")

    for path in docs:
        skill_dir = None
        parts = os.path.relpath(path, skills_dir).split(os.sep)
        if parts[0] != ".." and len(parts) > 1:
            skill_dir = os.path.join(skills_dir, parts[0])
        here = os.path.dirname(path)

        for lineno, line in enumerate(open(path, encoding="utf-8"), 1):
            where = f"{rel(path)}:{lineno}"

            for cmd in re.findall(rf"/{ns}:([a-z][a-z0-9-]*)", line):
                if cmd not in commands and cmd not in skills:
                    errors.append(f"{where}: /{name}:{cmd} is neither commands/{cmd}.md nor a skill")
            for ref in re.findall(rf"`{ns}:([a-z][a-z0-9-]*)`", line):
                if ref not in skills and ref not in commands:
                    errors.append(f"{where}: `{name}:{ref}` is not a skill or command in this plugin")

            if handoff_re:
                for file in re.findall(rf"{re.escape(HANDOFF_DIR)}/([A-Za-z0-9_./-]*[A-Za-z0-9_/-])", line):
                    if not handoff_re.match(file):
                        errors.append(f"{where}: {HANDOFF_DIR}/{file} is not a known hand-off file")

            if skill_dir is None or any(m in line for m in RETIRED_MARKERS):
                continue
            for ref in re.findall(r"`([^`\s]*?(?:references|scripts)/[A-Za-z0-9_.-]+\.(?:md|sh|py|js))`", line):
                candidates = [os.path.join(skill_dir, ref), os.path.join(here, ref), os.path.join(plugin, ref)]
                if not any(os.path.exists(os.path.normpath(c)) for c in candidates):
                    errors.append(f"{where}: `{ref}` does not exist")
            for ref in re.findall(r"\$\{CLAUDE_PLUGIN_ROOT\}/([A-Za-z0-9_./-]+\.(?:md|sh|py|js))", line):
                if not os.path.exists(os.path.join(plugin, ref)):
                    errors.append(f"{where}: ${{CLAUDE_PLUGIN_ROOT}}/{ref} does not exist")


def check_scripts(errors: list, plugin: str) -> None:
    py = glob.glob(os.path.join(plugin, "scripts", "*.py")) + glob.glob(os.path.join(plugin, "skills", "*", "scripts", "*.py"))
    for script in sorted(py):
        try:
            compile(open(script, encoding="utf-8").read(), script, "exec")
        except SyntaxError as e:
            errors.append(f"{rel(script)}: does not compile: {e}")
    for script in sorted(glob.glob(os.path.join(plugin, "skills", "*", "scripts", "*.sh"))):
        if not os.stat(script).st_mode & stat.S_IXUSR:
            errors.append(f"{rel(script)}: not executable")
        result = subprocess.run(["bash", "-n", script], capture_output=True, text=True)
        if result.returncode != 0:
            errors.append(f"{rel(script)}: bash -n failed: {result.stderr.strip()}")


def bundle_path(plugin: str) -> str:
    """<plugin>.plugin beside the plugin directory, or <root>/<name>.plugin when the plugin is the repo root."""
    if os.path.normpath(plugin) == ROOT:
        meta = json.load(open(os.path.join(ROOT, ".claude-plugin", "plugin.json"), encoding="utf-8"))
        return os.path.join(ROOT, meta["name"] + ".plugin")
    return plugin + ".plugin"


def plugin_files(plugin: str) -> dict:
    files = {}
    skip_dirs = {"__pycache__"}
    if os.path.normpath(plugin) == ROOT:  # repo-root plugin: leave out repo-only material
        skip_dirs |= {".git", ".github", "tests", "evals", "docs"}
    for root, dirs, names in os.walk(plugin):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for f in names:
            if f not in BUNDLE_IGNORE and not f.endswith(".plugin"):
                path = os.path.join(root, f)
                files[os.path.relpath(path, plugin).replace(os.sep, "/")] = path
    return files


def check_bundle(errors: list, plugin: str) -> None:
    bundle = bundle_path(plugin)
    if not os.path.exists(bundle):
        return
    fix = f"rebuild with: python3 {rel(__file__)} --rebuild-bundle"
    try:
        zf = zipfile.ZipFile(bundle)
    except zipfile.BadZipFile:
        errors.append(f"{rel(bundle)}: not a valid zip; {fix}")
        return
    in_zip = {n for n in zf.namelist() if not n.endswith("/") and os.path.basename(n) not in BUNDLE_IGNORE}
    on_disk = plugin_files(plugin)
    stale = sorted(n for n in in_zip & on_disk.keys() if zf.read(n) != open(on_disk[n], "rb").read())
    missing = sorted(on_disk.keys() - in_zip)
    extra = sorted(in_zip - on_disk.keys())
    for label, names in (("differs from source", stale), ("missing from bundle", missing), ("only in bundle", extra)):
        if names:
            shown = ", ".join(names[:5]) + (f" (+{len(names) - 5} more)" if len(names) > 5 else "")
            errors.append(f"{rel(bundle)}: {label}: {shown}; {fix}")


def rebuild_bundle(plugin: str) -> None:
    """Write <plugin>.plugin as a flat zip of the plugin directory, sorted for stable output."""
    bundle = bundle_path(plugin)
    with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, path in sorted(plugin_files(plugin).items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.external_attr = (os.stat(path).st_mode & 0o777) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, open(path, "rb").read())
    print(f"rebuilt {rel(bundle)}")


def main() -> int:
    errors = []
    plugin = plugin_dir(errors)
    if plugin is None:
        print(f"ERROR {errors[0]}")
        return 1
    if "--rebuild-bundle" in sys.argv:
        rebuild_bundle(plugin)

    skills = check_skills(errors, plugin)
    name = check_manifests(errors, plugin) or os.path.basename(plugin)
    commands = check_commands(errors, plugin, skills)
    check_links(errors, plugin, name, skills, commands)
    check_scripts(errors, plugin)
    check_bundle(errors, plugin)

    if errors:
        print(f"{len(errors)} error(s):")
        for error in errors:
            print(f"  ERROR {error}")
        return 1

    print(f"{name}: 0 errors ({len(skills)} skills, {len(commands)} commands)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
