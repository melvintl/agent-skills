"""Black-box tests for bin/link.sh.

Each test runs the script against a fixture repo and a temporary home
directory, then asserts on the resulting links, exit code and report.
"""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "bin" / "link.sh"

# Everything the script may call. The tests run it with only these on PATH so
# that "npm is not installed" can be reproduced on a machine that has npm.
TOOLS = ["cat", "dirname", "ln", "mkdir", "readlink", "rm"]


class LinkTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name).resolve()
        self.home = root / "home"
        self.repo = root / "repo"
        self.bin = root / "bin"
        self.elsewhere = root / "elsewhere"
        for d in (self.home, self.repo / "skills", self.bin, self.elsewhere):
            d.mkdir(parents=True)
        for tool in TOOLS:
            (self.bin / tool).symlink_to(shutil.which(tool))
        self.claude = self.home / ".claude" / "skills"
        self.pi = self.home / ".pi" / "agent" / "skills"
        self.skill("shared")
        self.skill("pi-only")
        self.manifest("pi-only pi\n")

    def skill(self, name, node=False):
        d = self.repo / "skills" / name
        d.mkdir()
        (d / "SKILL.md").write_text(f"---\nname: {name}\ndescription: x\n---\n")
        if node:
            (d / "package.json").write_text("{}")
        return d

    def manifest(self, text):
        (self.repo / "skills.conf").write_text(text)

    def fake_npm(self):
        (self.bin / "npm").write_text('#!/bin/sh\necho "$@" > npm-ran\n')
        (self.bin / "npm").chmod(0o755)

    def run_link(self, *args, env=None):
        base = {
            "HOME": str(self.home),
            "PATH": str(self.bin),
            "AGENT_SKILLS_REPO": str(self.repo),
        }
        return subprocess.run(
            [shutil.which("bash"), str(SCRIPT), *args],
            env={**base, **(env or {})},
            capture_output=True,
            text=True,
        )

    def link(self, *args, env=None):
        result = self.run_link(*args, env=env)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout

    def assertLinked(self, directory, name):
        path = directory / name
        self.assertTrue(path.is_symlink(), f"{path} is not a link")
        self.assertEqual(os.readlink(path), str(self.repo / "skills" / name))

    def test_fresh_home_links_each_skill_to_its_agents(self):
        self.link()
        self.assertLinked(self.claude, "shared")
        self.assertLinked(self.pi, "shared")
        self.assertLinked(self.pi, "pi-only")
        self.assertFalse((self.claude / "pi-only").exists())

    def test_second_run_changes_nothing(self):
        self.link()
        self.assertEqual(self.link(), "")
        self.assertLinked(self.claude, "shared")

    def test_directory_without_skill_md_is_not_linked(self):
        (self.repo / "skills" / "notes").mkdir()
        self.link()
        self.assertFalse((self.claude / "notes").exists())

    def test_foreign_file_and_link_are_left_and_reported(self):
        self.claude.mkdir(parents=True)
        self.pi.mkdir(parents=True)
        (self.claude / "shared").mkdir()
        (self.pi / "shared").symlink_to(self.elsewhere)

        result = self.run_link()

        self.assertEqual(result.returncode, 1)
        self.assertIn("refused", result.stdout)
        self.assertTrue((self.claude / "shared").is_dir())
        self.assertFalse((self.claude / "shared").is_symlink())
        self.assertEqual(os.readlink(self.pi / "shared"), str(self.elsewhere))
        self.assertLinked(self.pi, "pi-only")

    def test_removed_skill_is_pruned_and_other_links_survive(self):
        self.link()
        (self.claude / "theirs").symlink_to(self.elsewhere)
        shutil.rmtree(self.repo / "skills" / "shared")

        self.link()

        self.assertFalse((self.claude / "shared").is_symlink())
        self.assertFalse((self.pi / "shared").is_symlink())
        self.assertEqual(os.readlink(self.claude / "theirs"), str(self.elsewhere))
        self.assertLinked(self.pi, "pi-only")

    def test_narrowed_audience_is_pruned(self):
        self.link()
        self.manifest("pi-only pi\nshared claude\n")

        self.link()

        self.assertLinked(self.claude, "shared")
        self.assertFalse((self.pi / "shared").is_symlink())

    def test_whole_directory_link_becomes_a_real_directory(self):
        old = self.elsewhere / "pi-skills"
        (old / "shared").mkdir(parents=True)
        (old / "local-only").mkdir()
        (old / "tool").symlink_to(self.elsewhere)
        self.pi.parent.mkdir(parents=True)
        self.pi.symlink_to(old)

        out = self.link()

        self.assertFalse(self.pi.is_symlink())
        self.assertLinked(self.pi, "shared")
        self.assertLinked(self.pi, "pi-only")
        self.assertTrue((old / "shared").is_dir(), "old directory was modified")
        self.assertIn("relink by hand: tool", out)
        self.assertIn("not carried over: local-only", out)
        self.assertNotIn("not carried over: shared", out)

    def test_pi_agent_dir_override_is_honoured(self):
        custom = self.home / "custom-pi"
        self.link(env={"PI_CODING_AGENT_DIR": str(custom)})
        self.assertLinked(custom / "skills", "shared")
        self.assertFalse(self.pi.exists())

    def test_dry_run_reports_and_changes_nothing(self):
        self.pi.mkdir(parents=True)
        (self.pi / "gone").symlink_to(self.repo / "skills" / "gone")

        out = self.link("--dry-run")

        self.assertIn("would link", out)
        self.assertIn("would prune", out)
        self.assertFalse(self.claude.exists())
        self.assertTrue((self.pi / "gone").is_symlink())
        self.assertFalse((self.pi / "shared").exists())

    def test_dry_run_leaves_whole_directory_link(self):
        self.pi.parent.mkdir(parents=True)
        self.pi.symlink_to(self.elsewhere)

        out = self.link("--dry-run")

        self.assertIn("would convert", out)
        self.assertTrue(self.pi.is_symlink())
        self.assertEqual(list(self.elsewhere.iterdir()), [])

    def test_missing_dependencies_are_installed(self):
        node = self.skill("node", node=True)
        self.fake_npm()

        self.link()

        self.assertEqual((node / "npm-ran").read_text().split()[0], "ci")

    def test_installed_dependencies_are_not_reinstalled(self):
        node = self.skill("node", node=True)
        (node / "node_modules").mkdir()
        self.fake_npm()

        self.link()

        self.assertFalse((node / "npm-ran").exists())

    def test_missing_npm_warns_and_still_links(self):
        self.skill("node", node=True)

        out = self.link()

        self.assertIn("npm not found", out)
        self.assertLinked(self.claude, "node")

    def test_manifest_naming_unknown_skill_or_agent_is_an_error(self):
        for text in ("nope pi\n", "shared emacs\n", "shared\n"):
            with self.subTest(manifest=text):
                self.manifest(text)
                result = self.run_link()
                self.assertEqual(result.returncode, 2)
                self.assertIn("skills.conf", result.stderr)
                self.assertFalse(self.claude.exists())

    def test_doctor_is_clean_after_link(self):
        self.link()
        out = self.link("--doctor")
        self.assertIn("0 problem(s)", out)

    def test_doctor_reports_each_state_and_changes_nothing(self):
        self.skill("node", node=True)
        self.skill("brave-search")
        self.link()
        (self.claude / "shared").unlink()
        (self.pi / "shared").unlink()
        (self.pi / "shared").symlink_to(self.elsewhere)
        (self.claude / "pi-only").symlink_to(self.repo / "skills" / "pi-only")
        shared = self.home / ".agents" / "skills" / "node"
        shared.mkdir(parents=True)

        result = self.run_link("--doctor")

        self.assertEqual(result.returncode, 1)
        out = result.stdout
        self.assertRegex(out, r"missing\s+claude\s+shared")
        self.assertRegex(out, r"blocked\s+pi\s+shared")
        self.assertRegex(out, r"stale\s+claude\s+pi-only")
        self.assertRegex(out, r"ok\s+pi\s+pi-only")
        self.assertRegex(out, r"deps\s+-\s+skills/node")
        self.assertIn("BRAVE_API_KEY is not set", out)
        self.assertRegex(out, r"clash\s+pi\s+node")
        self.assertFalse((self.claude / "shared").exists())
        self.assertTrue((self.claude / "pi-only").is_symlink())

    def test_doctor_accepts_set_env_and_flags_whole_directory_link(self):
        self.skill("brave-search")
        self.pi.parent.mkdir(parents=True)
        self.pi.symlink_to(self.elsewhere)

        result = self.run_link("--doctor", env={"BRAVE_API_KEY": "k"})

        self.assertEqual(result.returncode, 1)
        self.assertNotIn("BRAVE_API_KEY", result.stdout)
        self.assertRegex(result.stdout, r"unlinked\s+pi")
        self.assertTrue(self.pi.is_symlink())

    def test_unknown_option_is_a_usage_error(self):
        result = self.run_link("--force")
        self.assertEqual(result.returncode, 2)
        self.assertFalse(self.claude.exists())


if __name__ == "__main__":
    unittest.main()
