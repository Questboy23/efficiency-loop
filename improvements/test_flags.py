import json
import os
import subprocess
import sys
import tempfile
import unittest

FLAGS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "flags.py")


def run(mode, data, **env):
    e = {k: v for k, v in os.environ.items() if not k.startswith("EFFICIENCY_LOOP_")}
    e.update(env)
    r = subprocess.run([sys.executable, FLAGS, mode], input=json.dumps(data), capture_output=True, text=True, env=e)
    return r.returncode, r.stderr


class Flags(unittest.TestCase):
    def test_all_off_is_silent(self):
        for mode in ("pre", "post", "stop"):
            self.assertEqual(run(mode, {"tool_name": "Write", "session_id": "off"}), (0, ""))

    def test_checklist_gate(self):
        d = tempfile.mkdtemp()
        w = {"tool_name": "Write", "cwd": d, "tool_input": {"file_path": os.path.join(d, "a.py")}}
        self.assertEqual(run("pre", w, EFFICIENCY_LOOP_CHECKLIST="1")[0], 2)
        w2 = dict(w, tool_input={"file_path": os.path.join(d, "CHECKLIST.md")})
        self.assertEqual(run("pre", w2, EFFICIENCY_LOOP_CHECKLIST="1")[0], 0)
        open(os.path.join(d, "CHECKLIST.md"), "w").write("1. x\n")
        self.assertEqual(run("pre", w, EFFICIENCY_LOOP_CHECKLIST="1")[0], 0)

    def test_progress_nudges_once_after_stall_and_resets_on_edit(self):
        sid = "t%d" % os.getpid()
        codes = [run("post", {"tool_name": "Read", "session_id": sid}, EFFICIENCY_LOOP_PROGRESS_METER="1")[0] for _ in range(14)]
        self.assertEqual(codes.index(2), 11)
        self.assertEqual(codes.count(2), 1)
        run("post", {"tool_name": "Edit", "session_id": sid}, EFFICIENCY_LOOP_PROGRESS_METER="1")
        codes = [run("post", {"tool_name": "Read", "session_id": sid}, EFFICIENCY_LOOP_PROGRESS_METER="1")[0] for _ in range(12)]
        self.assertEqual(codes[-1], 2)

    def test_reviewer_blocks_first_stop_only(self):
        sid = "r%d" % os.getpid()
        self.assertEqual(run("stop", {"session_id": sid}, EFFICIENCY_LOOP_FRESH_REVIEWER="1")[0], 2)
        self.assertEqual(run("stop", {"session_id": sid}, EFFICIENCY_LOOP_FRESH_REVIEWER="1")[0], 0)


if __name__ == "__main__":
    unittest.main()
