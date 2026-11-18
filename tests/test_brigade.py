"""Acceptance tests that drive the real CLI on a fixture store.

Each brigade test calls the command in the test process through the shared helper, the way the coordinator
does.
"""

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
import os
import unittest
from pathlib import Path

from tests.brigade.support import BrigadeTest, ProcessReason, SCRIPT, real_process


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


class SpendControlsTest(BrigadeTest):
    """The four owner controls, driven through the commands the coordinator runs."""

    def test_cap_and_review_controls_read_back_from_set_json_and_one_kind_and_every_kind_clear(self):
        self.open()
        meta = json.loads(self.brigade("set", "--cap", "polish=1,study=2", "--review", "feature=full,fix=light"))
        self.assertEqual((meta["caps"], meta["review"]), ({"polish": 1, "study": 2}, {"feature": "full", "fix": "light"}))
        meta = json.loads(self.brigade("set", "--cap", "polish=", "--review", "fix="))
        self.assertEqual((meta["caps"], meta["review"]), ({"study": 2}, {"feature": "full"}))
        meta = json.loads(self.brigade("set", "--cap", "", "--review", ""))
        self.assertNotIn("caps", meta)
        self.assertNotIn("review", meta)
        self.assertEqual((self.at / "restaurant.json").read_text(), json.dumps(meta, indent=2) + "\n")

    def test_set_cap_and_review_refuse_a_bad_pair_a_kind_outside_the_five_a_bad_value_and_a_kind_twice(self):
        self.open()
        cases = (
            ("--cap", "polish", "--cap takes kind=<n> pairs, such as polish=1,study=1; got 'polish'"),
            ("--cap", "x=1", "--cap takes a kind of feature, fix, polish, upkeep, or study; got 'x'"),
            ("--cap", "polish=0", "--cap polish takes a whole number of 1 or more, or nothing for no cap; got '0'"),
            ("--cap", "polish=1,polish=2", "--cap names polish twice; pass one pair per kind"),
            ("--review", "polish", "--review takes kind=<mode> pairs, such as feature=full,fix=light; got 'polish'"),
            ("--review", "x=full", "--review takes a kind of feature, fix, polish, upkeep, or study; got 'x'"),
            ("--review", "polish=f", "--review polish takes full or light, or nothing for no depth; got 'f'"),
            ("--review", "polish=full,polish=light", "--review names polish twice; pass one pair per kind"),
        )
        for flag, text, refusal in cases:
            with self.subTest(flag=flag, text=text):
                before = (self.at / "restaurant.json").read_bytes()
                self.assertEqual(self.brigade("set", flag, text, ok=False), f"brigade: {refusal}")
                self.assertEqual((self.at / "restaurant.json").read_bytes(), before)

    def test_one_startable_output_gives_a_paused_goal_and_a_kind_cap_each_its_own_line_in_the_refill_order(self):
        self.queue()
        self.goal("activity view", "--share", "1")
        self.filed("Fix a", "--paths", "a.txt", "--goal", "G1")
        self.brigade("fire", "--tickets", "T1", "--station", "bug-fix", "--summary", "Fix a")
        self.brigade("set", "--cap", "fix=1")
        self.brigade("goal", "set", "G1", "--state", "paused")
        self.brigade("ticket", "add", "--summary", "Tidy b", "--kind", "polish", "--goal", "G1", "--paths", "b.txt")
        self.brigade("ticket", "add", "--summary", "Fix c", "--kind", "fix", "--paths", "c.txt")
        self.brigade("ticket", "add", "--summary", "Add d", "--kind", "feature", "--paths", "d.txt",
                     "--priority", "urgent")
        self.assertEqual(self.brigade("startable"), "\n".join([
            "workers: 1 of 2 running, 1 idle, auto-start: normal",
            "waiting tickets: 3, startable: 1, goal paused: 1, kind cap: 1",
            "T4 urgent feature, 0m: startable; d.txt",
            "  Add d",
            "T2 normal polish G1, 0m: its goal is paused; b.txt",
            "T3 normal fix, 0m: the fix cap holds (1 of 1); c.txt",
        ]))

    def test_a_paused_goal_starts_no_ticket_on_its_own_until_the_goal_is_open_again(self):
        self.queue()
        self.goal("activity view")
        self.filed("Fix a", "--paths", "a.txt", "--goal", "G1")
        self.brigade("goal", "set", "G1", "--state", "paused")
        self.assertEqual(self.brigade("startable").splitlines()[2], "T1 normal fix G1, 0m: its goal is paused; a.txt")
        self.assertEqual(self.brigade("fire", "--tickets", "T1", "--station", "bug-fix", "--summary", "Fix a", ok=False),
                         "brigade: nothing fired: its goal is paused")
        self.brigade("goal", "set", "G1", "--state", "open")
        self.assertEqual(self.brigade("startable").splitlines()[2], "T1 normal fix G1, 0m: startable; a.txt")
        self.assertEqual(self.brigade("fire", "--tickets", "T1", "--station", "bug-fix", "--summary", "Fix a"), "D1")

    def test_a_goal_share_of_three_holds_the_fourth_ticket_of_that_goal_back(self):
        self.queue("--workers", "4")
        self.goal("activity view", "--share", "3")
        for number in range(1, 5):
            self.brigade("ticket", "add", "--summary", f"Fix {number}", "--kind", "fix", "--goal", "G1",
                         "--paths", f"{number}.txt")
        self.assertEqual(self.brigade("startable").splitlines()[1:], [
            "waiting tickets: 4, startable: 3, goal share: 1",
            "T1 normal fix G1, 0m: startable; 1.txt", "  Fix 1",
            "T2 normal fix G1, 0m: startable; 2.txt", "  Fix 2",
            "T3 normal fix G1, 0m: startable; 3.txt", "  Fix 3",
            "T4 normal fix G1, 0m: the G1 share holds (3 of 3); 4.txt",
        ])


