if __package__ in (None, ""):
    import sys
    from pathlib import Path

    _repo_root = Path(__file__).resolve().parent
    while _repo_root != _repo_root.parent and not (_repo_root / "tests" / "isolation.py").is_file():
        _repo_root = _repo_root.parent
    sys.path.insert(0, str(_repo_root))
from tests import isolation

isolation.install()

import json
import tempfile
import unittest
from .support import CATALOG, Repo, roles, setUpModule


OPUS = {"providerInstanceId": "claudeAgent", "model": "claude-opus-5-5"}
GROK = {"providerInstanceId": "grok", "model": "grok-4.7"}


def old_roles_file():
    """A roles file from before the retirement, naming retired roles in all three places."""
    return {
        "version": 1,
        "budget": "default",
        "mode": "full",
        "roles": {
            "how explorer": [GROK],
            "architect runners": [GROK, OPUS],
            "judgment and prose": [OPUS],
        },
        "exclude": [
            {"model": "grok*", "roles": ["reflect tooling", "bug-fix"]},
            {"model": "claude-opus*", "roles": ["why synthesizer", "hardest tasks"]},
        ],
        "backups": {
            "how explainer": [GROK],
            "bug-fix": [OPUS],
        },
    }


class RetiredRolesTest(unittest.TestCase):
    def test_the_list_names_every_retired_role_and_none_is_live(self):
        self.assertEqual(roles.RETIRED_ROLES, {
            "how explorer", "how explainer", "why investigators", "why synthesizer",
            "reflect tooling", "reflect judgment, divergent, synthesizer", "architect runners", "hardest tasks",
        })
        self.assertFalse(roles.RETIRED_ROLES & set(roles.ROLES))

    def test_a_user_or_project_file_naming_retired_roles_loads_and_resolves_the_rest(self):
        for where in ("user", "project"):
            with self.subTest(where=where), tempfile.TemporaryDirectory() as directory:
                repo = Repo(directory)
                repo.put(getattr(repo, where), old_roles_file())
                completed = repo.run("show", "--catalog", str(CATALOG), "--parent", "claudeAgent/claude-opus-5-5")
                self.assertEqual(completed.returncode, 0, completed.stderr)
                shown = json.loads(completed.stdout)["roles"]
                self.assertFalse(roles.RETIRED_ROLES & set(shown))
                self.assertEqual(shown["judgment and prose"]["seats"], [OPUS])
                self.assertEqual(shown["judgment and prose"]["source"], str(getattr(repo, where)))
                self.assertNotIn(roles.EXCLUDE_RULE, json.dumps(shown["judgment and prose"]))

    def test_an_exclude_entry_keeps_its_live_roles_and_one_naming_only_retired_roles_is_gone(self):
        rules = roles.parse_exclude(old_roles_file()["exclude"], "test")
        self.assertEqual(rules, ({"model": "grok*", "roles": ["bug-fix"]},))
        self.assertIsNotNone(roles.exclude_reason(GROK, rules, "bug-fix"))
        self.assertIsNone(roles.exclude_reason(OPUS, rules, "judgment and prose"))

    def test_a_retired_backups_key_is_dropped_and_the_live_one_kept(self):
        self.assertEqual(roles.parse_backups(old_roles_file()["backups"], "test"), {"bug-fix": (OPUS,)})

    def test_write_drops_every_retired_role_from_the_file_it_rewrites(self):
        for extra in ((), ("--replace",)):
            with self.subTest(flags=extra), tempfile.TemporaryDirectory() as directory:
                repo = Repo(directory)
                repo.put(repo.user, old_roles_file())
                completed = repo.write("--set", "bug-fix=claudeAgent/claude-opus-5-5", *extra)
                self.assertEqual(completed.returncode, 0, completed.stderr)
                text = repo.user.read_text(encoding="utf-8")
                written = json.loads(text)
                for name in roles.RETIRED_ROLES:
                    self.assertNotIn(name, text)
                self.assertEqual(written["exclude"], [{"model": "grok*", "roles": ["bug-fix"]}])
                self.assertEqual(written["backups"], {"bug-fix": [OPUS]})
                self.assertEqual(written["roles"]["bug-fix"], [OPUS])
                if not extra:
                    self.assertEqual(written["roles"]["judgment and prose"], [OPUS])

    def test_write_still_refuses_to_set_a_retired_role(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Repo(directory)
            completed = repo.write("--set", "how explorer=claudeAgent/claude-opus-5-5")
            self.assertEqual(completed.returncode, 2)
            self.assertIn("known role", completed.stderr)
            self.assertFalse(repo.user.exists())

    def test_an_unknown_role_that_was_never_retired_still_errors_in_every_place(self):
        files = {
            "roles": {"version": 1, "roles": {"how explorers": [OPUS]}},
            "exclude": {"version": 1, "exclude": [{"model": "grok*", "roles": ["how explorers"]}]},
            "backups": {"version": 1, "backups": {"how explorers": [OPUS]}},
        }
        for place, payload in files.items():
            with self.subTest(place=place), tempfile.TemporaryDirectory() as directory:
                repo = Repo(directory)
                repo.put(repo.user, payload)
                completed = repo.run("show", "--catalog", str(CATALOG), "--parent", "claudeAgent/claude-opus-5-5")
                self.assertEqual(completed.returncode, 2)
                self.assertEqual(completed.stdout, "")
                self.assertIn("'how explorers'", completed.stderr)


if __name__ == "__main__":
    unittest.main()
