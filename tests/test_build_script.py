"""build_script.py: turning a pdftotext dump plus narration.json into chapter scripts.

Several tests pin down bugs found while narrating real documents; those say so in their
docstrings, so a failure explains what a listener would hear.
"""
import os
import tempfile
import time
import unittest
from pathlib import Path

from helpers import body, build, paragraphs

CHAPTERS = {"chapter_headings": [r"^\d (Intro|Method)"]}


class Structure(unittest.TestCase):
    def test_drop_lines_and_chapters(self):
        proc, files = build(["1 Intro", "Kept text.", "12", "More text.", "2 Method", "Method text."],
                            dict(CHAPTERS, drop_lines=[[3, 3]]))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(list(files), ["00-1-intro.txt", "01-2-method.txt"])
        self.assertEqual(files["00-1-intro.txt"], "# 1 Intro.\n\nKept text. More text.\n")
        self.assertNotIn("12", body(files))

    def test_chapter_names_and_heading_rewrites(self):
        proc, files = build(["1 Intro", "Text.", "1.1 Scope", "Scope text."],
                            dict(CHAPTERS, chapter_names=["intro"], section_headings=[r"^\d\.\d [A-Z]"],
                                 heading_rewrites=[[r"^(\d(?:\.\d)?) ", r"Section \1. "]]))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(paragraphs(files["00-intro.txt"]),
                         ["# Section 1. Intro.", "Text.", "## Section 1.1. Scope.", "Scope text.\n"])

    def test_chapter_names_count_mismatch_is_an_error(self):
        proc, _ = build(["1 Intro", "a", "2 Method", "b"], dict(CHAPTERS, chapter_names=["only-one"]))
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("chapter_names has 1 entries but 2 chapters", proc.stderr)

    def test_text_before_first_heading_uses_title(self):
        proc, files = build(["Preamble text.", "1 Intro", "Body."], dict(CHAPTERS, title="My Paper"))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(files["00-my-paper.txt"].startswith("# My Paper.\n\nPreamble text."))

    def test_stale_chapter_removed_and_unchanged_file_keeps_mtime(self):
        """synth.py skips chapters whose WAV is newer than the text, so rewriting an unchanged
        file would force pointless re-narration, and a leftover file would be narrated."""
        out_dir = Path(tempfile.mkdtemp(prefix="pdf2audio-test-")) / "script"
        build(["1 Intro", "Text.", "2 Method", "More."], CHAPTERS, out_dir=out_dir)
        first = out_dir / "00-1-intro.txt"
        old = time.time() - 3600
        os.utime(first, (old, old))
        build(["1 Intro", "Text."], CHAPTERS, out_dir=out_dir)
        self.assertAlmostEqual(first.stat().st_mtime, old, delta=1)
        self.assertFalse((out_dir / "01-2-method.txt").exists())


class Paragraphs(unittest.TestCase):
    def test_numbered_line_after_sentence_starts_a_paragraph(self):
        proc, files = build(["1 Intro", "We list three items:", "1. First item.", "2. Second item."], CHAPTERS)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("1. First item.", paragraphs(body(files)))

    def test_wrapped_line_starting_with_a_number_does_not_split(self):
        """Found in a real draft: "...the output of Aim / 3. She..." was split mid-sentence."""
        proc, files = build(["1 Intro", "as described in Section", "2. The model then runs."], CHAPTERS)
        self.assertIn("as described in Section 2. The model then runs.", body(files))

    def test_bullets_start_paragraphs_and_lose_their_marker(self):
        proc, files = build(["1 Intro", "Lead in:", "• one point", "• another point"], CHAPTERS)
        self.assertEqual(paragraphs(files["00-1-intro.txt"])[1:], ["Lead in:", "one point", "another point\n"])

    def test_paragraph_starts_and_extra_patterns_add_to_defaults(self):
        proc, files = build(["1 Intro", "Some text.", "Proposed. We do X.", "Term", "definition here.",
                             "• bullet"],
                            dict(CHAPTERS, paragraph_starts=["Proposed."], paragraph_start_patterns=["^Term$"]))
        paras = paragraphs(files["00-1-intro.txt"])
        self.assertIn("Proposed. We do X.", paras)
        self.assertIn("Term definition here.", paras)
        self.assertIn("bullet\n", paras)  # default bullet rule still active

    def test_paragraph_breaks_before_splits_mid_line(self):
        proc, files = build(["1 Intro", "End of one idea. Limitations. The next part."],
                            dict(CHAPTERS, paragraph_breaks_before=["Limitations."]))
        self.assertEqual(paragraphs(files["00-1-intro.txt"])[1:],
                         ["End of one idea.", "Limitations. The next part.\n"])

    def test_blank_line_paragraph_mode(self):
        proc, files = build(["1 Intro", "First para", "continues.", "", "Second para."],
                            dict(CHAPTERS, blank_line_is_paragraph_break=True))
        self.assertEqual(paragraphs(files["00-1-intro.txt"])[1:], ["First para continues.", "Second para.\n"])


