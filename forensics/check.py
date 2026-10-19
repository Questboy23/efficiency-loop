#!/usr/bin/env python3
"""forensics.check: tripwire for fake/hand-typed/hallucinated data.

Exit 0 if the file passes (or has <50 numbers).
Exit 2 with a message if the data looks fabricated.
"""

import csv
import math
import os
import re
import sys
from collections import Counter
from typing import Dict, List, Tuple, Optional

# ----------------------------------------------------------------------
# Number extraction
# ----------------------------------------------------------------------


def extract_numbers_from_text(text: str) -> List[float]:
    """Extract all numbers from a string.
    Supports decimal, scientific notation, and numbers with commas.
    """
    # Regex for numbers: optional sign, digits with optional commas and decimal,
    # optional exponent.
    number_pattern = re.compile(
        r"""[-+]?                  # sign
            (?:                    # either
                \d{1,3}(?:,\d{3})* # digits with commas
                |                  # or
                \d+                # digits without commas
            )
            (?:                    # fractional part
                \.\d+
            )?                     # optional
            (?:                    # exponent part
                [eE][-+]?\d+
            )?                     # optional
        """,
        re.VERBOSE,
    )
    nums = []
    for match in number_pattern.finditer(text):
        s = match.group(0)
        # Remove commas
        s = s.replace(",", "")
        try:
            nums.append(float(s))
        except ValueError:
            pass
    return nums


def parse_csv_tsv(path: str, delimiter: str) -> Optional[Dict[str, List[float]]]:
    """Try to parse a CSV/TSV file into columns of numbers.
    Returns dict mapping header to list of floats, or None if parsing fails.
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            # Try to sniff dialect
            sample = f.read(1024)
            f.seek(0)
            if not sample:
                return None
            has_header = csv.Sniffer().has_header(sample)
            f.seek(0)
            reader = csv.reader(f, delimiter=delimiter)
            rows = list(reader)
    except Exception:
        return None

    if not rows:
        return None

    # Determine header
    if has_header and len(rows) >= 1:
        header_rows = [rows[0]]
        data_rows = rows[1:]
    else:
        # No header: generate generic names
        header_rows = [[f"col{i}" for i in range(len(rows[0]))] if rows else []]
        data_rows = rows

    if not header_rows or not header_rows[0]:
        return None

    headers = [h.strip() for h in header_rows[0]]
    n_cols = len(headers)
    # Initialize columns
    columns: Dict[str, List[float]] = {h: [] for h in headers}

    for row in data_rows:
        # If row length differs, pad or truncate
        if len(row) < n_cols:
            row += [""] * (n_cols - len(row))
        elif len(row) > n_cols:
            row = row[:n_cols]
        for i, cell in enumerate(row):
            cell = cell.strip()
            if cell == "":
                continue
            # Try to convert to float
            try:
                val = float(cell)
                columns[headers[i]].append(val)
            except ValueError:
                # Not a number, skip
                pass

    # Ensure all columns have same length (truncate to shortest)
    if columns:
        min_len = min(len(v) for v in columns.values())
        if min_len == 0:
            return None
        for h in headers:
            columns[h] = columns[h][:min_len]
        return columns
    return None


def extract_numbers_from_file(path: str) -> Dict[str, List[float]]:
    """Extract numbers from any file, returning dict of columns.
    For recognized tabular formats (CSV, TSV, Markdown tables) returns columns.
    For other files, returns a single column with key "_".
    """
    # Try CSV/TSV based on extension
    lower = path.lower()
    if lower.endswith(".csv"):
        cols = parse_csv_tsv(path, ",")
        if cols is not None:
            return cols
    if lower.endswith(".tsv"):
        cols = parse_csv_tsv(path, "\t")
        if cols is not None:
            return cols
    # Try markdown tables for .md files
    if lower.endswith(".md"):
        cols = parse_markdown_table(path)
        if cols is not None:
            return cols
    # Fallback: treat whole file as text, single column
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception:
        return {"_": []}
    nums = extract_numbers_from_text(content)
    if nums:
        return {"_": nums}
    return {"_": []}


def parse_markdown_table(path: str) -> Optional[Dict[str, List[float]]]:
    """Very simple markdown table parser: expects pipe-delimited with separator line of ---."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = [line.rstrip("\n") for line in f]
    except Exception:
        return None

    # Find a line that looks like a separator: contains at least three | and --- or ===
    sep_idx = -1
    for i, line in enumerate(lines):
        if "|" in line:
            # Check if next line is separator
            if i + 1 < len(lines) and re.match(r'^\s*\|?\s*[-:]+[-|:\s]*[-:]+\s*\|?\s*$', lines[i + 1]):
                sep_idx = i
                break
    if sep_idx == -1:
        return None

    header_line = lines[sep_idx]
    sep_line = lines[sep_idx + 1]
    data_lines = lines[sep_idx + 2 :]

    # Extract headers from header_line
    # Split by |, ignore empty first/last if due to leading/trailing |
    parts = [p.strip() for p in header_line.split("|")]
    # If first or last empty due to surrounding pipes, drop them
    if parts and parts[0] == "":
        parts = parts[1:]
    if parts and parts[-1] == "":
        parts = parts[:-1]
    if not parts:
        return None
    headers = parts
    n_cols = len(headers)

    columns: Dict[str, List[float]] = {h: [] for h in headers}

    for line in data_lines:
        if not line.strip():
            continue
        if "|" not in line:
            break  # stop at non-table line
        parts = [p.strip() for p in line.split("|")]
        if parts and parts[0] == "":
            parts = parts[1:]
        if parts and parts[-1] == "":
            parts = parts[:-1]
        if len(parts) < n_cols:
            parts += [""] * (n_cols - len(parts))
        elif len(parts) > n_cols:
            parts = parts[:n_cols]
        for i, cell in enumerate(parts):
            if cell == "":
                continue
            # Try to convert to float
            try:
                val = float(cell)
                columns[headers[i]].append(val)
            except ValueError:
                pass

    # Truncate to shortest column
    if columns:
        min_len = min(len(v) for v in columns.values())
        if min_len == 0:
            return None
        for h in headers:
            columns[h] = columns[h][:min_len]
        return columns
    return None


