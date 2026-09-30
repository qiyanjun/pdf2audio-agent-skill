# Writing the narration config

The goal is a script that a person would be happy to have read to them for an hour. Each rule
below exists because the unedited text fails that test in a specific way.

## Config fields

| Field | Type | Meaning |
|---|---|---|
| `title` | string | Used as the chapter title if text appears before any heading. |
| `drop_lines` | `[[first, last], ...]` | 1-based inclusive line ranges of `raw.txt` to delete. |
| `blank_line_is_paragraph_break` | bool, default `false` | See "Paragraphs" below. |
| `chapter_headings` | regex list | A line matching any of these starts a new chapter. |
| `chapter_names` | string list, optional | File name stems, one per chapter. Default: slug of the title. |
| `section_headings` | regex list | A matching line becomes a spoken sub-heading with a longer pause. |
| `heading_rewrites` | `[[pattern, replacement], ...]` | Applied to heading lines only, before `substitutions`. |
| `paragraph_starts` | string list | A line beginning with one of these starts a new paragraph. |
| `paragraph_start_patterns` | regex list | Same, as regexes. Added to the built-in rules (below), not replacing them. |
| `paragraph_breaks_before` | string list | Start a paragraph at this text even in the middle of a line. |
| `inserts` | list of objects | `{"after": anchor, "text": ...}` adds a paragraph after the paragraph containing `anchor`; `{"chapter_start": regex, "text": ...}` opens the chapter whose raw title matches. |
| `dehyphenate` | `{fused: fixed}` | Plain string fixes for words that lost a hyphen. |
| `pre_substitutions` | `[[pattern, replacement], ...]` | Regex rewrites that run *before* citation removal. |
| `keep_citations` | bool, default `false` | Keep bracketed numeric citations like `[12, 15]`. |
| `substitutions` | `[[pattern, replacement], ...]` | Regex rewrites, applied in order to all text. |
| `spell_digits_from` | int, default `0` (off) | Numbers with at least this many digits are read digit by digit. |

Patterns are Python regexes; in JSON every backslash is doubled (`"\\bPI\\b"`).

Order of operations on each paragraph: `dehyphenate`, `pre_substitutions`, citation removal,
bullet removal, `substitutions`, digit spelling, whitespace tidy. Inserted text goes through the
same steps. A paragraph that ends up empty is dropped silently, which is a handy way to remove a
line you only kept as an anchor.

Built-in paragraph rules: a bullet (`•`) always starts a paragraph. A line like `1. Text` starts
one only when the previous line ended a sentence or clause. Without that condition a wrapped
line such as "...as described in Section / 2. The model then..." would be split mid-sentence.

The raw text is Unicode-normalized (NFKC) before anything else, and so are the config strings.
This matters because PDFs from pandoc/xdvipdfmx write every semicolon as U+037E GREEK QUESTION
MARK. That character looks identical but the voice skips it, and it silently breaks any regex
containing `;`. Ligatures (`ﬁ`) and no-break spaces are folded too. You do not need a
substitution for any of these.

## What to drop

- **Page numbers and running headers/footers.** Usually a lone number surrounded by blank
  lines, often in the middle of a sentence that continues on the next page. They are *not*
  always surrounded by blanks: in some PDFs the number sits directly after a text line. Lint
  flags numbers that leaked into the script. Do not drop lone digits blindly, because table
  cells produce them too.
- **Figure and table bodies.** `pdftotext` emits their cells and labels as a column of
  fragments in no useful order. Drop the whole block *and its caption*, then describe the float
  with an insert. Pandoc output may repeat the label ("Figure 2: Figure 2").
- **The reference list.** Nobody wants ninety citations read aloud. A glossary or appendix may
  follow it; keep those if they help a listener, and consider telling the listener early on
  that a glossary comes at the end.
- **Title-page clutter** such as affiliations, emails, cover-page forms, and submission
  metadata, unless the user wants it. For drafts, say in your report which placeholders were
  in the dropped clutter, because the author will not hear them.
