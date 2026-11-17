#!/usr/bin/env python3
"""Find or strip code comments in the files git tracks under a directory.

`python3 scripts/comments.py` lists every comment in this checkout as path:line and exits 1 when it finds one.
`python3 scripts/comments.py --fix [DIR]` deletes them in place. A comment that a tool reads to run stays: a
shebang, a Python encoding line, and lint or type directives such as `# noqa`, `# type:`, `// @ts-expect-error`,
and `// eslint-disable`. Docstrings and Markdown are not comments. scripts/sync_upstream.py strips the upstream
tree with strip_tree before it lands in vendor/pstack.
"""

import argparse
import io
import re
import subprocess
import sys
import tokenize
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]

PY_DIRECTIVE = re.compile(r"#\s*(?:type:|noqa\b|pragma\b|pyright:|mypy:|pylint:|fmt:|isort:|ruff:)")
PY_ENCODING = re.compile(r"^#.*?coding[:=]")
C_DIRECTIVE = re.compile(r"^(?://|/\*)\s*(?:@ts-|eslint-|/\s*<reference|biome-ignore|prettier-ignore|c8 |istanbul |@jsx)")
MMD_DIRECTIVE = re.compile(r"^%%\{.*\}%%\s*$")
NEWLINE = "\n"
REGEX_KEYWORDS = {"return", "typeof", "case", "in", "of", "delete", "void", "throw", "new", "else", "do", "yield", "await", "instanceof"}


def _lines(text):
    return re.findall(r"[^\n]*\n|[^\n]+$", text)


def _python(text):
    spans = []
    lines = _lines(text)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    for token in tokenize.generate_tokens(io.StringIO(text).readline):
        if token.type != tokenize.COMMENT:
            continue
        row, col = token.start
        body = token.string
        if PY_DIRECTIVE.match(body) or (row <= 2 and (PY_ENCODING.match(body) or (row == 1 and col == 0 and body.startswith("#!")))):
            continue
        start = offsets[row - 1] + col
        spans.append((start, start + len(body)))
    return spans


def _c_like(text, regex=True, hash_lines=False):
    spans = []
    i = 0
    n = len(text)
    if text.startswith("#!"):
        i = text.find("\n") if "\n" in text else n
    braces = []
    last = ""
    while i < n:
        c = text[i]
        if hash_lines and c == "#" and (i == 0 or text[i - 1] == "\n"):
            end = text.find("\n", i)
            end = n if end < 0 else end
            spans.append((i, end))
            i = end
            continue
        if c == "/" and text.startswith("//", i):
            end = text.find("\n", i)
            end = n if end < 0 else end
            if not C_DIRECTIVE.match(text[i:end]):
                spans.append((i, end))
            i = end
            continue
        if c == "/" and text.startswith("/*", i):
            end = text.find("*/", i + 2)
            end = n if end < 0 else end + 2
            if not C_DIRECTIVE.match(text[i:end]):
                spans.append((i, end))
            i = end
            continue
        if c in "\"'":
            i = _skip_string(text, i + 1, c)
            last = "a"
            continue
        if c == "`" and regex:
            i = _skip_template(text, i + 1, braces)
            last = "a"
            continue
        if c == "}" and braces and braces[-1] == "${":
            braces.pop()
            i = _skip_template(text, i + 1, braces)
            last = "a"
            continue
        if c == "{" and regex:
            braces.append("{")
        elif c == "}" and braces:
            braces.pop()
        if c == "/" and regex and _regex_allowed(text, i, last):
            i = _skip_regex(text, i + 1)
            last = "a"
            continue
        if c.isalnum() or c in "_$":
            j = i
            while j < n and (text[j].isalnum() or text[j] in "_$"):
                j += 1
            word = text[i:j]
            last = "kw" if word in REGEX_KEYWORDS else "a"
            i = j
            continue
        if not c.isspace():
            last = c
        i += 1
    return spans


def _regex_allowed(text, i, last):
    return last == "kw" or last in "(,=:[!&|?{};+-*%<>~^"


def _skip_string(text, i, quote):
    n = len(text)
    while i < n:
        if text[i] == "\\":
            i += 2
            continue
        if text[i] == quote:
            return i + 1
        i += 1
    return n


