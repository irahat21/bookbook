"""MOCK language model (LLM_MODE=mock). No neural network: simple, deterministic text tricks.

Why it exists: Ollama is not installed on the demo machine (ASSUMPTIONS M-08), but the
chatbot (UC-12/13) and the Reading Companion (UC-14) must still be demonstrable. So the
mock does the two jobs an LLM does in the SRS, in the simplest honest way:

* embed(text)  - a "hashed bag of words": every content word is hashed to one of 2048
  positions and counted. Texts that share words point in similar directions, so cosine
  similarity really finds the relevant chunks (SRS 4.21 retrieve). It knows nothing about
  meaning: "car" and "automobile" are unrelated to it.
* answer / summarize / explain / define / quiz - extractive: the mock never invents text.
  It picks and arranges sentences from the facts or book excerpts it was given.

Everything it produces is labelled MOCK in the UI.
"""
import hashlib
import json
import random
import re
from collections import Counter

import numpy as np

EMBED_DIM = 2048
EMBED_MODEL_ID = f"mock-hashed-bow-{EMBED_DIM}"   # stored with every vector (re-index on change)

STOPWORDS = set("""
a about above after again against all also am an and any are as at be because been before being
below between both but by can could did do does doing down during each few for from further had
has have having he her here hers herself him himself his how i if in into is it its itself just
me more most my myself no nor not now of off on once only or other our ours ourselves out over own
same she should so some such than that the their theirs them themselves then there these they
this those through to too under until up very was we were what when where which while who whom
why will with would you your yours yourself yourselves said says say one two three get got let book
like make made many much may might must shall still upon well went yes back every never always
""".split())

_WORD = re.compile(r"[a-z0-9]+(?:'[a-z]+)?")


def tokens(text: str) -> list[str]:
    """Lower-case content words with a very light plural strip ("maps" -> "map")."""
    out = []
    for w in _WORD.findall(text.lower()):
        w = w.split("'")[0]                     # "dragon's" -> "dragon"
        if len(w) < 2 or w in STOPWORDS:
            continue
        if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
            w = w[:-1]
        out.append(w)
    return out


def sentences(text: str) -> list[str]:
    """Split prose on . ! ? and poems on line breaks; drop very short fragments."""
    parts = []
    for block in re.split(r"\n\s*\n", text):
        lines = block.strip().split("\n")
        if len(lines) > 2 and all(len(l) < 60 for l in lines):     # a stanza: keep lines whole
            parts.extend(l.strip() for l in lines)
        else:
            parts.extend(re.split(r"(?<=[.!?])\s+", " ".join(l.strip() for l in lines)))
    return [p.strip() for p in parts if len(p.split()) >= 4]


def _slot(word: str) -> tuple[int, float]:
    h = int.from_bytes(hashlib.md5(word.encode()).digest()[:4], "big")
    return h % EMBED_DIM, (1.0 if h & 0x80000000 else -1.0)    # signed hashing reduces collisions


def embed(text: str) -> np.ndarray:
    """Hashed bag-of-words unit vector. Term counts are damped (1 + log n) so one
    repeated word does not dominate a 250-word chunk."""
    v = np.zeros(EMBED_DIM)
    for word, n in Counter(tokens(text)).items():
        i, sign = _slot(word)
        v[i] += sign * (1.0 + np.log(n))
    norm = np.linalg.norm(v)
    if norm == 0:                               # no content words: a fixed, harmless vector
        v[0] = 1.0
        return v
    return v / norm


def unique_sentences(texts: list[str], keep_short: bool = False) -> list[str]:
    """Sentences of several chunks, in order, without repeats. Chunks overlap by 40 words
    (SRS 4.21), so a sentence cut at a chunk border appears once whole and once as a
    fragment ("... Brandt could"); a fragment contained in a longer sentence is dropped.
    keep_short: keep a text with no full sentence (e.g. "Balance: $50.00") as one item."""
    pool = list(dict.fromkeys(s for t in texts for s in (sentences(t) or ([t.strip()] if keep_short else []))))
    return [s for s in pool if not any(s != other and s in other for other in pool)]


def _overlap(a: set, sentence: str) -> int:
    return len(a & set(tokens(sentence)))


def _best_sentences(query: str, texts: list[str], k: int) -> list[str]:
    """The k sentences sharing the most words with the query, best first. Ties go to the
    shorter, more precise sentence, so "Your balance: $50.00" beats a long policy
    paragraph that merely mentions balances."""
    q = set(tokens(query))
    pool = unique_sentences(texts, keep_short=True)
    scored = []
    for i, s in enumerate(pool):
        overlap = _overlap(q, s)
        if overlap:
            scored.append((-overlap, -overlap / max(1, len(tokens(s))), i, s))
    return [s for *_rank, s in sorted(scored)[:k]]