# ----------------------------------------------------------------------
# Statistical helpers
# ----------------------------------------------------------------------


def benford_expected_first(digit: int) -> float:
    """Probability of first digit d under Benford's law."""
    return math.log10(1 + 1 / digit)


def benford_expected_second(digit: int) -> float:
    """Probability of second digit d under Benford's law."""
    if digit < 0 or digit > 9:
        return 0.0
    total = 0.0
    for first in range(1, 10):
        total += math.log10(1 + 1 / (10 * first + digit))
    return total


def chi_square(observed: List[int], expected: List[float]) -> float:
    """Chi-square statistic."""
    if len(observed) != len(expected):
        raise ValueError("Length mismatch")
    total = 0.0
    for o, e in zip(observed, expected):
        if e == 0:
            continue
        total += (o - e) ** 2 / e
    return total


def chi_square_pvalue(chisq: float, df: int) -> float:
    """Approximate p-value for chi-square statistic with df degrees of freedom.
    Using the Wilson-Hilferty approximation for better accuracy.
    """
    if chisq <= 0 or df <= 0:
        return 1.0
    # Wilson-Hilferty: (chisq/df)^(1/3) is approximately normal
    # with mean 1 - 2/(9*df) and variance 2/(9*df)
    chisq_df = chisq / df
    if chisq_df == 0:
        return 1.0
    y = math.pow(chisq_df, 1.0 / 3.0)
    mu = 1 - 2.0 / (9.0 * df)
    sigma = math.sqrt(2.0 / (9.0 * df))
    z = (y - mu) / sigma
    # p-value for upper tail (we care about large chisq)
    return 0.5 * math.erfc(-z / math.sqrt(2.0))


