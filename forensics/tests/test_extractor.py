import unittest
import tempfile
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from forensics.check import extract_numbers_from_file

class TestExtractor(unittest.TestCase):
    def test_extract_numbers_from_csv(self):
        csv_data = "a,b,c\\n1,2.5,foo\\n3,bar,4.5"
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write(csv_data)
            fname = f.name
        try:
            numbers = extract_numbers_from_file(fname)
            # Expect numbers: 1, 2.5, 3, 4.5
            self.assertEqual(len(numbers), 4)
            self.assertAlmostEqual(numbers[0], 1.0)
            self.assertAlmostEqual(numbers[1], 2.5)
            self.assertAlmostEqual(numbers[2], 3.0)
            self.assertAlmostEqual(numbers[3], 4.5)
        finally:
            os.unlink(fname)

    def test_extract_numbers_from_tsv(self):
        tsv_data = "a\tb\tc\\n1\t2.5\tfoo\\n3\tbar\t4.5"
        with tempfile.NamedTemporaryFile(mode='w', suffix='.tsv', delete=False) as f:
            f.write(tsv_data)
            fname = f.name
        try:
            numbers = extract_numbers_from_file(fname)
            # Expect numbers: 1, 2.5, 3, 4.5
            self.assertEqual(len(numbers), 4)
            self.assertAlmostEqual(numbers[0], 1.0)
            self.assertAlmostEqual(numbers[1], 2.5)
            self.assertAlmostEqual(numbers[2], 3.0)
            self.assertAlmostEqual(numbers[3], 4.5)
        finally:
            os.unlink(fname)

    def test_extract_numbers_from_markdown_table(self):
        md = "| a | b |\n|---|---|\n| 1 | 2.5 |\n| 3 | 4.5 |"
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write(md)
            fname = f.name
        try:
            numbers = extract_numbers_from_file(fname)
            # Expect numbers: 1, 2.5, 3, 4.5
            self.assertEqual(len(numbers), 4)
            self.assertAlmostEqual(numbers[0], 1.0)
            self.assertAlmostEqual(numbers[1], 2.5)
            self.assertAlmostEqual(numbers[2], 3.0)
            self.assertAlmostEqual(numbers[3], 4.5)
        finally:
            os.unlink(fname)

    def test_extract_numbers_from_json(self):
        json_data = '{"a": 1, "b": [2.5, "foo"], "c": {"d": 3}}'
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write(json_data)
            fname = f.name
        try:
            numbers = extract_numbers_from_file(fname)
            # Expect numbers: 1, 2.5, 3
            self.assertEqual(len(numbers), 3)
            self.assertAlmostEqual(numbers[0], 1.0)
            self.assertAlmostEqual(numbers[1], 2.5)
            self.assertAlmostEqual(numbers[2], 3.0)
        finally:
            os.unlink(fname)

    def test_extract_numbers_from_text(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("The price is $12.99 and the quantity is 3.")
            fname = f.name
        try:
            numbers = extract_numbers_from_file(fname)
            # Expect numbers: 12.99, 3
            self.assertEqual(len(numbers), 2)
            self.assertAlmostEqual(numbers[0], 12.99)
            self.assertAlmostEqual(numbers[1], 3.0)
        finally:
            os.unlink(fname)

if __name__ == '__main__':
    unittest.main()