class Inserts(unittest.TestCase):
    def test_inserts_on_one_anchor_keep_config_order(self):
        """Found in real use: several inserts on one anchor came out reversed."""
        proc, files = build(["1 Intro", "As Figure 1 shows, it works."],
                            dict(CHAPTERS, inserts=[{"after": "Figure 1", "text": "First."},
                                                    {"after": "Figure 1", "text": "Second."}]))
        self.assertEqual(paragraphs(files["00-1-intro.txt"])[2:], ["First.", "Second.\n"])

    def test_chapter_start_insert_for_a_table_only_chapter(self):
        proc, files = build(["1 Intro", "Text.", "2 Method"],
                            dict(CHAPTERS, inserts=[{"chapter_start": "Method", "text": "Table walk-through."}]))
        self.assertEqual(files["01-2-method.txt"], "# 2 Method.\n\nTable walk-through.\n")

    def test_missing_anchor_fails_loudly(self):
        proc, _ = build(["1 Intro", "Text."], dict(CHAPTERS, inserts=[{"after": "nowhere", "text": "x"}]))
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("nowhere", proc.stderr)


class Cleaning(unittest.TestCase):
    def test_citations_removed_by_default(self):
        proc, files = build(["1 Intro", "Prior work [3, 7] and more [12]."], CHAPTERS)
        self.assertIn("Prior work and more.", body(files))

    def test_keep_citations(self):
        proc, files = build(["1 Intro", "Prior work [3]."], dict(CHAPTERS, keep_citations=True))
        self.assertIn("Prior work [3].", body(files))

    def test_pre_substitutions_run_before_citation_removal(self):
        proc, files = build(["1 Intro", "We adapt the score of [41]."],
                            dict(CHAPTERS, pre_substitutions=[[r"of \[41\]", "of reference 41"]]))
        self.assertIn("the score of reference 41.", body(files))

    def test_greek_question_mark_becomes_semicolon(self):
        """Found in real use: pandoc/xdvipdfmx PDFs write every ';' as U+037E, which the voice
        skips, and which silently broke config regexes containing ';'."""
        proc, files = build(["1 Intro", "first part; second part."],
                            dict(CHAPTERS, substitutions=[["part; second", "part; then second"]]))
        self.assertIn("first part; then second part.", body(files))
        self.assertNotIn(";", body(files))

    def test_ligatures_folded(self):
        proc, files = build(["1 Intro", "the ﬁrst result."], CHAPTERS)
        self.assertIn("the first result.", body(files))

    def test_dehyphenate_and_substitutions(self):
        proc, files = build(["1 Intro", "An openweight model with HHH training."],
                            dict(CHAPTERS, dehyphenate={"openweight": "open-weight"},
                                 substitutions=[[r"\bHHH\b", "H H H"]]))
        self.assertIn("An open-weight model with H H H training.", body(files))

    def test_long_numbers_spelled_digit_by_digit(self):
        proc, files = build(["1 Intro", "Award 2124538 in 2026."], dict(CHAPTERS, spell_digits_from=7))
        self.assertIn("Award 2 1 2 4 5 3 8 in 2026.", body(files))

    def test_paragraph_emptied_by_substitution_is_dropped(self):
        proc, files = build(["1 Intro", "Text.", "Table header"],
                            dict(CHAPTERS, paragraph_starts=["Table header"],
                                 substitutions=[["^Table header$", ""]]))
        self.assertEqual(files["00-1-intro.txt"], "# 1 Intro.\n\nText.\n")

    def test_body_paragraph_cannot_become_a_heading_marker(self):
        proc, files = build(["1 Intro", "Text.", "# not a heading"], dict(CHAPTERS, paragraph_starts=["#"]))
        self.assertNotIn("\n# not", files["00-1-intro.txt"])


class LetterA(unittest.TestCase):
    """The voice reads a lone "A" as the article "uh"; found across every real document."""

    def text(self, line):
        proc, files = build(["1 Intro", line], CHAPTERS)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return body(files)

    def test_spelled_acronym(self):
        self.assertIn("the U V Eigh records", self.text("From the U V A records."))

    def test_spelled_award_code(self):
        self.assertIn("Z I Eigh L M 2", self.text("Grant Z I A L M 2 funds it."))

    def test_label_before_lowercase_word(self):
        self.assertIn("F and Eigh rate", self.text("Indirect costs use the F and A rate."))
        self.assertIn("enters, Eigh patient note", self.text("Harm enters, A patient note first."))

    def test_article_after_list_marker_untouched(self):
        self.assertIn("(1) A second reviewer", self.text("Two roles: (1) A second reviewer checks."))

    def test_label_before_punctuation_untouched(self):
        self.assertIn("cases A, B", self.text("This covers cases A, B and C."))

    def test_sentence_initial_article_untouched(self):
        self.assertIn("A model learns", self.text("Results hold. A model learns."))

    def test_hyphenated_spelling_untouched(self):
        self.assertIn("A-S-C-R office", self.text("The A-S-C-R office agreed."))


if __name__ == "__main__":
    unittest.main()
