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


# Legacy encodings a job description file may come in when it is not UTF-8: Windows Turkish,
# Mac Roman (what macOS `pbpaste` writes when no UTF-8 locale is set) and Mac Turkish.
LEGACY_ENCODINGS = ("cp1254", "mac_roman", "mac_turkish")
PLAUSIBLE = set("çğıöşüÇĞİÖŞÜâîûÂÎÛéèàäëïÉÈÀÄ’‘“”–—•…€")


def decode_text(data: bytes) -> str:
    """Decode a text file: UTF-8 (with or without BOM), UTF-16 with BOM, or else the legacy
    encoding whose non-ASCII characters look most like real text."""
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        pass

    def plausibility(text: str) -> int:
        return sum(1 if c in PLAUSIBLE else -1 for c in text if ord(c) > 127)

    return max((data.decode(e, errors="replace") for e in LEGACY_ENCODINGS), key=plausibility)


def tokens(text: str) -> list[str]:
    """Words as matching keys (see fold), in order."""
    return fold(text).split()


def original_words(text: str) -> dict[str, str]:
    """Matching key -> the word as written, for showing examples to the user."""
    return {fold(word): word for word in reversed(WORD.findall(text))}