def mad_observed_vs_expected(observed: List[int], expected: List[float]) -> float:
    """Mean absolute difference between observed proportions and expected."""
    total_obs = sum(observed)
    if total_obs == 0:
        return 0.0
    obs_prop = [o / total_obs for o in observed]
    return sum(abs(o - e) for o, e in zip(obs_prop, expected)) / len(obs_prop)


# ----------------------------------------------------------------------
# Individual tests
# ----------------------------------------------------------------------


def test_benford_first(columns: Dict[str, List[float]]) -> Tuple[Optional[str], Optional[float], Optional[str]]:
    """Benford's first digit test per column.
    Returns (test_name, p_value, column_name) or (None, None, None) if not applicable.
    """
    for col_name, nums in columns.items():
        if len(nums) < 100:
            continue
        # Check if values span at least 2 orders of magnitude
        positives = [x for x in nums if x != 0]
        if not positives:
            continue
        min_val = min(abs(x) for x in positives)
        max_val = max(abs(x) for x in positives)
        if min_val == 0 or max_val / min_val < 10:
            continue

        # Extract first non-zero digit
        first_digits = []
        for x in nums:
            if x == 0:
                continue
            x = abs(x)
            while x >= 10:
                x /= 10.0
            while x < 1:
                x *= 10.0
            first_digit = int(math.floor(x))
            first_digits.append(first_digit)

        if not first_digits:
            continue

        observed = [0] * 10  # indices 0-9, we'll use 1-9
        for d in first_digits:
            if 1 <= d <= 9:
                observed[d] += 1

        expected = [benford_expected_first(d) for d in range(1, 10)]
        chisq = chi_square(observed[1:], expected)
        p = chi_square_pvalue(chisq, 8)  # 9 categories -> df=8
        if p < 0.05:  # we'll let Holm correction decide later
            return "benford_first", p, col_name
    return None, None, None


def test_benford_second(columns: Dict[str, List[float]]) -> Tuple[Optional[str], Optional[float], Optional[str]]:
    """Benford's second digit test (n >= 300) per column."""
    for col_name, nums in columns.items():
        if len(nums) < 300:
            continue

        second_digits = []
        for x in nums:
            if x == 0:
                continue
            x = abs(x)
            while x >= 100:
                x /= 10.0
            while x < 10:
                x *= 10.0
            # Now x in [10, 100)
            second_digit = int(math.floor(x)) % 10
            second_digits.append(second_digit)

        if not second_digits:
            continue

        observed = [0] * 10
        for d in second_digits:
            observed[d] += 1

        expected = [benford_expected_second(d) for d in range(10)]
        chisq = chi_square(observed, expected)
        p = chi_square_pvalue(chisq, 9)  # 10 categories -> df=9
        if p < 0.05:
            return "benford_second", p, col_name
    return None, None, None


def test_last_digit_uniformity(columns: Dict[str, List[float]]) -> Tuple[Optional[str], Optional[float], Optional[str]]:
    """Last-digit uniformity for numbers with >= 3 significant digits per column."""
    for col_name, nums in columns.items():
        last_digits = []
        for x in nums:
            if x == 0:
                continue
            x = abs(x)
            if x < 100:  # less than 3 digits in integer part
                continue
            last_digit = int(round(x)) % 10
            last_digits.append(last_digit)

        if len(last_digits) < 30:
            continue

        observed = [0] * 10
        for d in last_digits:
            observed[d] += 1

        expected = [len(last_digits) / 10.0] * 10
        chisq = chi_square(observed, expected)
        p = chi_square_pvalue(chisq, 9)  # 10 categories -> df=9
        if p < 0.05:
            return "last_digit_uniformity", p, col_name
    return None, None, None


