#!/usr/bin/env python3
"""Turn a pdftotext dump into a narration script, one text file per chapter.

    build_script.py raw.txt narration.json out_dir

The config (see references/narration-guide.md) says which lines to drop, where chapters and
paragraphs start, what prose stands in for figures and tables, and how to respell things for
the ear. In each output file the first line is "# Chapter title", sub-headings are
"## Heading" paragraphs, and paragraphs are separated by a blank line.
"""
import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

BULLET_LINE = re.compile(r"^[•◦▪‣]")
# "1. Text" starts a list item only when the previous line ended a sentence or clause; otherwise
# it is a wrapped line such as "...as described in Section / 2. The model then...".
NUMBERED_LINE = re.compile(r"^\d{1,2}\. [A-Z]")
CLAUSE_END = re.compile(r"[.:;?!)”\"]$")
CITATION = re.compile(r"\s*\[\d+(?:\s*[,–-]\s*\d+)*\]")
BULLET = re.compile(r"^[•◦▪‣]\s*")
# Spelled-out letters ("U V A", "Z I A L M 2"): the voice reads a lone "A" as the article "uh",
# even hyphenated ("U-V-A"). "Eigh" is read "ay" in every context tested.
LETTER_RUN = re.compile(r"(?<![\w’'-])(?:[A-Z] )+[A-Z](?![\w-])")
# A capital "A" mid-sentence before a lowercase word is a label ("F and A rate", "enters, A
# patient note"), never the article, which would be lowercase there - but it is read "uh".
# Not after ")" or a digit: "(1) A second reviewer" is an article after a list marker.
LABEL_A = re.compile(r"(?<=[a-z,;] )A(?= [a-z])")


def nfkc(s):
    return unicodedata.normalize("NFKC", s)


def slug(text, limit=40):
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:limit].rstrip("-") or "chapter"


