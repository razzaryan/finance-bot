import pathlib

BAD = ("\u00f0\u0178", "\u00e2\u20ac", "\u00c3\u00a2", "\u00c2\u00b1", "\ufffd")
for p in sorted(pathlib.Path(".").rglob("*")):
    if not p.is_file() or any(x in {".venv", "__pycache__", ".git", ".pytest_cache", ".ruff_cache"} for x in p.parts):
        continue
    if p.suffix not in {".py", ".md", ".ps1", ".ini", ".txt", ".example", ""}:
        continue
    try:
        text = p.read_text(encoding="utf-8")
    except UnicodeDecodeError as e:
        print("NOT-UTF8", p, e)
        continue
    for marker in BAD:
        if marker in text:
            idx = text.index(marker)
            line = text.count("\n", 0, idx) + 1
            print(f"MOJIBAKE {p}:{line} {marker!r}")
            break