def test_round_number_excess(columns: Dict[str, List[float]]) -> Tuple[Optional[str], Optional[float], Optional[str]]:
    """Excess of numbers ending in 0 or 5 per column."""
    for col_name, nums in columns.items():
        endings = []
        for x in nums:
            if x == 0:
                continue
            rounded = round(x)
            last_digit = int(abs(rounded)) % 10
            endings.append(last_digit)

        if len(endings) < 30:
            continue

        # Count endings in {0,5}
        count_05 = sum(1 for d in endings if d in (0, 5))
        n = len(endings)
        # Expected proportion: 2/10 = 0.2
        expected = 0.2
        p_hat = count_05 / n
        # If the observed proportion equals expected, return p=1 (no evidence)
        if p_hat == expected:
            return "round_number_excess", 1.0, col_name
        # Standard error under null
        std = math.sqrt(expected * (1 - expected) / n)
        if std == 0:
            return "round_number_excess", 1.0, col_name
        z = (p_hat - expected) / std
        # Two-tailed p-value from standard normal: erfc(|z|/sqrt(2))
        p = math.erfc(abs(z) / math.sqrt(2.0))
        # Clamp to [0, 1] just in case
        if p < 0.0:
            p = 0.0
        if p > 1.0:
            p = 1.0
        if p < 0.05:
            return "round_number_excess", p, col_name
    return None, None, None


def test_duplicate_rows_and_values(columns: Dict[str, List[float]]) -> Tuple[Optional[str], Optional[float], Optional[str]]:
    """Test for duplicate rows and repeated identical values.
    We check for duplicate rows across columns (i.e., identical rows).
    """
    # Need to reconstruct rows
    if not columns:
        return None, None, None
    # Ensure all columns same length
    lengths = [len(v) for v in columns.values()]
    if not lengths:
        return None, None, None
    min_len = min(lengths)
    if min_len < 10:
        return None, None, None
    # Build rows as tuples of values per column in header order
    headers = list(columns.keys())
    rows = []
    for i in range(min_len):
        row = tuple(columns[h][i] for h in headers)
        rows.append(row)
    if not rows:
        return None, None, None
    # Count duplicate rows
    seen = {}
    dup_count = 0
    for row in rows:
        if row in seen:
            dup_count += 1
        else:
            seen[row] = 1
    if dup_count == 0:
        return None, None, None
    # If more than 10% of rows are duplicates, flag
    if dup_count > len(rows) * 0.1:
        return "duplicate_rows_and_values", 0.001, ", ".join(headers)
    else:
        return "duplicate_rows_and_values", 0.5, ", ".join(headers)


def test_impossible_values(columns: Dict[str, List[float]]) -> Tuple[Optional[str], Optional[float], Optional[str]]:
    """Check for impossible values: probabilities outside [0,1], percentages >100,
    negative SD or counts. Uses column headers to infer meaning.
    """
    impossible_found = False
    details = []
    for col_name, nums in columns.items():
        header_lower = col_name.lower()
        # Determine constraints
        min_allowed = None
        max_allowed = None
        must_be_int = False
        if any(word in header_lower for word in ("prob", "p-value", "p value")):
            min_allowed = 0.0
            max_allowed = 1.0
        elif "%" in header_lower or "percent" in header_lower:
            min_allowed = 0.0
            max_allowed = 100.0
        elif any(word in header_lower for word in ("sd", "std", "standard error", "stderr")):
            min_allowed = 0.0
            # max unbounded
        elif any(word in header_lower for word in ("count", "n", "number", "sample size")):
            min_allowed = 0.0
            must_be_int = True
        # If no constraints, skip
        if min_allowed is None and not must_be_int:
            continue
        bad_vals = []
        for val in nums:
            if min_allowed is not None and val < min_allowed:
                bad_vals.append(val)
            elif max_allowed is not None and val > max_allowed:
                bad_vals.append(val)
            elif must_be_int and not float(val).is_integer():
                bad_vals.append(val)
        if bad_vals:
            impossible_found = True
            details.append(f"{col_name}: {len(bad_vals)} impossible values (e.g., {bad_vals[0]})")
    if impossible_found:
        # Return a low p-value to indicate failure
        return "impossible_values", 0.001, "; ".join(details)
    return None, None, None


