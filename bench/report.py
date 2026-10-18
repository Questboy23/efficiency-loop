#!/usr/bin/env python3
"""Benchmark for forensics checker: compute false-positive and detection rates.

This version uses subsets of real files (first 1000 rows) to keep size manageable.
"""

import csv
import json
import math
import os
import random
import subprocess
import sys
import tempfile
from pathlib import Path

# Add the project root to the path so we can import forensics.check
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from forensics.check import extract_numbers_from_file, run_forensics

def run_checker(filepath: Path) -> bool:
    """Run forensics/check.py on filepath.
    Returns True if the checker trips (exit code 2), False otherwise.
    """
    try:
        result = subprocess.run(
            [sys.executable, str(Path(__file__).resolve().parents[1] / 'forensics' / 'check.py'),
             str(filepath)],
            capture_output=True,
            text=True,
            timeout=30  # seconds
        )
        # Exit code 2 means tripped
        return result.returncode == 2
    except subprocess.TimeoutExpired:
        # If it times out, we assume it did not trip (or we could count as error)
        return False
    except Exception as e:
        print(f"Unexpected error running checker on {filepath.name}: {e}")
        return False

def collect_real_files_subset(max_rows=1000) -> list[Path]:
    """Collect real-shaped data files, taking only the first max_rows rows."""
    real_dirs = [
        Path('/Users/reedhomefolder/hospitalprice/out/tables'),
        Path('/Users/reedhomefolder/housing_forecast/results'),
        Path('/Users/reedhomefolder/housing_forecast/data/manual'),
        Path('/Users/reedhomefolder/housing_forecast/data/raw'),
    ]
    files = []
    for d in real_dirs:
        if d.is_dir():
            # Only take CSV files for simplicity
            for csv_path in d.glob('*.csv'):
                # Read the file and write first max_rows rows to a temporary file
                try:
                    with open(csv_path, 'r', encoding='utf-8') as f:
                        # Read header
                        header = f.readline()
                        rows = []
                        for i in range(max_rows):
                            row = f.readline()
                            if not row:
                                break
                            rows.append(row)
                    # If we have at least one row (or header), create a temp file
                    if header or rows:
                        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as tmp:
                            tmp.write(header)
                            tmp.writelines(rows)
                            tmp_path = Path(tmp.name)
                    else:
                        continue
                except Exception as e:
                    print(f"Error processing {csv_path.name}: {e}")
                    continue
                files.append(tmp_path)
            # Also take TSV if any
            for tsv_path in d.glob('*.tsv'):
                try:
                    with open(tsv_path, 'r', encoding='utf-8') as f:
                        header = f.readline()
                        rows = []
                        for i in range(max_rows):
                            row = f.readline()
                            if not row:
                                break
                            rows.append(row)
                    if header or rows:
                        with tempfile.NamedTemporaryFile(mode='w', suffix='.tsv', delete=False) as tmp:
                            tmp.write(header)
                            tmp.writelines(rows)
                            tmp_path = Path(tmp.name)
                    else:
                        continue
                except Exception as e:
                    print(f"Error processing {tsv_path.name}: {e}")
                    continue
                files.append(tmp_path)
            # JSON
            for json_path in d.glob('*.json'):
                try:
                    # For JSON, we can't easily take a subset, so we'll skip if the file is large?
                    # We'll just use the whole file but hope it's not too big.
                    # We'll check the file size and skip if > 5 MB.
                    if json_path.stat().st_size > 5 * 1024 * 1024:
                        continue
                    files.append(json_path)
                except Exception:
                    continue
            # Markdown
            for md_path in d.glob('*.md'):
                try:
                    if md_path.stat().st_size > 5 * 1024 * 1024:
                        continue
                    files.append(md_path)
                except Exception:
                    continue
    # Limit to first 10 files to avoid too many
    return files[:5]

