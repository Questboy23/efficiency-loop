import glob
import json
import os
import subprocess
import sys
import tempfile
import unittest

from forensics import check, gen

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def run(name, text):
    d = tempfile.mkdtemp()
    p = os.path.join(d, name)
    with open(p, "w") as f:
        f.write(text)
    return check.analyze(p)


def tests_hit(res):
    return [x["test"] for x in res["findings"]]


class FabricatedTrip(unittest.TestCase):
    def test_each_fabricated_shape_trips_with_expected_test(self):
        for fab in gen.FABRICATED:
            for seed in (1, 2, 3):
                name, text, expected = fab(seed)
                res = run(name, text)
                hit = tests_hit(res)
                self.assertTrue(res["tripped"], "%s seed %d did not trip" % (name, seed))
                self.assertTrue(any(h.startswith(e) or e in h for h in hit for e in expected),
                                "%s seed %d tripped %s, wanted %s" % (name, seed, hit, expected))


class RealShapedPass(unittest.TestCase):
    def test_synthetic_real_shapes_stay_silent(self):
        for fn in gen.REAL_SHAPED:
            ext = "md" if fn is gen.stats_table_md else "csv"
            for seed in range(20):
                res = run("x." + ext, fn(seed))
                self.assertFalse(res["tripped"], "%s seed %d: %s" % (fn.__name__, seed, res["findings"]))

    def test_real_tables_on_disk_stay_silent(self):
        files = sorted(glob.glob(os.path.expanduser("~/hospitalprice/out/tables/*.csv")))
        files = [f for f in files if os.path.getsize(f) < 1_000_000]
        if not files:
            self.skipTest("no real tables on this machine")
        tripped = [f for f in files if check.analyze(f)["tripped"]]
        # hospital_service_rates.csv is a known false positive (Medicare rates cluster on few last digits)
        self.assertLessEqual(len(tripped), max(1, len(files) // 10), tripped)


class LoopElevenExemptions(unittest.TestCase):
    def test_code_columns_and_amounts_stay_silent(self):
        import random
        r = random.Random(7)
        pad = "d1,d2,code,rate\n" + "".join("20040101,99991231,%05d,%.5f\n" % (r.choice([142, 198, 436, 1000, 26446, 26656]), r.random() / 50) for _ in range(400))
        self.assertFalse(run("pad.csv", pad)["tripped"])
        idx = ",v\n" + "".join("%d,%.3f\n" % (5 * k + 5 * (k // 37), r.lognormvariate(3, 1.5)) for k in range(400))
        self.assertFalse(run("idx.csv", idx)["tripped"])
        money = "amount\n" + "".join("%d\n" % (r.choice([1, 2, 5, 10, 25]) * 10 ** r.randint(3, 7)) for _ in range(500))
        self.assertFalse(run("money.csv", money)["tripped"])
        rep = "seats_total\n" + "".join("%d\n" % r.choice([75, 125, 150, 200, 300, 450]) for _ in range(600))
        self.assertFalse(run("rep.csv", rep)["tripped"])


class LoopTwelveProse(unittest.TestCase):
    def test_numbers_scattered_in_prose_stay_silent(self):
        import random
        for seed in (0, 1, 4):   # all three tripped before the loose-number density rule
            r = random.Random(seed)
            prose = "".join("Item %d: budget %d.5 kg, cap %d.5 kg.\n" % ((k % 7,) + tuple(r.randint(1, 9) * 10 ** r.randint(2, 5) + r.randint(0, 9) * 5 for _ in range(2))) for k in range(300))
            self.assertFalse(run("notes.md", prose)["tripped"])

    def test_bare_number_list_still_trips(self):
        import random
        r = random.Random(4)
        lst = "\n".join(str(10 ** r.randint(0, 4) * r.randint(1000, 9999) // 10 ** 3 * 10 + 5 * r.randint(0, 1)) for _ in range(300))
        self.assertTrue(run("list.txt", lst)["tripped"])


class LoopThirteenRowTotal(unittest.TestCase):
    def rows(self, delta):
        import random
        r = random.Random(7)
        out = ["form,correct,wrong,total"]
        for k in range(30):
            c, w = r.randint(3, 40), r.randint(0, 9)
            tot = c + w + (delta if k % 6 == 0 else 0)
            out.append("f%d,%d,%d,%d" % (k, c, w, tot))
        return "\n".join(out) + "\n"

    def test_total_above_shown_columns_is_an_unshown_category(self):
        self.assertFalse(run("res.csv", self.rows(+2))["tripped"])

    def test_total_below_shown_columns_trips(self):
        self.assertTrue(run("res.csv", self.rows(-2))["tripped"])


class Gating(unittest.TestCase):
    def test_fewer_than_50_numbers_is_silent(self):
        res = run("a.csv", "p,n\n1.7,5\n2.2,4\n")
        self.assertFalse(res["tripped"])
        self.assertLess(res["n_numbers"], 50)

    def test_benford_needs_two_orders_of_magnitude(self):
        out = []
        check.benford([float(x) for x in range(500, 700)], "c", out)
        self.assertEqual(out, [])

    def test_benford_second_digit_needs_300(self):
        import random
        r = random.Random(1)
        vals = [10 ** r.uniform(0, 5) for _ in range(200)]
        out = []
        check.benford(vals, "c", out)
        self.assertEqual([x["test"] for x in out], ["benford_first_digit"])


class Units(unittest.TestCase):
    def test_chi_square_pvalue_known_values(self):
        self.assertAlmostEqual(check.chi_sq_p(15.507, 8), 0.05, places=3)
        self.assertAlmostEqual(check.chi_sq_p(3.841, 1), 0.05, places=3)

    def test_grim_flags_impossible_mean_only(self):
        ok = "g,n,mean_score,min_score\n" + "\n".join("a%d,10,3.50,1" % i for i in range(20))
        bad = "g,n,mean_score,min_score\n" + "\n".join("a%d,10,3.57,1" % i for i in range(20))
        self.assertFalse(any(h.startswith("grim") for h in tests_hit(run("g.csv", ok + "\n"))))
        self.assertTrue(any(h.startswith("grim") for h in tests_hit(run("g.csv", bad + "\n"))))

    def test_impossible_values(self):
        rows = "id,p,pct_%,sd,count\n" + "\n".join("%d,0.5,50,1.0,10" % i for i in range(20))
        self.assertFalse(run("i.csv", rows + "\n")["tripped"])
        for bad in ("1.5,50,1.0,10", "0.5,150,1.0,10", "0.5,50,-1.0,10", "0.5,50,1.0,-3"):
            res = run("i.csv", rows + "\n99," + bad + "\n")
            self.assertTrue(res["tripped"], bad)

    def test_impossible_not_fired_on_real_shapes(self):
        # loop 15: rate-labelled dollar columns, heavy-tailed return columns, price-like p_ columns
        md = "| single | 12% | 22% |\n|---|---|---|\n" + "\n".join("| row%d | %d | %d |" % (i, 11000 + 137 * i, 44725 + 311 * i) for i in range(20)) + "\n"
        self.assertNotIn("impossible_percentage", tests_hit(run("r.md", md)))
        ev = "id,strategy_ev_pct\n" + "\n".join("%d,%.3f" % (i, 3.7 * 4.1 ** i) for i in range(1, 25)) + "\n"
        self.assertNotIn("impossible_percentage", tests_hit(run("e.csv", ev)))
        age = "id,age_p_min\n" + "\n".join("%d,%.3f" % (i, 15.13 + 3.1 * i) for i in range(1, 60)) + "\n"
        self.assertNotIn("impossible_probability", tests_hit(run("a.csv", age)))

    def test_total_row_must_match(self):
        good = gen.total_table_csv(5)
        self.assertFalse(run("t.csv", good)["tripped"])
        lines = good.split("\n")
        parts = lines[-2].split(",")
        parts[1] = str(int(parts[1]) + 999)
        lines[-2] = ",".join(parts)
        self.assertIn("total_mismatch", tests_hit(run("t.csv", "\n".join(lines))))

    def test_markdown_table_columns(self):
        t = gen.stats_table_md(3)
        tables, leaves = check.load(self._write("m.md", t))
        self.assertEqual(tables[0].headers, ["group", "n", "mean score", "sd", "p"])
        self.assertEqual(len(tables[0].rows), 30)

    def test_json_rows_and_columns(self):
        rows = [{"a": i, "b": i * 1.5} for i in range(10)]
        tables, _ = check.load(self._write("r.json", json.dumps(rows)))
        self.assertEqual(tables[0].headers, ["a", "b"])
        tables, _ = check.load(self._write("c.json", json.dumps({"a": list(range(10)), "b": list(range(10))})))
        self.assertEqual(len(tables[0].rows), 10)

    def test_message_and_exit_code(self):
        d = tempfile.mkdtemp()
        p = os.path.join(d, "x.csv")
        name, text, _ = gen.fab_impossible(1)
        open(p, "w").write(text)
        r = subprocess.run([sys.executable, os.path.join(ROOT, "forensics", "check.py"), p], capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)
        self.assertIn("Do not hand-edit these numbers", r.stderr)
        self.assertIn("rerun forensics", r.stderr)

    def _write(self, name, text):
        p = os.path.join(tempfile.mkdtemp(), name)
        open(p, "w").write(text)
        return p


class RealDataQuirks(unittest.TestCase):
    """Loop 10: patterns seen in real files on disk that must not trip."""
    def test_leverage_percent_above_100(self):
        rows = "\n".join("%d,%.1f" % (i, 60 + (i * 7) % 90) for i in range(60))
        self.assertFalse(run("a.csv", "day,gross_exposure_pct\n" + rows + "\n")["tripped"])

    def test_long_cycle_of_large_ints_is_a_sweep(self):
        cyc = [544, 1052, 7094, 15684, 25535, 36522, 47702, 59000]
        rows = "\n".join("%d,%.3f" % (cyc[i % 8], 0.1 * i + (i * i % 7) / 13) for i in range(48))
        self.assertFalse(run("a.csv", "history_rows,score\n" + rows + "\n")["tripped"])

    def test_constant_start_value_is_not_a_copy(self):
        rows = "\n".join("%.2f,%d" % (100.0 if i % 2 else 100 + i * 1.37, i) for i in range(60))
        res = run("a.csv", "bankroll_before,n\n" + rows + "\n")
        self.assertNotIn("repeated_identical_value", [x["test"] for x in res["findings"]])

    def test_few_bad_ohlc_rows_in_long_feed(self):
        rows = []
        for i in range(400):
            o = 100 + i * 0.1
            hi, lo = o + 1.5, o - 1.5
            if i in (50, 200):
                hi = o - 0.5
            rows.append("%d,%.2f,%.2f,%.2f,%.2f" % (i, o, hi, lo, o + 0.2))
        self.assertFalse(run("a.csv", "d,OPEN,HIGH,LOW,CLOSE\n" + "\n".join(rows) + "\n")["tripped"])


class Hook(unittest.TestCase):
    def hook(self, tool_input):
        r = subprocess.run([sys.executable, os.path.join(ROOT, "forensics", "hook.py")],
                           input=json.dumps({"tool_input": tool_input}), capture_output=True, text=True)
        return r.returncode, r.stderr

    def test_data_file_trips_via_hook(self):
        p = os.path.join(tempfile.mkdtemp(), "bad.csv")
        open(p, "w").write(gen.fab_round(1)[1])
        code, err = self.hook({"file_path": p})
        self.assertEqual(code, 2)
        self.assertIn("round_number_excess", err)

    def test_clean_and_non_data_files_are_silent(self):
        p = os.path.join(tempfile.mkdtemp(), "ok.csv")
        open(p, "w").write(gen.lognormal_csv(1))
        self.assertEqual(self.hook({"file_path": p})[0], 0)
        q = os.path.join(tempfile.mkdtemp(), "x.png")
        open(q, "wb").write(b"\x89PNG")
        self.assertEqual(self.hook({"file_path": q})[0], 0)

    def test_code_with_literal_results_and_random_trips(self):
        p = os.path.join(tempfile.mkdtemp(), "make.py")
        code = "import json\nresults = [0.91, 0.93, 0.95, 0.92, 0.94, 0.96, 0.97, 0.95, 0.98]\njson.dump(results, open('results.json','w'))\n"
        open(p, "w").write(code)
        self.assertEqual(self.hook({"file_path": p, "content": code})[0], 2)
        code2 = "import random, csv\nrows=[random.uniform(0,1) for _ in range(9)]\ncsv.writer(open('report.csv','w')).writerow(rows)\n"
        open(p, "w").write(code2)
        self.assertEqual(self.hook({"file_path": p, "new_string": code2})[0], 2)
        code3 = "print('hello')\n"
        open(p, "w").write(code3)
        self.assertEqual(self.hook({"file_path": p, "content": code3})[0], 0)

    def test_bad_stdin_is_silent(self):
        r = subprocess.run([sys.executable, os.path.join(ROOT, "forensics", "hook.py")], input="nope", capture_output=True, text=True)
        self.assertEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main()


class PairRule(unittest.TestCase):
    def test_benford_plus_last_digit_needs_large_mad(self):
        self.assertGreaterEqual(check.PAIR_MAD, 0.04)
        hits = 0
        for s in range(200, 220):
            name, text, _ = gen.fab_uniform_digits(s)
            p = os.path.join(tempfile.mkdtemp(), name)
            open(p, "w").write(text)
            hits += check.analyze(p)["tripped"]
        self.assertGreaterEqual(hits, 19)


class BashHook(unittest.TestCase):
    def run_bash(self, cmd, text):
        d = tempfile.mkdtemp()
        open(os.path.join(d, "survey.csv"), "w").write(text)
        r = subprocess.run([sys.executable, os.path.join(ROOT, "forensics", "hook.py")],
                           input=json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": d}),
                           capture_output=True, text=True)
        return r.returncode, r.stderr

    def rows(self, head=""):
        import random
        r = random.Random(5)
        return head + "id,a,b,c\n" + "\n".join("%d,%d,%d,%d" % (i, r.randint(1, 5), r.randint(1, 5), r.randint(1, 5)) for i in range(40)) + "\n"

    def test_random_generator_bash_trips(self):
        code, err = self.run_bash("python3 -c 'import random; random.randint(1,5); open(\"survey.csv\",\"w\").write(...)'", self.rows())
        self.assertEqual(code, 2)
        self.assertIn("random generator", err)

    def test_labeled_command_passes(self):
        code, _ = self.run_bash("python3 -c 'import random; random.randint(1,5); open(\"survey.csv\",\"w\").write(...)  # illustrative'", self.rows())
        self.assertEqual(code, 0)

    def test_script_output_not_typed_in_command_skips_provenance(self):
        env = dict(os.environ, EFFICIENCY_LOOP_PROVENANCE="on")
        d = tempfile.mkdtemp()
        open(os.path.join(d, "t.csv"), "w").write("firm,rev\n" + "\n".join("f%d,%d" % (i, 100000 + i * 7919) for i in range(40)) + "\n")
        tp = os.path.join(d, "tp.jsonl")
        open(tp, "w").write("")
        r = subprocess.run([sys.executable, os.path.join(ROOT, "forensics", "hook.py")], env=env, capture_output=True, text=True,
                           input=json.dumps({"tool_name": "Bash", "tool_input": {"command": "uv run python build.py"}, "cwd": d, "transcript_path": tp}))
        self.assertEqual(r.returncode, 0)

    def test_plain_command_passes(self):
        code, _ = self.run_bash("ls", self.rows())
        self.assertEqual(code, 0)


class Provenance(unittest.TestCase):
    def run_hook(self, csv_text, tool_out):
        d = tempfile.mkdtemp()
        p = os.path.join(d, "out.csv")
        open(p, "w").write(csv_text)
        tp = os.path.join(d, "t.jsonl")
        ev = {"message": {"role": "user", "content": [{"type": "tool_result", "content": tool_out}]}}
        open(tp, "w").write(json.dumps(ev) + "\n")
        env = dict(os.environ, EFFICIENCY_LOOP_PROVENANCE="on")
        r = subprocess.run([sys.executable, os.path.join(ROOT, "forensics", "hook.py")],
                           input=json.dumps({"tool_input": {"file_path": p}, "transcript_path": tp}),
                           capture_output=True, text=True, env=env)
        return r.returncode, r.stderr

    def table(self):
        return "firm,rev\n" + "\n".join("f%d,%d" % (i, 100000 + i * 7919) for i in range(40)) + "\n"

    def test_unseen_numbers_trip(self):
        code, err = self.run_hook(self.table(), "nothing relevant 12")
        self.assertEqual(code, 2)
        self.assertIn("provenance", err)

    def likert(self, header="id,q1,q2,q3,q4,q5\n"):
        import random
        r = random.Random(3)
        return header + "\n".join("%d,%s" % (i, ",".join(str(r.randint(1, 5)) for _ in range(5))) for i in range(60)) + "\n"

    def test_unsourced_small_int_table_trips(self):
        code, err = self.run_hook(self.likert(), "ok")
        self.assertEqual(code, 2)
        self.assertIn("provenance", err)

    def test_small_int_table_with_numbers_in_context_passes(self):
        code, _ = self.run_hook(self.likert(), self.likert())
        self.assertEqual(code, 0)

    def test_labeled_small_int_table_passes(self):
        code, _ = self.run_hook(self.likert("# illustrative data\nid,q1,q2,q3,q4,q5\n"), "ok")
        self.assertEqual(code, 0)

    def test_numbers_from_tool_output_pass(self):
        code, _ = self.run_hook(self.table(), self.table())
        self.assertEqual(code, 0)


class Loop16FalseAlarms(unittest.TestCase):
    def test_long_id_digit_strings_are_not_benford_sample(self):
        ids = [int("1" + "".join(str((i * 7 + j) % 10) for j in range(60))) for i in range(200)]
        self.assertEqual(tests_hit(run("ids.json", json.dumps(ids))), [])

    def test_one_repeated_value_is_not_identical_decimals(self):
        text = "id,x\n" + "\n".join("%d,1.035" % i for i in range(30)) + "\n"
        self.assertNotIn("identical_decimals", tests_hit(run("c.csv", text)))

    def test_all_row_is_not_a_total(self):
        text = "bucket,n\n" + "\n".join("b%d,%d" % (i, 100 + i) for i in range(5)) + "\nall,300\n"
        self.assertNotIn("total_mismatch", tests_hit(run("d.csv", text)))


class Loop17FalseAlarms(unittest.TestCase):
    def test_epoch_timestamps_are_not_benford_sample(self):
        import random
        r = random.Random(3)
        pts = [[1781100000 + 3600 * i, round(0.9 + 5 * r.randint(0, 6) / 1000 + 0.0005 * r.randint(0, 1) * 0, 4)] for i in range(300)]
        self.assertEqual(tests_hit(run("hist.json", json.dumps({"pts": pts}))), [])