# ---------------------------------------------------------------- tasks
def answer(question: str, facts: list[str]) -> str:
    """Chatbot / companion "ask": quote the best-matching sentences of the facts."""
    if not facts:
        return ("I'm running without a language model (MOCK mode), so I can't answer general "
                "questions. Ask me about the store, or start Ollama and set LLM_MODE=real.")
    best = _best_sentences(question, facts, 2)
    if not best:                                # facts were retrieved but share no words
        best = sentences(facts[0])[:2] or [facts[0]]
    return " ".join(best)


def classify(_question: str, store_context: list[str]) -> str:
    """The STORE/GENERAL fallback classifier (SRS 4.20). The mock cannot judge meaning, so
    it uses retrieval as a proxy: if the question matches some store chunk (policy or
    catalog) it is a STORE question, otherwise GENERAL (ASSUMPTIONS A-27)."""
    return "STORE" if store_context else "GENERAL"


def summarize(chunks: list[str], points: int = 5) -> str:
    """Frequency summary: the sentences whose words are most common in the chapter."""
    pool = unique_sentences(chunks)
    freq = Counter(w for s in pool for w in tokens(s))
    scored = sorted(((sum(freq[w] for w in set(tokens(s))) / (len(tokens(s)) + 3) ** 0.5, i, s)
                     for i, s in enumerate(pool)), key=lambda x: (-x[0], x[1]))[:points]
    return "\n".join("• " + s for _sc, _i, s in sorted(scored, key=lambda x: x[1]))


def explain(selection: str, chunks: list[str]) -> str:
    keywords = [w for w, _n in Counter(tokens(selection)).most_common(4)]
    pool = unique_sentences(chunks)
    sel = " ".join(selection.split())
    hit = next((i for i, s in enumerate(pool) if s in sel or sel[:40] in s), None)
    if hit is not None:                         # the sentences just before and after the selection
        context = [pool[i] for i in (hit - 1, hit + 1) if 0 <= i < len(pool) and pool[i] not in sel]
    else:
        context = [s for s in _best_sentences(selection, chunks, 4) if s not in sel][:2]
    text = f"This passage is mainly about: {', '.join(keywords) or 'a short moment in the text'}."
    if context:
        text += "\nNearby in the book: " + " ".join(context)
    return text + "\n(MOCK: a real language model would rephrase the passage in plain English.)"


def define(word: str, chunks: list[str]) -> str:
    w = word.strip().lower()
    uses = [s for s in unique_sentences(chunks) if re.search(rf"\b{re.escape(w)}", s.lower())]
    if not uses:
        return f"'{word}' does not appear in this chapter's excerpts."
    return (f"'{word}' is used here: \"{uses[0]}\"\n(MOCK: no dictionary meaning without a "
            "language model; the sentence shows how the word is used.)")


def quiz(chunks: list[str], count: int = 3) -> str:
    """Fill-in-the-blank multiple-choice questions, as the JSON the SRS asks the LLM for:
    [{"q": ..., "options": [4 strings], "answer_index": 0-3}]."""
    pool = [s for s in unique_sentences(chunks) if 8 <= len(s.split()) <= 35]
    words = sorted({w for s in pool for w in re.findall(r"[A-Za-z]{5,}", s)
                    if w.lower() not in STOPWORDS}, key=str.lower)
    out, used = [], set()
    # spread the questions over the chapter: try evenly spaced sentences first
    spaced = [int(j * len(pool) / count) for j in range(count)] + list(range(len(pool)))
    for s in (pool[i] for i in dict.fromkeys(spaced) if i < len(pool)):
        cands = [w for w in re.findall(r"[A-Za-z]{5,}", s) if w.lower() not in STOPWORDS and w not in used]
        if not cands:
            continue
        target = max(cands, key=len)            # the longest word is usually the most specific
        rng = random.Random(hashlib.md5(s.encode()).hexdigest())
        distractors = [w for w in words if w.lower() != target.lower() and w not in s]
        same_case = [w for w in distractors if w[0].isupper() == target[0].isupper()]
        if len(same_case) >= 3:                 # "Saturday" among lower-case words is a giveaway
            distractors = same_case
        if len(distractors) < 3:
            continue
        options = rng.sample(distractors, 3) + [target]
        rng.shuffle(options)
        used.add(target)
        out.append({"q": "Fill in the blank: " + re.sub(rf"\b{target}\b", "_____", s, count=1),
                    "options": options, "answer_index": options.index(target)})
        if len(out) == count:
            break
    return json.dumps(out)