class OpenFlagHelpTest(BrigadeTest):
    """The two creation-only flags, as the open help states them to a user reopening a store."""

    CAP_HELP = ("--context-cap CONTEXT_CAP on creation, set the context cap; missing reads as 300000; "
                "creation with a cap, or with an explicit provider, writes the cap to the project's "
                ".claude/settings.local.json when the provider is claude, replacing any autoCompactWindow "
                "already there; a plain open writes nothing under the project root; an existing store is "
                "left alone")
    PROVIDER_HELP = ("--coordinator-provider COORDINATOR_PROVIDER on creation, choose claude or other; "
                     "missing uses claude; an existing store uses its saved provider")

    def test_open_help_states_the_two_flags_take_effect_on_creation_only(self):
        result = real_process(ProcessReason.HELP, SCRIPT, ["open", "--help"])
        self.assertEqual(result.returncode, 0, result.stderr)
        words = " ".join(result.stdout.split())
        self.assertIn(self.CAP_HELP, words)
        self.assertIn(self.PROVIDER_HELP, words)


class SetContextCapHelpTest(BrigadeTest):
    """The context cap setting, as the set help states it."""

    CAP_HELP = ('--context-cap CONTEXT_CAP the auto-compact window written to .claude/settings.local.json '
                'when the provider is claude; "" clears it to 300000')

    def test_set_help_states_the_window_path_and_the_empty_value_that_clears_to_300000(self):
        result = real_process(ProcessReason.HELP, SCRIPT, ["set", "--help"])
        self.assertEqual(result.returncode, 0, result.stderr)
        words = " ".join(result.stdout.split())
        cap_help = words.split("--context-cap CONTEXT_CAP ", 1)[1].split(" --coordinator-provider ", 1)[0]
        self.assertEqual(self.CAP_HELP, "--context-cap CONTEXT_CAP " + cap_help)


class ChangeNoteDirTest(BrigadeTest):
    """The changeNoteDir key: unset by default, set and cleared through set, refused when malformed."""

    def meta(self):
        return json.loads((self.at / "restaurant.json").read_text())

    def test_set_records_a_normalized_directory_and_empty_clears_it(self):
        self.open()
        self.assertNotIn("changeNoteDir", self.meta())
        meta = json.loads(self.brigade("set", "--change-note-dir", "notes/sub/"))
        self.assertEqual(meta["changeNoteDir"], "notes/sub")
        self.assertEqual(self.meta()["changeNoteDir"], "notes/sub")
        meta = json.loads(self.brigade("set", "--change-note-dir", ""))
        self.assertNotIn("changeNoteDir", meta)
        self.assertNotIn("changeNoteDir", self.meta())

    def test_set_refuses_a_bad_directory_and_writes_nothing(self):
        self.open()
        for text in ("/abs", "../up", "a/../..", "a,b", "has space"):
            with self.subTest(text=text):
                before = (self.at / "restaurant.json").read_bytes()
                error = self.brigade("set", "--change-note-dir", text, ok=False)
                self.assertIn("--change-note-dir", error)
                self.assertIn(f"got '{text}'", error)
                self.assertEqual((self.at / "restaurant.json").read_bytes(), before)

    def test_set_refuses_a_stored_directory_that_does_not_parse(self):
        self.open()
        path = self.at / "restaurant.json"
        meta = self.meta()
        for stored in ("/abs", 5):
            with self.subTest(stored=stored):
                meta["changeNoteDir"] = stored
                path.write_text(json.dumps(meta))
                before = path.read_bytes()
                error = self.brigade("set", "--reporting", "digest", ok=False)
                self.assertIn("changeNoteDir", error)
                self.assertEqual(path.read_bytes(), before)
                del meta["changeNoteDir"]


if __name__ == "__main__":
    unittest.main()
