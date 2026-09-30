"""The plugin package: manifests agree with each other and with the skill on disk."""
import json
import os
import re
import unittest

from helpers import ROOT, SCRIPTS, SKILL

AUTHOR = "Yanjun Qi"


def frontmatter(text):
    m = re.match(r"---\n(.*?)\n---\n", text, re.S)
    return dict(re.findall(r"^(\w+): (.*)$", m.group(1), re.M)) if m else {}


class Plugin(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plugin = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())
        cls.market = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text())
        cls.skill_md = (SKILL / "SKILL.md").read_text()

    def test_manifests_agree(self):
        entry = self.market["plugins"][0]
        self.assertEqual(entry["name"], self.plugin["name"])
        self.assertEqual(entry["source"], "./")

    def test_version_is_semver(self):
        self.assertRegex(self.plugin["version"], r"^\d+\.\d+\.\d+$")

    def test_author_is_yanjun_qi(self):
        self.assertEqual(self.plugin["author"]["name"], AUTHOR)
        self.assertEqual(self.market["owner"]["name"], AUTHOR)
        self.assertEqual(self.market["plugins"][0]["author"]["name"], AUTHOR)
        self.assertIn(f"Copyright (c) 2026 {AUTHOR}\n", (ROOT / "LICENSE").read_text())

    def test_skill_frontmatter(self):
        fm = frontmatter(self.skill_md)
        self.assertEqual(fm.get("name"), SKILL.name)
        self.assertTrue(0 < len(fm.get("description", "")) <= 1024)

    def test_files_named_in_skill_md_exist(self):
        for rel in set(re.findall(r"`((?:scripts|references|assets)/[\w./-]+\.\w+)`", self.skill_md)):
            self.assertTrue((SKILL / rel).exists(), rel)

    def test_scripts_are_executable(self):
        for p in SCRIPTS.iterdir():
            if p.suffix in (".py", ".sh") and p.name != "tts_common.py":
                self.assertTrue(os.access(p, os.X_OK), p.name)


if __name__ == "__main__":
    unittest.main()