def test_grim(columns: Dict[str, List[float]]) -> Tuple[Optional[str], Optional[float], Optional[str]]:
    """GRIM test: mean of integer data must be achievable.
    Look for columns named 'mean' and 'n' (or 'sample size').
    For each row, mean * n should be close to an integer (within rounding).
    """
    # Find mean column and n column
    mean_col = None
    n_col = None
    for col_name in columns.keys():
        lower = col_name.lower()
        if "mean" in lower:
            mean_col = col_name
        if ("n" in lower and len(lower) == 1) or "sample size" in lower or ("n" in lower and "size" in lower):
            n_col = col_name
    if mean_col is None or n_col is None:
        return None, None, None
    mean_vals = columns[mean_col]
    n_vals = columns[n_col]
    # Ensure same length
    length = min(len(mean_vals), len(n_vals))
    if length < 10:
        return None, None, None
    # Check each row
    inconsistent = 0
    for i in range(length):
        m = mean_vals[i]
        n = n_vals[i]
        if n <= 0:
            continue
        product = m * n
        # Allow small tolerance due to floating point
        nearest_int = round(product)
        if abs(product - nearest_int) > 1e-9:
            inconsistent += 1
    if inconsistent == 0:
        return None, None, None
    # If more than 10% of rows inconsistent, flag
    if inconsistent > length * 0.1:
        return "grim", 0.001, f"mean column '{mean_col}', n column '{n_col}'"
    else:
        return "grim", 0.5, f"mean column '{mean_col}', n column '{n_col}'"


def test_internal_arithmetic(columns: Dict[str, List[float]]) -> Tuple[Optional[str], Optional[float], Optional[str]]:
    """Check for internal arithmetic: stated totals or sums that do not match rows.
    Look for columns labeled 'total' or 'sum'.
    For each row, the total should equal sum of other numeric columns.
    """
    total_cols = []
    for col_name in columns.keys():
        lower = col_name.lower()
        if "total" in lower or "sum" in lower:
            total_cols.append(col_name)
    if not total_cols:
        return None, None, None
    # We'll use the first total column found
    total_col = total_cols[0]
    total_vals = columns[total_col]
    # Determine other columns (exclude total column)
    other_cols = [h for h in columns.keys() if h != total_col]
    if not other_cols:
        return None, None, None
    # Ensure same length
    length = min(len(total_vals), *[len(columns[h]) for h in other_cols])
    if length < 10:
        return None, None, None
    inconsistent = 0
    details = []
    for i in range(length):
        total = total_vals[i]
        # Sum other columns
        row_sum = 0.0
        for h in other_cols:
            val = columns[h][i]
            row_sum += val
        if abs(total - row_sum) > 1e-9 * max(1.0, abs(total)):
            inconsistent += 1
            if len(details) < 2:
                details.append(f"row {i}: total={total}, sum={row_sum}")
    if inconsistent == 0:
        return None, None, None
    if inconsistent > length * 0.1:
        return "internal_arithmetic", 0.001, f"total column '{total_col}'; " + "; ".join(details)
    else:
        return "internal_arithmetic", 0.5, f"total column '{total_col}'; " + "; ".join(details)


