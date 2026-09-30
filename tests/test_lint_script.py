"""lint_script.py: the checks that stand in for listening."""
import tempfile
import unittest
from pathlib import Path

from helpers import run_script

SCRIPT = """# Test chapter.

See § 4 and the plus + sign. The results are clear 13

The openweight model beats other open weight models; a checkpoint too.

In case A alone, the NIH panel met.
"""


class Lint(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        d = Path(tempfile.mkdtemp(prefix="pdf2audio-lint-"))
        (d / "00-test.txt").write_text(SCRIPT)
        cls.proc = run_script("lint_script.py", d)
        cls.out = cls.proc.stdout

    def test_runs(self):
        self.assertEqual(self.proc.returncode, 0, self.proc.stderr)

    def test_flags_unspeakable_characters(self):
        self.assertIn("SECTION SIGN", self.out)
        self.assertIn("PLUS SIGN", self.out)

    def test_flags_leaked_page_number(self):
        section = self.out.split("== Stray numbers (leaked page numbers?) ==")[1].split("\n== ")[0]
        self.assertIn("clear 13", section)

    @unittest.skipUnless(Path("/usr/share/dict/words").exists(), "no system word list")
    def test_ranks_fused_word_with_split_form_as_likely(self):
        likely = next(l for l in self.out.splitlines() if l.strip().startswith("likely:"))
        self.assertIn("open-weight", likely)
        self.assertNotIn("check-point", likely)

    def test_lists_acronyms_and_mid_sentence_a(self):
        section = self.out.split("== How acronyms")[1]
        self.assertIn("NIH", section)
        self.assertIn("A (mid-sentence)", section)

    def test_clean_script_reports_none(self):
        d = Path(tempfile.mkdtemp(prefix="pdf2audio-lint-"))
        (d / "00-clean.txt").write_text("# Clean.\n\nA plain sentence, nothing odd.\n")
        out = run_script("lint_script.py", d).stdout
        self.assertIn("Characters a voice may skip or misread ==\n  none", out)


if __name__ == "__main__":
    unittest.main()