def compile_pairs(pairs):
    return [(re.compile(nfkc(p)), nfkc(r)) for p, r in pairs]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("raw")
    ap.add_argument("config")
    ap.add_argument("out_dir")
    args = ap.parse_args()

    cfg = json.loads(Path(args.config).read_text())
    raw = Path(args.raw).read_text().split("\n")

    drop = {i for a, b in cfg.get("drop_lines", []) for i in range(a, b + 1)}
    blank_breaks = cfg.get("blank_line_is_paragraph_break", False)
    # NFKC folds look-alikes the voice would skip or misread: xdvipdfmx PDFs emit every ";" as
    # U+037E GREEK QUESTION MARK, ligatures such as "ﬁ" become plain letters, and no-break spaces
    # become spaces. Config strings are normalized the same way so they keep matching.
    lines = [nfkc(l).strip() for i, l in enumerate(raw, 1) if i not in drop]
    if not blank_breaks:
        lines = [l for l in lines if l]

    chapter_re = [re.compile(nfkc(p)) for p in cfg.get("chapter_headings", [])]
    section_re = [re.compile(nfkc(p)) for p in cfg.get("section_headings", [])]
    start_re = [re.compile(nfkc(p)) for p in cfg.get("paragraph_start_patterns", [])]
    starts = tuple(nfkc(s) for s in cfg.get("paragraph_starts", []))
    breaks_before = [nfkc(s) for s in cfg.get("paragraph_breaks_before", [])]
    heading_rewrites = compile_pairs(cfg.get("heading_rewrites", []))
    pre_subs = compile_pairs(cfg.get("pre_substitutions", []))
    subs = compile_pairs(cfg.get("substitutions", []))
    dehyph = {nfkc(a): nfkc(b) for a, b in cfg.get("dehyphenate", {}).items()}
    digits_from = cfg.get("spell_digits_from", 0)

    def clean(t):
        for a, b in dehyph.items():
            t = t.replace(a, b)
        for pat, rep in pre_subs:
            t = pat.sub(rep, t)
        if not cfg.get("keep_citations", False):
            t = CITATION.sub("", t)
        t = BULLET.sub("", t)
        for pat, rep in subs:
            t = pat.sub(rep, t)
        if digits_from:
            t = re.sub(rf"\b\d{{{digits_from},}}\b", lambda m: " ".join(m.group(0)), t)
        t = LETTER_RUN.sub(lambda m: re.sub(r"\bA\b", "Eigh", m.group(0)), t)
        t = LABEL_A.sub("Eigh", t)
        t = re.sub(r"\s+([,.;:)])", r"\1", t)
        t = re.sub(r"\(\s+", "(", t)
        t = re.sub(r"\s{2,}", " ", t).strip()
        return t.lstrip("#").strip()  # a leading "#" would read as a heading marker downstream

    def heading(t):
        for pat, rep in heading_rewrites:
            t = pat.sub(rep, t)
        t = clean(t)
        return t if t[-1] in ".?!" else t + "."

    # chapters: [raw title, [raw paragraphs]]; section headings are kept as "## ..." paragraphs.
    chapters, para = [], []

    def flush():
        if para:
            if not chapters:
                chapters.append([cfg.get("title", "Document"), []])
            text = " ".join(para)
            for b in breaks_before:  # run-in heads that begin mid-line
                text = text.replace(" " + b, "\n\n" + b)
            chapters[-1][1].extend(text.split("\n\n"))
            para.clear()

    prev = ""
    for l in lines:
        if not l:
            flush()
        elif any(r.search(l) for r in chapter_re):
            flush()
            chapters.append([l, []])
        elif any(r.search(l) for r in section_re):
            flush()
            if not chapters:
                chapters.append([cfg.get("title", "Document"), []])
            chapters[-1][1].append("## " + l)
        else:
            if (l.startswith(starts) or BULLET_LINE.search(l) or any(r.search(l) for r in start_re)
                    or (NUMBERED_LINE.search(l) and (not prev or CLAUSE_END.search(prev)))):
                flush()
            para.append(l)
        prev = l
    flush()
    if not chapters:
        sys.exit("No text left after dropping lines.")

    # Inserts: {"after": anchor, "text"} goes after the first paragraph containing the anchor
    # (raw text); several inserts on one anchor keep their config order. {"chapter_start": regex,
    # "text"} opens the chapter whose raw title matches - for chapters that are only a table.
    pending, unmatched = [], []
    for x in cfg.get("inserts", []):
        if "chapter_start" in x:
            hits = [c for c in chapters if re.search(nfkc(x["chapter_start"]), c[0])]
            if hits:
                hits[0][1].insert(sum(1 for p in hits[0][1] if p.startswith("\0start")), "\0start" + x["text"])
            else:
                unmatched.append("chapter_start " + x["chapter_start"])
        else:
            pending.append(dict(x, after=nfkc(x["after"])))
    for _, paras in chapters:
        i = 0
        while i < len(paras):
            hits = [x for x in pending if x["after"] in paras[i]]
            for k, ins in enumerate(hits, 1):
                pending.remove(ins)
                paras.insert(i + k, ins["text"])
            i += 1
        paras[:] = [p.removeprefix("\0start") for p in paras]
    unmatched += ["after " + x["after"] for x in pending]
    if unmatched:
        sys.exit("Insert anchor not found:\n  " + "\n  ".join(unmatched))

    names = cfg.get("chapter_names") or [slug(t) for t, _ in chapters]
    if len(names) != len(chapters):
        sys.exit(f"chapter_names has {len(names)} entries but {len(chapters)} chapters were found: "
                 + "; ".join(t for t, _ in chapters))

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    wanted = {f"{i:02d}-{n}.txt" for i, n in enumerate(names)}
    for old in out.glob("*.txt"):  # a chapter that no longer exists must not be narrated
        if old.name not in wanted:
            old.unlink()

    total = 0
    for i, (name, (title, paras)) in enumerate(zip(names, chapters)):
        body = ["## " + heading(p[3:]) if p.startswith("## ") else clean(p) for p in paras]
        body = [b for b in body if b]  # a paragraph a substitution emptied is dropped silently
        text = "\n\n".join(["# " + heading(title)] + body) + "\n"
        path = out / f"{i:02d}-{name}.txt"
        if not path.exists() or path.read_text() != text:  # keep mtime so synth.py can skip it
            path.write_text(text)
        words = len(text.split())
        total += words
        print(f"{path.name}: {len(body)} paragraphs, {words} words, ~{words / 150:.0f} min")
    print(f"Total: {total} words, ~{total / 150:.0f} min of audio")


if __name__ == "__main__":
    main()