def test_too_perfect_patterns(columns: Dict[str, List[float]]) -> Tuple[Optional[str], Optional[float], Optional[str]]:
    """Too-perfect patterns: many p-values just under 0.05, constant step sizes,
    identical decimals across rows.
    """
    # Check for p-value columns
    p_cols = []
    for col_name in columns.keys():
        lower = col_name.lower()
        if "p" in lower and ("value" in lower or lower == "p" or lower.endswith("_p")):
            p_cols.append(col_name)
    # If no p-cols, check any column for constant step or identical decimals
    for col_name, nums in columns.items():
        if len(nums) < 10:
            continue
        # 1. Many values just under 0.05 (if column looks like p-values)
        header_lower = col_name.lower()
        if any(word in header_lower for word in ("p", "p-value", "p value")):
            near_threshold = [v for v in nums if 0.045 <= v < 0.05]
            if len(near_threshold) > len(nums) * 0.5:  # more than half just under 0.05
                return "too_perfect_patterns", 0.001, f"column '{col_name}': {len(near_threshold)} values in [0.045,0.05)"
        # 2. Constant step sizes (check differences between consecutive sorted values)
        sorted_nums = sorted(nums)
        if len(sorted_nums) >= 3:
            diffs = [sorted_nums[i+1] - sorted_nums[i] for i in range(len(sorted_nums)-1)]
            # If all differences are nearly equal (within tolerance)
            if len(diffs) > 0:
                avg_diff = sum(diffs) / len(diffs)
                if avg_diff != 0:
                    # compute relative std dev
                    variance = sum((d - avg_diff) ** 2 for d in diffs) / len(diffs)
                    std_dev = math.sqrt(variance)
                    if std_dev / avg_diff < 0.01:  # relative std dev < 1%
                        return "too_perfect_patterns", 0.001, f"column '{col_name}': constant step size {avg_diff:.6f}"
        # 3. Identical decimals across rows: check if fractional part is constant
        # Multiply by 1000 and look at last 3 decimal digits? Simpler: check if rounding to 2 decimal places yields same value for all?
        rounded = [round(v, 2) for v in nums]
        if len(set(rounded)) == 1 and len(nums) > 5:
            return "too_perfect_patterns", 0.001, f"column '{col_name}': identical decimals (rounded to 2 places) across rows"
    return None, None, None


# ----------------------------------------------------------------------
# Main logic
# ----------------------------------------------------------------------


def run_forensics(columns: Dict[str, List[float]]) -> Tuple[bool, Optional[str], Optional[float], Optional[str]]:
    """Run all applicable tests per column and return (tripped, test_name, p_value, column_related).
    If tripped is True, then test_name, p_value, column_related are set for the most
    significant test (smallest p-value after Holm correction).
    """
    total_numbers = sum(len(v) for v in columns.values())
    if total_numbers < 50:
        return False, None, None, None

    tests = [
        test_benford_first,
        test_benford_second,
        test_last_digit_uniformity,
        test_round_number_excess,
        test_duplicate_rows_and_values,
        test_impossible_values,
        test_grim,
        test_internal_arithmetic,
        test_too_perfect_patterns,
    ]

    results = []  # list of (test_name, p_value, column_related)
    for test in tests:
        name, p, col_related = test(columns)
        if name is not None and p is not None:
            results.append((name, p, col_related))

    if not results:
        return False, None, None, None

    # Apply Holm-Bonferroni correction
    alpha = 0.05
    # Sort by p-value
    results.sort(key=lambda x: x[1])
    m = len(results)
    for i, (name, p, col_related) in enumerate(results):
        # Holm threshold for the i-th smallest p-value
        threshold = alpha / (m - i)
        if p < threshold:
            # We reject this hypothesis (and all previous ones)
            # We return the first one that is rejected (smallest p-value)
            return True, name, p, col_related

    return False, None, None, None


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: forensics/check.py <file>", file=sys.stderr)
        sys.exit(1)

    path = sys.argv[1]
    if not os.path.exists(path):
        print(f"File not found: {path}", file=sys.stderr)
        sys.exit(1)

    columns = extract_numbers_from_file(path)
    tripped, test_name, p_value, col_related = run_forensics(columns)

    if tripped:
        col_msg = f" in column '{col_related}'" if col_related else ""
        msg = (
            f"forensics tripwire: {test_name} failed (p={p_value:.4g}){col_msg}. "
            "Do not hand-edit these numbers. Find where they came from, "
            "regenerate them with code from the real source, or label them "
            "clearly as illustrative. Then rerun forensics."
        )
        print(msg, file=sys.stderr)
        sys.exit(2)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()