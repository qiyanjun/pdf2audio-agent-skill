#!/usr/bin/env python3
"""Find things in a narration script that a voice will stumble on.

    lint_script.py script_dir [--lang en-us] [--words "Nersk, Sigh-Dack, the A-S-C-R office"]

Reports:
  1. characters outside what a voice reads cleanly (symbols, non-Latin letters, look-alikes);
  2. stray numbers that look like leaked page numbers;
  3. words that look like two words fused where a hyphen was lost;
  4. acronyms, respellings, spaced letters and a mid-sentence letter "A", each phonemized inside
     its own sentence context - the voice says "UVA" differently alone and before a comma.
--words phonemizes any strings you pass, to test a respelling before putting it in the config.
Phonemes need the TTS interpreter (~/.cache/pdf2audio/venv/bin/python); with plain python3
section 4 lists tokens only.
"""
import argparse
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

SPEAKABLE_PUNCT = set(" \n.,;:!?'\"()-–—‘’“”%")
DICT = Path("/usr/share/dict/words")
SUFFIXES = [("", ""), ("s", ""), ("es", ""), ("ed", ""), ("d", ""), ("ing", ""), ("ing", "e"), ("ed", "e"),
            ("ies", "y"), ("ied", "y"), ("ly", ""), ("er", ""), ("ers", ""), ("al", ""), ("ness", ""),
            ("ment", ""), ("ments", ""), ("ation", "e"), ("ations", "e"), ("ize", ""), ("izes", "ize"),
            ("ized", "ize"), ("izing", "ize"), ("able", "")]
# Tokens whose pronunciation is worth seeing: 2+ capitals (UVA, NIH, dbGaP), letters mixed with
# digits (R01, h5ad), hyphenated respellings (Sigh-Dack), spaced letter runs (U V A).
WATCH = re.compile(r"\b(?:[A-Za-z]*[A-Z][a-z]*[A-Z][A-Za-z]*|[A-Za-z]+\d[\w]*|\d+[A-Za-z]+\w*"
                   r"|[A-Z][a-z]*(?:-[A-Z][a-z]*)+|(?:[A-Z] ){1,}[A-Z](?:’s|'s|s)?)\b")
MID_SENTENCE_A = re.compile(r"(?<=[a-z,;(] )A\b(?! (?:[a-z]+ )?(?:is|was|has|can|will|would|should|must)\b)")


def known(word, vocab):
    for suf, rep in SUFFIXES:
        if word.endswith(suf):
            stem = word[: len(word) - len(suf)]
            if stem + rep in vocab or (len(stem) > 3 and stem[-1] == stem[-2] and stem[:-1] in vocab):
                return True
    return False


def fused(word, vocab):
    """word is unknown but splits into two known words of 3+ letters: likely a lost hyphen."""
    if known(word, vocab):
        return None
    for i in range(3, len(word) - 2):
        if word[:i] in vocab and known(word[i:], vocab):
            return f"{word[:i]}-{word[i:]}"
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("script_dir")
    ap.add_argument("--lang", default="en-us")
    ap.add_argument("--words", help="comma-separated strings to phonemize")
    args = ap.parse_args()

    phonemize = None
    try:
        import tts_common
        voice = tts_common.load()
        phonemize = lambda s: voice.tokenizer.phonemize(s, args.lang)
    except (ImportError, SystemExit):
        pass

    if args.words:
        print("== Requested words ==")
        for w in (w.strip() for w in args.words.split(",")):
            print(f"  {w:<30} {phonemize(w) if phonemize else '(needs the TTS interpreter)'}")
        print()

    files = sorted(Path(args.script_dir).glob("*.txt"))
    texts = {f.name: re.sub(r"(?m)^#+ ", "", f.read_text()) for f in files}

    print("== Characters a voice may skip or misread ==")
    bad = defaultdict(list)
    for name, text in texts.items():
        for i, ch in enumerate(text):
            latin = ch.isalpha() and unicodedata.name(ch, "").startswith("LATIN")
            if not (ch.isdigit() or latin or ch in SPEAKABLE_PUNCT):
                bad[ch].append((name, text[max(0, i - 30): i + 20].replace("\n", " ")))
    for ch, hits in sorted(bad.items(), key=lambda kv: -len(kv[1])):
        print(f"  {ch!r} U+{ord(ch):04X} {unicodedata.name(ch, '?')} x{len(hits)}, e.g. {hits[0][0]}: ...{hits[0][1]}...")
    print("  none" if not bad else "")

    print("== Stray numbers (leaked page numbers?) ==")
    stray = 0
    for name, text in texts.items():
        for m in re.finditer(r"(?:[a-z,] \d{1,3}$|[.?!] \d{1,3} [A-Z])", text, re.M):
            print(f"  {name}: ...{text[max(0, m.start() - 40): m.end() + 10].strip()}...")
            stray += 1
    print("  none\n" if not stray else "")

    print("== Words that look fused (lost hyphen?) ==")
    if DICT.exists():
        vocab = {w.lower() for w in DICT.read_text().split()}
        everything = "\n".join(texts.values()).lower()
        words = {w.lower() for t in texts.values() for w in re.findall(r"\b[A-Za-z]{6,}\b", t)}
        found = sorted(filter(None, (fused(w, vocab) for w in words)))
        # The old system dictionary lacks many real compounds (checkpoint, baseline), so rank by
        # evidence: the document also writing the pair apart or hyphenated is a strong signal.
        likely = [f for f in found if f in everything or f.replace("-", " ") in everything]
        possible = [f for f in found if f not in likely]
        print("  likely:   " + (", ".join(likely) or "none"))
        print("  possible: " + (", ".join(possible) or "none")
              + "\n  (possible = splits into two words; most are real compounds, skim for surprises)\n")
    else:
        print("  skipped: no /usr/share/dict/words\n")

    print("== How acronyms and respellings will be spoken, in context ==")
    contexts = defaultdict(list)
    for text in texts.values():
        for rx, label in ((WATCH, None), (MID_SENTENCE_A, "A (mid-sentence)")):
            for m in rx.finditer(text):
                before = re.findall(r"\S+\s*$", text[: m.start()])
                after = re.match(r"[^\s\w]*\s*\S*", text[m.end():]).group(0)
                window = ((before[0] if before else "") + m.group(0) + after).strip()
                contexts[label or m.group(0)].append(window)
    if not phonemize:
        print("  (run with the TTS interpreter to see phonemes)")
    for tok, windows in sorted(contexts.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        if not phonemize:
            print(f"  {tok} x{len(windows)}")
            continue
        seen = {}
        for w in windows:
            seen.setdefault(phonemize(w), w)
        print(f"  {tok} x{len(windows)}")
        for ph, w in list(seen.items())[:3]:
            print(f"      {w!r:<40} {ph}")
    if not contexts:
        print("  none")


if __name__ == "__main__":
    main()
