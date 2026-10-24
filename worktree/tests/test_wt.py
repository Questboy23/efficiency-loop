"""End-to-end tests for wt.py using a fake `claude` binary (no tokens spent).

Run: python3 -m unittest worktree/tests/test_wt.py
"""
import json, os, stat, subprocess, sys, tempfile, textwrap, unittest
from pathlib import Path

WT = Path(__file__).resolve().parent.parent / "wt.py"

# Fake agent: writes answer.txt. Content depends on FAKE_MODE and the worktree name,
# so tourney entries differ. Prints a Claude-style JSON result line.
FAKE = textwrap.dedent("""\
    #!/usr/bin/env python3
    import json, os, sys
    name = os.path.basename(os.getcwd())
    mode = os.environ.get("FAKE_MODE", "good")
    harness = "--plugin-dir" in sys.argv
    fcc = os.environ.get("ANTHROPIC_BASE_URL", "")
    if mode == "mixed":
        good = name.endswith("-1")
    elif mode == "bad":
        good = False
    else:
        good = True
    open("answer.txt", "w").write("42\\n" if good else "41\\n")
    open("metric.txt", "w").write("0.9" if good else "0.1")
    open("env.txt", "w").write(f"harness={harness} fcc={fcc}")
    toks = 500 if harness else 1000
    print(json.dumps({"usage": {"input_tokens": toks, "output_tokens": 10},
                      "total_cost_usd": 0, "num_turns": 2, "is_error": False}))
""")


class WtTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.repo = self.tmp / "proj"
        self.repo.mkdir()
        fake = self.tmp / "claude"
        fake.write_text(FAKE)
        fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
        self.env = dict(os.environ, WT_CLAUDE=str(fake), GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
                        GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
        g = lambda *a: subprocess.run(["git", *a], cwd=self.repo, check=True, capture_output=True, env=self.env)
        g("init", "-q", "-b", "main")
        (self.repo / ".gitignore").write_text(".env\n")
        (self.repo / ".env").write_text("SECRET=1\n")
        (self.repo / "metric.txt").write_text("0.5")
        g("add", "-A"); g("commit", "-qm", "init")

    def wt(self, *args, mode="good", ok=True):
        r = subprocess.run([sys.executable, str(WT), *args], cwd=self.repo, capture_output=True,
                           text=True, env={**self.env, "FAKE_MODE": mode})
        if ok:
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r.stdout + r.stderr

    def branches(self):
        return subprocess.run(["git", "branch", "--list", "wt/*"], cwd=self.repo,
                              capture_output=True, text=True).stdout

    def runs(self):
        return [json.loads(l) for l in (self.repo / ".wt" / "runs.jsonl").read_text().splitlines()]

    def test_new_copies_env_and_assigns_ports(self):
        self.wt("new", "a"); self.wt("new", "b")
        a, b = self.tmp / "proj.wt" / "a", self.tmp / "proj.wt" / "b"
        self.assertEqual((a / ".env").read_text(), "SECRET=1\n")
        self.assertNotEqual((a / ".wt-port").read_text(), (b / ".wt-port").read_text())
        self.assertIn(".wt/", (self.repo / ".git" / "info" / "exclude").read_text())
        self.assertIn("a", self.wt("ls"))
        self.wt("rm", "a")
        self.assertFalse(a.exists())
        self.assertNotIn("wt/a", self.branches())

    def test_tourney_keeps_only_passing_winner(self):
        out = self.wt("tourney", "fix it", "-n", "3", "--test", "grep -q 42 answer.txt", mode="mixed")
        self.assertIn("winner", out)
        self.assertEqual(self.branches().count("wt/"), 1)
        self.assertTrue(self.branches().strip().endswith("-1"))

    def test_tourney_merge(self):
        self.wt("tourney", "fix it", "-n", "2", "--test", "grep -q 42 answer.txt", "--merge")
        self.assertEqual((self.repo / "answer.txt").read_text(), "42\n")
        self.assertEqual(self.branches(), "")

    def test_tourney_all_fail_keeps_everything(self):
        out = self.wt("tourney", "fix", "-n", "2", "--test", "grep -q 42 answer.txt", mode="bad")
        self.assertIn("no agent passed", out)
        self.assertEqual(self.branches().count("wt/"), 2)

    def test_ab_arms_differ(self):
        out = self.wt("ab", "fix", "--test", "grep -q 42 answer.txt")
        self.assertIn("harness off: 1/1 pass, 1,010 mean tokens", out)
        self.assertIn("harness on : 1/1 pass, 510 mean tokens", out)
        self.assertEqual(self.branches(), "")

    def test_fcc_routes_to_proxy_and_discards_failures(self):
        out = self.wt("fcc", "fix", "--test", "grep -q 42 answer.txt", mode="bad")
        self.assertIn("discarded", out)
        self.assertEqual(self.branches(), "")
        self.wt("fcc", "fix", "--test", "grep -q 42 answer.txt", "--merge")
        self.assertIn("fcc=http://localhost:8082", (self.repo / "env.txt").read_text())

    def test_try_keeps_only_improvements(self):
        out = self.wt("try", "speed up", "--bench", "cat metric.txt", mode="bad")
        self.assertIn("discarded", out)
        out = self.wt("try", "speed up", "--bench", "cat metric.txt", "--merge")
        self.assertIn("gain +0.4", out)
        self.assertEqual((self.repo / "metric.txt").read_text(), "0.9")
        self.assertEqual([r["kept"] for r in self.runs()], [False, True])

    def test_bg_runs_with_port(self):
        self.wt("bg", "job", "--", "sh", "-c", "echo port=$PORT > out.txt")
        out = self.tmp / "proj.wt" / "job" / "out.txt"
        for _ in range(50):
            if out.exists() and out.read_text().strip():
                break
            __import__("time").sleep(0.1)
        self.assertRegex(out.read_text(), r"port=31\d0")


if __name__ == "__main__":
    unittest.main()