- **Tool output that is not the document**, such as a generator's preamble ("Generating the
  full application..."). An author's closing to-do list or self-review is part of their draft;
  keep it as its own last chapter, and mention it so they can skip it.

A drop range must not swallow the first or last line of real text next to it. After building,
find the sentence on each side of every dropped range in the script and confirm it reads
continuously.

## Headings

- **Multi-line headings.** A long heading can wrap onto a second raw line. Drop the second
  line, then restore the full text with a `heading_rewrites` entry on the first.
- **Section numbers on their own line** (some DOE/NIH templates). Drop the number line and put
  it back with `heading_rewrites` if you want it spoken.
- **Small caps split words**: "M EASURE", "L IMIT". Fix them with substitutions; lint does not
  catch them.
- **Numbered documents.** A heading regex like `^\d+\. [A-Z]` also matches run-in lists
  ("1. Conceptual:"). Prefer listing the actual section names:
  `^\d+\. (Specific Aims|Significance|Innovation)`.
- `heading_rewrites` can turn "2.3 Task 1.1: ..." into "Section 2.3. Task 1.1: ..." so the
  listener hears where they are.

## Paragraphs

LaTeX-style PDFs, from both pdfTeX and pandoc/xdvipdfmx, give one line per visual line with *no*
blank line between paragraphs. Blank lines appear only around floats and page breaks. For
these, leave `blank_line_is_paragraph_break` off. Mark paragraph boundaries with
`paragraph_starts`: run-in heads such as "Proposed." or "Why now.", and glossary terms. A run-in
head that begins mid-line ("...as noted above. Limitations. The...") needs
`paragraph_breaks_before`. Missing a boundary only costs a pause, so list the ones a listener
needs to hear as signposts and do not chase the rest.

Glossaries typeset as a term on its own line followed by the definition need a
`paragraph_start_patterns` entry such as `"^(Agent|Loop|Checkpoint)$"`. Add a substitution
that puts a period after the term (`"^(Agent|Loop|Checkpoint) " -> "\\1. "`) so the voice
pauses.

If the raw text does have a blank line between paragraphs and none in the middle of them
(common for Word-exported PDFs), turn the option on.

## Figures and tables

Write the insert the way you would describe the float to someone on the phone.

- A **figure**: one or two sentences saying what it shows; the caption is usually a good base.
  Open with "Figure 2 shows..." so in-text references still make sense.
- A **small table that carries content** (assumptions, a timeline, reviewer objections, a
  glossary): walk through it in the order a listener can hold. That is usually one row or one
  column at a time, in full sentences: "In Year 1, Thrust 1 delivers... In Year 2..."
  Reconstruct the cells from the scrambled raw text carefully. When the order is ambiguous,
  check the page itself (`pdftoppm -f N -l N -png -r 80 in.pdf page`, then Read the image).
- A **table that restates the prose** or is mostly numbers: say what it contains and how it is
  organized, and let the body text carry the detail. Do not read a grid of numbers.

Pick an anchor at a paragraph boundary near where the float is first referenced. Anchors match
the raw paragraph text within one paragraph. Several inserts on one anchor come out in config
order. A chapter that is nothing but a table has no paragraph to anchor to; use
`chapter_start` for it.

## Rewriting for the ear

Check every one of these against the lint output rather than trusting intuition; voices differ.
Lint phonemizes each token *in its sentence context*, which matters. "VLA" before a comma is
said "vlah" but spelled out elsewhere, and "PI," becomes "pie" while "the PI directs" is fine.
Use `lint_script.py --words "..."` to try a respelling before committing to it.

- **Citations**: `[12]` and `[3, 7]` are removed by default.
  - **Citations used as nouns** ("the score of [41]") would leave a hole. Rewrite them in
    `pre_substitutions` ("the score of reference 41").
  - **Author-year citations** need a substitution, for example
    `"\\s*\\((?:[A-Z][\\w-]+(?: et al\\.)?,? \\d{4}[a-z]?(?:; )?)+\\)" -> ""`. Keep the ones
    that are the grammatical subject ("Smith and Lee (2020) showed").
  - **Label-style citations** such as `(P3, P4)` or `(L41)`: try
    `"\\s*\\((?:[PLG]\\d+(?:\\.[A-Z]\\d+)?(?:,\\s*)?)+\\)" -> ""`. Keep labels that are the
    subject of a sentence.
