if __package__ in (None, ""):
    import sys
    from pathlib import Path

    _repo_root = Path(__file__).resolve().parent
    while _repo_root != _repo_root.parent and not (_repo_root / "tests" / "isolation.py").is_file():
        _repo_root = _repo_root.parent
    sys.path.insert(0, str(_repo_root))
from tests import isolation

isolation.install()

import sys
import tempfile
import unittest
from pathlib import Path
from .support import (
    setUpModule,
    check,
)


class CheckoutRuleTest(unittest.TestCase):
    def _directory(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        return Path(temporary.name)

    def _pair(self, roles, install):
        root = self._directory()
        roles_path = root / "roles.py"
        install_path = root / "install.py"
        roles_path.write_text(roles)
        install_path.write_text(install)
        return roles_path, install_path

    def test_shared_source_matches_when_the_three_names_are_the_same(self):
        body = (
            'IGNORED = "same"\n'
            "def config_home(environ, default):\n"
            "    return environ\n"
            "def new_file(directory):\n"
            "    return directory\n"
        )
        roles_path, install_path = self._pair(body, body)
        self.assertEqual(check.shared_source_findings(roles_path, install_path), [])

    def test_shared_source_reports_a_comment_and_a_missing_name(self):
        install = (
            'IGNORED = "same"\n'
            "def config_home(environ, default):\n"
            "    return environ\n"
            "def new_file(directory):\n"
            "    return directory\n"
        )
        commented = (
            'IGNORED = "same"\n'
            "def config_home(environ, default):\n"
            "    # kept\n"
            "    return environ\n"
            "def new_file(directory):\n"
            "    return directory\n"
        )
        roles_path, install_path = self._pair(commented, install)
        self.assertEqual(check.shared_source_findings(roles_path, install_path), [
            "t3/scripts/roles.py: config_home differs from the one in scripts/install.py. Make the source text the same",
        ])
        missing = (
            "def config_home(environ, default):\n"
            "    return environ\n"
            "def new_file(directory):\n"
            "    return directory\n"
        )
        roles_path, install_path = self._pair(missing, install)
        self.assertEqual(check.shared_source_findings(roles_path, install_path), [
            "t3/scripts/roles.py: has no IGNORED. Define it with the same source text as scripts/install.py",
        ])

    def test_shared_source_reports_a_decorator_a_trailing_comment_or_an_unresolved_binding(self):
        same = (
            'IGNORED = "same"\n'
            "def config_home(environ, default):\n"
            "    return environ\n"
            "def new_file(directory):\n"
            "    return directory\n"
        )
        differs = "t3/scripts/roles.py: config_home differs from the one in scripts/install.py. Make the source text the same"
        cases = (
            (
                "a decorator on one function",
                'IGNORED = "same"\n'
                "def review_identity(function):\n"
                "    return function\n"
                "\n"
                "@review_identity\n"
                "def config_home(environ, default):\n"
                "    return environ\n"
                "def new_file(directory):\n"
                "    return directory\n",
                [differs],
            ),
            (
                "a trailing inline comment",
                'IGNORED = "same"\n'
                "def config_home(environ, default):\n"
                "    return environ  # review comment\n"
                "def new_file(directory):\n"
                "    return directory\n",
                [differs],
            ),
            (
                "an indented trailing comment",
                'IGNORED = "same"\n'
                "def config_home(environ, default):\n"
                "    return environ\n"
                "    # review comment\n"
                "def new_file(directory):\n"
                "    return directory\n",
                [differs],
            ),
            (
                "a later definition inside if",
                'IGNORED = "same"\n'
                "def config_home(environ, default):\n"
                "    return environ\n"
                "def new_file(directory):\n"
                "    return directory\n"
                "if True:\n"
                "    def config_home(environ, default):\n"
                "        return environ\n",
                ["t3/scripts/roles.py:7: config_home is bound where the static comparison cannot resolve it"],
            ),
            (
                "a later definition inside try",
                'IGNORED = "same"\n'
                "def config_home(environ, default):\n"
                "    return environ\n"
                "def new_file(directory):\n"
                "    return directory\n"
                "try:\n"
                "    def new_file(directory):\n"
                "        return directory\n"
                "except Exception:\n"
                "    pass\n",
                ["t3/scripts/roles.py:7: new_file is bound where the static comparison cannot resolve it"],
            ),
            (
                "a conditional assignment to IGNORED",
                'IGNORED = "same"\n'
                "def config_home(environ, default):\n"
                "    return environ\n"
                "def new_file(directory):\n"
                "    return directory\n"
                "if True:\n"
                '    IGNORED = "different"\n',
                ["t3/scripts/roles.py:7: IGNORED is bound where the static comparison cannot resolve it"],
            ),
            (
                "IGNORED +=",
                'IGNORED = "same"\n'
                "def config_home(environ, default):\n"
                "    return environ\n"
                "def new_file(directory):\n"
                "    return directory\n"
                'IGNORED += " different"\n',
                ["t3/scripts/roles.py:6: IGNORED is bound where the static comparison cannot resolve it"],
            ),
        )
        for label, roles, expected in cases:
            with self.subTest(label):
                roles_path, install_path = self._pair(roles, same)
                self.assertEqual(check.shared_source_findings(roles_path, install_path), expected)
