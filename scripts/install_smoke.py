#!/usr/bin/env python3
"""Run install, doctor, and uninstall from this checkout against a home this run makes, on any platform.

Each step runs scripts/install.py in its own process with HOME set to the new home. A skill directory that already
holds one of the skill names stands in for an older copy, so the run proves --replace moves it aside and uninstall
puts it back. Every harness must reach N/N in doctor, where N is the number of built skills. On Windows each link must
be a directory junction. The stdout of a run that works holds one ok line per step. It exits 1 on the first failure.
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

CHECKOUT = Path(__file__).resolve().parents[1]
INSTALL = CHECKOUT / "scripts" / "install.py"
FOREIGN = "an older copy\n"

sys.path.insert(0, str(CHECKOUT / "scripts"))
import install  # noqa: E402


def run(home, *args):
    env = {key: value for key, value in os.environ.items() if key not in ("XDG_CONFIG_HOME", "CLAUDE_CONFIG_DIR")}
    env["HOME"] = str(home)
    return subprocess.run([sys.executable, str(INSTALL), *args], env=env, capture_output=True, text=True, timeout=300)


def expect(step, done, status, *needles):
    text = done.stdout + done.stderr
    missing = [needle for needle in needles if needle not in text]
    if done.returncode != status or missing:
        print(f"FAIL {step}: exit {done.returncode}, wanted {status}; missing {missing}\n{text}")
        sys.exit(1)
    print(f"ok {step}")
    return text


def check(step, condition, detail=""):
    if not condition:
        print(f"FAIL {step}: {detail}")
        sys.exit(1)
    print(f"ok {step}")


def main():
    names = install.skill_names()
    total = len(names)
    harnesses = install.HARNESSES
    root = Path(tempfile.mkdtemp(prefix="pstack-install-smoke-"))
    try:
        home = root / "home"
        saved = dict(os.environ)
        for name in ("XDG_CONFIG_HOME", "CLAUDE_CONFIG_DIR"):
            os.environ.pop(name, None)
        os.environ["HOME"] = str(home)
        try:
            directories = install.skill_dirs(None, True)
        finally:
            os.environ.clear()
            os.environ.update(saved)
        taken = directories["cursor"] / names[0]
        taken.mkdir(parents=True)
        (taken / "SKILL.md").write_text(FOREIGN, encoding="utf-8")

        expect("install stops on a taken path", run(home), 1, "rerun with --replace")
        expect("install --replace", run(home, "--replace"), 0, f"linked {total * len(harnesses)} skills")
        report = expect("doctor after install", run(home, "doctor"), 0)
        for harness in harnesses:
            check(f"doctor shows {total}/{total} for {harness}",
                  f"{directories[harness]}: {total}/{total} pstack-t3" in report, report)
        links = [directories[harness] / name for harness in harnesses for name in names]
        wrong = [str(link) for link in links if not install.system.is_link(link) or not install.points_here(link)]
        check("every skill is a link into this checkout", not wrong, wrong[:5])
        if install.system.WINDOWS:
            check("every link is a junction", all(install.system.is_junction(link) for link in links))
        expect("install again links nothing", run(home), 0, "linked 0 skills")
        expect("uninstall", run(home, "uninstall"), 0, f"removed {total * len(harnesses)} links, restored 1 entries")
        check("uninstall restores the older copy", (taken / "SKILL.md").read_text(encoding="utf-8") == FOREIGN)
        left = [str(link) for link in links if os.path.lexists(link) and link != taken]
        check("uninstall removes every link", not left, left[:5])
        backups = home / ".config" / "pstack-t3" / "backups"
        check("uninstall prunes the empty backup directories", not any(backups.iterdir()) if backups.exists() else True,
              list(backups.iterdir()) if backups.exists() else "")
        expect("doctor after uninstall", run(home, "doctor"), 1, f"0/{total} pstack-t3")
    finally:
        shutil.rmtree(root, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