- **Acronyms**: all-caps tokens are mostly spelled out correctly, but check each one in
  context. Write letters apart to force spelling (`HHH` -> `H H H`), or write a respelling to
  force a word (`OLMo` -> `Olmo`, `MuJoCo` -> `Moo-Joe-Co`).
  - **Plural acronyms** can lose their plural: "LLMs" comes out as "LLM". `L L M's` works.
- **The letter A is the big trap.** Standing alone before a word, it is read as the article
  "uh". This happens even inside a hyphenated spelling ("U-V-A" gives "U V uh").
  - **Spaced-out acronyms** ("U V A records", "Z I A L M 2") are fixed automatically: the
    builder writes each A in a letter run as "Eigh", which is read "ay" in every context
    tested. So spelling an acronym out with spaces is safe.
  - **A capital "A" mid-sentence before a lowercase word** ("F and A rate", "enters, A patient
    note", "case A is") is also written "Eigh" automatically. The article would be lowercase
    there. The rule skips an "A" right after ")" or a digit ("(1) A second reviewer"), which
    really is an article.
  - **An "A" before punctuation** ("cases A, B", "(case A).") is read correctly as is. Lint
    lists every remaining mid-sentence "A" with its phonemes. Where one is still wrong, put the
    letter in quotes (`case “A”`) or write `Eigh`.
- **Names the voice will not know** (models, tools, people): respell phonetically, and check
  the respelling with `--words`. For example, "Qi" is read "kai" unless respelled "Chee".
- **Numbers**: decimals, percentages, and "Task 1.1" read fine. Long identifiers such as award
  numbers should be read digit by digit (`spell_digits_from`, or a substitution for mixed ones
  like `R01` -> "R oh 1"). Rewrite date ranges, currency, and `N =1024`-style math into words.
- **Symbols**: `pre/post` -> "pre and post", `->` -> "to", `+` -> "plus" or "and", `§ 4` ->
  "section 4", `κ ≥ 0.6` -> "kappa of at least 0.6", `e.g.,` -> "for example,". Primes and
  subscripts (`c0` from a typeset c-prime) -> "c-prime". Lint flags every character outside
  plain letters, digits and ordinary punctuation.
- **Lost hyphens**: `pdftotext` rejoins words split at a line end and drops the hyphen even
  when it was real ("openweight", "tamperresistant"). Pandoc can fuse words without any line
  break ("researchsecurity", "onehot"). Lint lists words that split cleanly into two dictionary
  words; fix them in `dehyphenate`. It cannot see two related problems:
  - **Number ranges**: "2-3 models" can come out as "23 models". Search the raw text for
    suspicious numbers near line ends, and compare them with the PDF.
  - **Page-end hyphens** are joined with a space ("DNA- binding").
- **Editorial marks in drafts** such as `[PLACEHOLDER: ...]` or `[TODO ...]`: keep them, spoken
  as "(placeholder: ...)". The author listening to their own draft wants to hear what is still
  open. For a finished document there will be none.
- **Internal labels** the document never defines (gap labels "G1 to G7", traceability tags
  "P16.C1") mean nothing when heard. Remove them, and say so in your report.
- **Cross-references to things that are gone** ("see the Appendix", "(Figure 1)"): leave short
  ones; rewrite the ones that no longer make sense.

## What not to change

Do not shorten, reorder, or "improve" the author's sentences. Do not skip sections because they
seem boring. The script is saved next to the audio precisely so the user can verify that what
they heard is what they wrote. If the PDF itself looks wrong (a garbled formula, a broken
superscript), narrate your best reading and tell the user so they can fix the source.
