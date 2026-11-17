if __package__ in (None, ""):
    import sys
    from pathlib import Path

    _repo_root = Path(__file__).resolve().parent
    while _repo_root != _repo_root.parent and not (_repo_root / "tests" / "isolation.py").is_file():
        _repo_root = _repo_root.parent
    sys.path.insert(0, str(_repo_root))
from tests import isolation

isolation.install()

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


def fence_git_environment():
    """Remove every GIT_* variable from os.environ and point GIT_CONFIG_GLOBAL and GIT_CONFIG_SYSTEM at the null device.

    A module cleanup restores os.environ to what it held at this call.
    """
    saved = dict(os.environ)

    def restore():
        os.environ.clear()
        os.environ.update(saved)

    unittest.addModuleCleanup(restore)
    for name in [name for name in os.environ if name.startswith("GIT_")]:
        del os.environ[name]
    os.environ["GIT_CONFIG_GLOBAL"] = os.devnull
    os.environ["GIT_CONFIG_SYSTEM"] = os.devnull


def setUpModule():
    fence_git_environment()


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/comments.py"

CASES = {
    "tool.py": (
        '#!/usr/bin/env python3\n# -*- coding: utf-8 -*-\n"""Docstring stays."""\n# gone\nimport os  # noqa: F401\nx = "# not a comment"  # gone\n',
        '#!/usr/bin/env python3\n# -*- coding: utf-8 -*-\n"""Docstring stays."""\nimport os  # noqa: F401\nx = "# not a comment"\n',
    ),
    "app.ts": (
        '// gone\nconst url = "http://x"; // gone\n/**\n * gone\n */\nconst re = /\\/\\//g;\nconst t = `// ${a /* gone */ + 1}`;\n// @ts-expect-error kept\nconst n: number = "s";\n',
        'const url = "http://x";\nconst re = /\\/\\//g;\nconst t = `// ${a + 1}`;\n// @ts-expect-error kept\nconst n: number = "s";\n',
    ),
    "run.sh": (
        "#!/bin/sh\n# gone\necho \"# kept\" '# kept' $# ${#x} # gone\ncat <<'EOF'\n# heredoc text\nEOF\n",
        "#!/bin/sh\necho \"# kept\" '# kept' $# ${#x}\ncat <<'EOF'\n# heredoc text\nEOF\n",
    ),
    "ci.yml": (
        "# gone\non: push\njobs:\n  a:\n    steps:\n      - run: |\n          # gone\n          echo '#kept' # gone\n        env:\n          X: \"a # b\"  # gone\n",
        "on: push\njobs:\n  a:\n    steps:\n      - run: |\n          echo '#kept'\n        env:\n          X: \"a # b\"\n",
    ),
    "Spec.tla": (
        '---- MODULE Spec ----\n\\* gone\n(* gone (* nested *) *)\nInit == x = "\\* kept" \\* gone\n====\n',
        '---- MODULE Spec ----\nInit == x = "\\* kept"\n====\n',
    ),
    "chart.mmd": ("%%{init: {}}%%\n%% gone\nstateDiagram-v2\n", "%%{init: {}}%%\nstateDiagram-v2\n"),
    "tool": ("#!/usr/bin/env node\n// gone\nconsole.log(1);\n", "#!/usr/bin/env node\nconsole.log(1);\n"),
}


def git(directory, *arguments):
    subprocess.run(("git", *arguments), cwd=directory, check=True, capture_output=True)


def run(*arguments):
    return subprocess.run((sys.executable, str(SCRIPT), *arguments), capture_output=True, text=True)


class CommentsTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        git(self.root, "init", "--quiet")

    def write(self, files):
        for name, text in files.items():
            (self.root / name).write_bytes(text.encode())
        git(self.root, "add", "--all")

    def test_fix_deletes_comments_and_keeps_code_strings_and_tool_directives(self):
        self.write({name: before for name, (before, _) in CASES.items()})
        self.assertEqual(run("--fix", str(self.root)).returncode, 0)
        for name, (_, after) in CASES.items():
            with self.subTest(file=name):
                self.assertEqual((self.root / name).read_bytes().decode(), after)
        result = run(str(self.root))
        self.assertEqual((result.returncode, result.stdout), (0, ""))

    def test_the_check_names_a_reintroduced_comment_and_fails(self):
        self.write({name: after for name, (_, after) in CASES.items()})
        self.assertEqual(run(str(self.root)).returncode, 0)
        self.write({"tool.py": CASES["tool.py"][1] + "y = 1  # back again\n"})
        result = run(str(self.root))
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "tool.py:6: comment\n")

    def test_crlf_files_keep_their_line_endings(self):
        before, after = CASES["run.sh"]
        self.write({"run.sh": before.replace("\n", "\r\n")})
        run("--fix", str(self.root))
        self.assertEqual((self.root / "run.sh").read_bytes(), after.replace("\n", "\r\n").encode())

    def test_markdown_and_untracked_files_are_not_checked(self):
        self.write({"notes.md": "# Heading\n\n```sh\n# example\n```\n"})
        (self.root / "loose.py").write_text("# untracked\n")
        result = run(str(self.root))
        self.assertEqual((result.returncode, result.stdout), (0, ""))


if __name__ == "__main__":
    unittest.main()