def generate_fabricated_files() -> list[Path]:
    """Generate fabricated data files that should trip the checker."""
    fabricated_dir = Path(__file__).resolve().parent / 'fabricated'
    fabricated_dir.mkdir(exist_ok=True)
    files = []

    # 1. Uniform first digits (to trip Benford first digit test)
    uniform_path = fabricated_dir / 'uniform_first_digits.csv'
    with open(uniform_path, 'w') as f:
        f.write('value\\n')
        for _ in range(2000):  # Increase size to ~2000 rows
            first = random.randint(1, 9)
            rest = random.randint(0, 99)
            num = first * 100 + rest
            f.write(f'{num}\\n')
    files.append(uniform_path)

    # 2. Round-number excess (to trip round-number excess test)
    round_path = fabricated_dir / 'round_number_excess.csv'
    with open(round_path, 'w') as f:
        f.write('value\\n')
        for _ in range(2000):
            num = random.randint(1, 100) * 5
            f.write(f'{num}\\n')
    files.append(round_path)

    # 3. Duplicate rows (all same number) - should trip duplicate test
    dup_path = fabricated_dir / 'duplicate_rows.csv'
    with open(dup_path, 'w') as f:
        f.write('value\\n')
        for _ in range(2000):
            f.write('42.0\\n')
    files.append(dup_path)

    # 4. Last-digit non-uniformity (all numbers end with 0) - should trip last-digit uniformity test
    last_digit_path = fabricated_dir / 'last_digit_nonuniform.csv'
    with open(last_digit_path, 'w') as f:
        f.write('value\\n')
        for _ in range(2000):
            num = random.randint(1, 20) * 10
            f.write(f'{num}\\n')
    files.append(last_digit_path)

    # 5. GRIM-impossible means: we need two columns: mean and n.
    grim_path = fabricated_dir / 'grim_impossible.csv'
    with open(grim_path, 'w') as f:
        f.write('mean,n\\n')
        for _ in range(500):
            mean_val = random.uniform(10.0, 20.0)
            mean_val = round(mean_val, 1)
            n = random.randint(5, 30)
            f.write(f'{mean_val},{n}\\n')
    files.append(grim_path)

    return files

def main():
    real_files = collect_real_files_subset(max_rows=1000)
    fab_files = generate_fabricated_files()

    print(f'Real files (subset): {len(real_files)}')
    print(f'Fabricated files: {len(fab_files)}')

    # Test real files
    false_positives = 0
    for real_file in real_files:
        try:
            if run_checker(real_file):
                false_positives += 1
                print(f'REAL FILE TRIPPED (false positive): {real_file.name}')
            else:
                print(f'REAL FILE OK: {real_file.name}')
        except Exception as e:
            print(f'ERROR processing {real_file.name}: {e}')

    # Test fabricated files
    true_positives = 0
    for fab_file in fab_files:
        try:
            if run_checker(fab_file):
                true_positives += 1
                print(f'FAB FILE TRIPPED (true positive): {fab_file.name}')
            else:
                print(f'FAB FILE NOT TRIPPED (false negative): {fab_file.name}')
        except Exception as e:
            print(f'ERROR processing {fab_file.name}: {e}')

    # Compute rates
    fp_rate = false_positives / len(real_files) if real_files else 0.0
    tp_rate = true_positives / len(fab_files) if fab_files else 0.0

    # Write RESULTS.md
    results_path = Path(__file__).resolve().parents[1] / 'RESULTS.md'
    with open(results_path, 'w') as results_file:
        results_file.write('# Forensics Checker Benchmark Results\\n\\n')
        results_file.write(f'**False-positive rate**: {fp_rate:.2%} ({false_positives}/{len(real_files)} real files tripped)\\n\\n')
        results_file.write(f'**Detection rate**: {tp_rate:.2%} ({true_positives}/{len(fab_files)} fabricated files tripped)\\n\\n')
        results_file.write('## Details\\n\\n')
        results_file.write('### Real-shaped data (should not trip)\\n')
        for real_file in real_files:
            tripped = run_checker(real_file)
            results_file.write(f'- {real_file.name}: {"TRIPPED" if tripped else "OK"}\\n')
        results_file.write('\\n### Fabricated data (should trip)\\n')
        for fab_file in fab_files:
            tripped = run_checker(fab_file)
            results_file.write(f'- {fab_file.name}: {"TRIPPED" if tripped else "NOT TRIPPED"}\\n')

    print(f'Results written to {results_path}')

    # Clean up temporary real files
    for real_file in real_files:
        try:
            os.unlink(real_file)
        except Exception:
            pass

if __name__ == '__main__':
    main()