def _skip_template(text, i, braces):
    n = len(text)
    while i < n:
        if text[i] == "\\":
            i += 2
            continue
        if text[i] == "`":
            return i + 1
        if text.startswith("${", i):
            braces.append("${")
            return i + 2
        i += 1
    return n


def _skip_regex(text, i):
    n = len(text)
    in_class = False
    while i < n and text[i] != "\n":
        if text[i] == "\\":
            i += 2
            continue
        if text[i] == "[":
            in_class = True
        elif text[i] == "]":
            in_class = False
        elif text[i] == "/" and not in_class:
            return i + 1
        i += 1
    return i


def _shell(text, line_offset=0):
    spans = []
    lines = _lines(text)
    position = 0
    heredoc = None
    quote = None
    for number, line in enumerate(lines, start=1):
        start = position
        position += len(line)
        if heredoc:
            if line.strip("\r\n").lstrip("\t") == heredoc:
                heredoc = None
            continue
        if number == 1 and line_offset == 0 and line.startswith("#!"):
            continue
        i = 0
        n = len(line)
        while i < n:
            c = line[i]
            if quote:
                if c == "\\" and quote == '"':
                    i += 2
                    continue
                if c == quote:
                    quote = None
                i += 1
                continue
            if c == "\\":
                i += 2
                continue
            if c in "'\"":
                quote = c
                i += 1
                continue
            if c == "#" and (i == 0 or line[i - 1] in " \t;&|()"):
                spans.append((start + i, start + len(line.rstrip("\r\n"))))
                break
            if line.startswith("<<", i) and not line.startswith("<<<", i):
                match = re.match(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1", line[i:])
                if match:
                    heredoc = match.group(2)
                    i += match.end()
                    continue
            i += 1
    return spans


def _yaml(text):
    spans = []
    lines = _lines(text)
    position = 0
    block = None
    run_block = None
    for line in lines:
        start = position
        position += len(line)
        content = line.rstrip("\r\n")
        indent = len(content) - len(content.lstrip(" "))
        if block is not None:
            if not content.strip() or indent > block:
                if run_block is not None:
                    run_block.append((start, line))
                continue
            if run_block:
                spans += _shell_block(run_block)
            block = None
            run_block = None
        quote = None
        for i, c in enumerate(content):
            if quote:
                if c == quote:
                    quote = None
                continue
            if c in "'\"" and (i == 0 or content[i - 1] in " :[{,-"):
                quote = c
            elif c == "#" and (i == 0 or content[i - 1] in " \t"):
                spans.append((start + i, start + len(content)))
                content = content[:i]
                break
        if re.search(r"(?:^|[\s:-])[|>][-+0-9]*\s*$", content):
            block = indent
            run_block = [] if re.match(r"\s*(?:-\s+)?run:\s*[|>]", content) else None
    if run_block:
        spans += _shell_block(run_block)
    return spans


def _shell_block(lines):
    text = "".join(line for _, line in lines)
    spans = []
    for begin, end in _shell(text, line_offset=1):
        base = 0
        for start, line in lines:
            if base <= begin < base + len(line):
                spans.append((start + begin - base, start + end - base))
                break
            base += len(line)
    return spans


def _line_hash(text):
    spans = []
    position = 0
    for line in _lines(text):
        if line.lstrip(" \t").startswith("#"):
            spans.append((position, position + len(line.rstrip("\r\n"))))
        position += len(line)
    return spans


def _tla(text):
    spans = []
    i = 0
    n = len(text)
    while i < n:
        if text[i] == '"':
            i = _skip_string(text, i + 1, '"')
            continue
        if text.startswith("\\*", i):
            end = text.find("\n", i)
            end = n if end < 0 else end
            spans.append((i, end))
            i = end
            continue
        if text.startswith("(*", i):
            depth = 0
            j = i
            while j < n:
                if text.startswith("(*", j):
                    depth += 1
                    j += 2
                elif text.startswith("*)", j):
                    depth -= 1
                    j += 2
                    if depth == 0:
                        break
                else:
                    j += 1
            spans.append((i, j))
            i = j
            continue
        i += 1
    return spans


def _mermaid(text):
    spans = []
    position = 0
    for line in _lines(text):
        stripped = line.strip()
        if stripped.startswith("%%") and not MMD_DIRECTIVE.match(stripped):
            offset = position + len(line) - len(line.lstrip())
            spans.append((offset, position + len(line.rstrip("\r\n"))))
        position += len(line)
    return spans


SCANNERS = {
    ".py": _python,
    ".ts": _c_like,
    ".tsx": _c_like,
    ".js": _c_like,
    ".mjs": _c_like,
    ".cjs": _c_like,
    ".java": lambda text: _c_like(text, regex=False),
    ".dot": lambda text: _c_like(text, regex=False, hash_lines=True),
    ".sh": _shell,
    ".bash": _shell,
    ".yml": _yaml,
    ".yaml": _yaml,
    ".tla": _tla,
    ".cfg": _tla,
    ".mmd": _mermaid,
    ".gitignore": _line_hash,
    ".example": _line_hash,
}
SHEBANGS = {"python": _python, "node": _c_like, "bun": _c_like, "deno": _c_like, "sh": _shell, "bash": _shell}


def scanner(path, text):
    name = PurePosixPath(path).name
    suffix = name if name == ".gitignore" else PurePosixPath(path).suffix
    if suffix in SCANNERS:
        return SCANNERS[suffix]
    if suffix:
        return None
    if not text.startswith("#!"):
        return None
    words = [word.rsplit("/", 1)[-1] for word in text[2:].split("\n", 1)[0].split()]
    if words[:1] == ["env"]:
        words = [word for word in words[1:] if not word.startswith("-")]
    return SHEBANGS.get(re.sub(r"[\d.]+$", "", words[0])) if words else None


def comment_spans(path, text):
    scan = scanner(path, text)
    return scan(text) if scan else []


def strip(text, spans):
    if not spans:
        return text
    pieces = []
    previous = 0
    for start, end in spans:
        before = text[previous:start]
        if before.endswith((" ", "\t")) and text[end : end + 1] in (" ", "\t"):
            before = before.rstrip(" \t") + " "
            end += len(text[end:]) - len(text[end:].lstrip(" \t"))
        pieces.append(before)
        pieces.append("\0")
        previous = end
    pieces.append(text[previous:])
    marked = "".join(pieces)
    out = []
    for line in _lines(marked):
        if "\0" not in line:
            out.append(line)
            continue
        body = line.replace("\0", "")
        ending = body[len(body.rstrip("\r\n")) :]
        code = body.rstrip("\r\n").rstrip(" \t")
        if code.strip():
            out.append(code + ending)
    return "".join(out)


def tracked(root):
    listing = subprocess.run(
        ("git", "-c", "core.quotepath=off", "ls-files", "-z"), cwd=root, check=True, capture_output=True
    ).stdout
    return [name for name in listing.decode("utf-8").split("\0") if name]


def read(path):
    data = path.read_bytes()
    if b"\0" in data:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def findings(root):
    found = []
    for name in tracked(root):
        path = root / name
        text = read(path) if path.is_file() else None
        if text is None:
            continue
        for start, _ in comment_spans(name, text):
            found.append(f"{name}:{text.count(NEWLINE, 0, start) + 1}")
    return found


def strip_tree(root):
    changed = []
    for name in tracked(root):
        path = root / name
        text = read(path) if path.is_file() and not path.is_symlink() else None
        if text is None:
            continue
        new = strip(text, comment_spans(name, text))
        if new != text:
            path.write_bytes(new.encode("utf-8"))
            changed.append(name)
    return changed


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--fix", action="store_true", help="delete the comments in place")
    parser.add_argument("root", nargs="?", default=str(ROOT), help="a git checkout or a directory inside one (default: this checkout)")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    if args.fix:
        for name in strip_tree(root):
            print(f"stripped {name}")
        return 0
    found = findings(root)
    for line in found:
        print(f"{line}: comment")
    if found:
        print(f"{len(found)} comments. Run python3 scripts/comments.py --fix to delete them.", file=sys.stderr)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
