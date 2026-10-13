"""Text helpers shared by checks and matching."""

import re
import unicodedata

BULLETS = "•●▪■◦►–-*"
WORD = re.compile(r"\w+")
# Dotted and dotless i are folded together so that "EXPERIENCE", "Experience", "DENEYİM" and
# "deneyim" all compare equal regardless of the language the text was lowercased in.
_FOLD = str.maketrans({"ı": "i", "İ": "i", "I": "i", "ğ": "g", "ş": "s", "ç": "c", "ö": "o", "ü": "u"})


def fold(text: str) -> str:
    """Matching key: lowercase, Turkish letters folded to ASCII, accents and punctuation removed."""
    text = unicodedata.normalize("NFKC", text).translate(_FOLD).lower().translate(_FOLD)
    text = "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))
    return " ".join(WORD.findall(text))


def tokens(text: str) -> list[str]:
    """Words as matching keys (see fold), in order."""
    return fold(text).split()


def original_words(text: str) -> dict[str, str]:
    """Matching key -> the word as written, for showing examples to the user."""
    return {fold(word): word for word in reversed(WORD.findall(text))}
