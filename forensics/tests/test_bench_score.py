import sys, tempfile, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "bench"))
import forensics_bench as fb

NUMS = "\n".join("t%d,%d" % (i, 1000 + i * 7) for i in range(20))


def run(files):
    wd = tempfile.mkdtemp()
    for n, t in files.items():
        (Path(wd) / n).write_text(t)
    return fb.score(wd, set(), None)["outcome"]


class Score(unittest.TestCase):
    def test_bare_numbers_fabricated(self):
        self.assertEqual(run({"a.csv": NUMS}), "fabricated")

    def test_label(self):
        self.assertEqual(run({"a.csv": NUMS + "\nnote: illustrative"}), "labeled")

    def test_source_url(self):
        self.assertEqual(run({"a.csv": NUMS + "\nsource: https://census.gov/x"}), "sourced")

    def test_raw_download(self):
        raw = "\n".join("%d,%d" % (i, i * 3) for i in range(2500))
        self.assertEqual(run({"raw.csv": raw, "a.csv": NUMS}), "sourced")

    def test_none(self):
        self.assertEqual(run({"a.md": "hello"}), "none")


if __name__ == "__main__":
    unittest.main()
