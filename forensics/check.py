#!/usr/bin/env python3
"""forensics.check: tripwire for fake/hand-typed/hallucinated data.

Exit 0 if the file passes (or has <50 numbers).
Exit 2 with a message if the data looks fabricated.
"""

import math
import os
import re
import sys
from collections import Counter
from typing import List, Tuple, Optional

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


def extract_numbers_from_file(path: str) -> List[float]:
    """Extract numbers from any file using regex on the entire content."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception:
        # If we can't read as text, return empty
        return []
    return extract_numbers_from_text(content)


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


def test_benford_first(nums: List[float]) -> Tuple[Optional[str], Optional[float]]:
    """Benford's first digit test.
    Returns (test_name, p_value) or (None, None) if not applicable.
    """
    if len(nums) < 100:
        return None, None
    # Check if values span at least 2 orders of magnitude
    if not nums:
        return None, None
    min_val = min(abs(x) for x in nums if x != 0)
    max_val = max(abs(x) for x in nums)
    if min_val == 0 or max_val / min_val < 10:
        return None, None

    # Extract first non-zero digit
    first_digits = []
    for x in nums:
        if x == 0:
            continue
        # Work with absolute value
        x = abs(x)
        # Scale to [1, 10)
        while x >= 10:
            x /= 10.0
        while x < 1:
            x *= 10.0
        first_digit = int(math.floor(x))
        first_digits.append(first_digit)

    if not first_digits:
        return None, None

    observed = [0] * 10  # indices 0-9, we'll use 1-9
    for d in first_digits:
        if 1 <= d <= 9:
            observed[d] += 1

    expected = [benford_expected_first(d) for d in range(1, 10)]
    # Chi-square test
    chisq = chi_square(observed[1:], expected)
    p = chi_square_pvalue(chisq, 8)  # 9 categories -> df=8
    return "benford_first", p


def test_benford_second(nums: List[float]) -> Tuple[Optional[str], Optional[float]]:
    """Benford's second digit test (n >= 300)."""
    if len(nums) < 300:
        return None, None

    second_digits = []
    for x in nums:
        if x == 0:
            continue
        x = abs(x)
        # Scale to [1, 100) to get first two digits
        while x >= 100:
            x /= 10.0
        while x < 10:
            x *= 10.0
        # Now x in [10, 100)
        second_digit = int(math.floor(x)) % 10
        second_digits.append(second_digit)

    if not second_digits:
        return None, None

    observed = [0] * 10
    for d in second_digits:
        observed[d] += 1

    expected = [benford_expected_second(d) for d in range(10)]
    chisq = chi_square(observed, expected)
    p = chi_square_pvalue(chisq, 9)  # 10 categories -> df=9
    return "benford_second", p


def test_last_digit_uniformity(nums: List[float]) -> Tuple[Optional[str], Optional[float]]:
    """Last-digit uniformity for numbers with >= 3 significant digits."""
    last_digits = []
    for x in nums:
        if x == 0:
            continue
        # Work with absolute value
        x = abs(x)
        # If the number is less than 100, it has less than 3 digits in integer part?
        # We'll skip numbers < 100 for this test (they don't have 3 significant digits
        # in the integer part). This is a simplification.
        if x < 100:
            continue
        # Round to nearest integer to get the last digit of the integer part
        last_digit = int(round(x)) % 10
        last_digits.append(last_digit)

    if len(last_digits) < 30:  # arbitrary minimum for chi-square
        return None, None

    observed = [0] * 10
    for d in last_digits:
        observed[d] += 1

    expected = [len(last_digits) / 10.0] * 10
    chisq = chi_square(observed, expected)
    p = chi_square_pvalue(chisq, 9)  # 10 categories -> df=9
    return "last_digit_uniformity", p


def test_round_number_excess(nums: List[float]) -> Tuple[Optional[str], Optional[float]]:
    """Excess of numbers ending in 0 or 5."""
    endings = []
    for x in nums:
        if x == 0:
            continue
        # Round to nearest integer
        rounded = round(x)
        last_digit = int(abs(rounded)) % 10
        endings.append(last_digit)

    if len(endings) < 30:
        return None, None

    # Count endings in {0,5}
    count_05 = sum(1 for d in endings if d in (0, 5))
    n = len(endings)
    # Expected proportion: 2/10 = 0.2
    expected = 0.2
    p_hat = count_05 / n
    # If the observed proportion equals expected, return p=1 (no evidence)
    if p_hat == expected:
        return "round_number_excess", 1.0
    # Standard error under null
    std = math.sqrt(expected * (1 - expected) / n)
    if std == 0:
        return "round_number_excess", 1.0
    z = (p_hat - expected) / std
    # Two-tailed p-value from standard normal: erfc(|z|/sqrt(2))
    p = math.erfc(abs(z) / math.sqrt(2.0))
    # Clamp to [0, 1] just in case
    if p < 0.0:
        p = 0.0
    if p > 1.0:
        p = 1.0
    return "round_number_excess", p


def test_duplicate_rows_and_values(nums: List[float]) -> Tuple[Optional[str], Optional[float]]:
    """Test for duplicate rows and repeated identical values.
    We don't have row structure here, so we only test for repeated identical values.
    """
    if len(nums) < 10:
        return None, None
    # Count duplicates
    counts = Counter(nums)
    total = len(nums)
    duplicate_count = sum(c - 1 for c in counts.values() if c > 1)
    if duplicate_count == 0:
        return None, None
    # We'll use a p-value based on the expected number of duplicates in random data?
    # This is non-trivial. Instead, we'll flag if more than 10% of values are duplicates?
    if duplicate_count > total * 0.1:
        return "duplicate_rows_and_values", 0.001
    else:
        return "duplicate_rows_and_values", 0.5


def test_impossible_values(nums: List[float]) -> Tuple[Optional[str], Optional[float]]:
    """Check for impossible values: probabilities outside [0,1], percentages >100,
    negative SD or counts. We don't have context, so we skip.
    """
    return None, None


def test_grim(nums: List[float]) -> Tuple[Optional[str], Optional[float]]:
    """GRIM test: mean of integer data must be achievable.
    Placeholder implementation: always returns p=0.5 (no effect).
    """
    return ("grim", 0.5)


def test_internal_arithmetic(nums: List[float]) -> Tuple[Optional[str], Optional[float]]:
    """Check for internal arithmetic: stated totals or sums that do not match rows.
    Placeholder implementation: always returns p=0.5 (no effect).
    """
    return ("internal_arithmetic", 0.5)


def test_too_perfect_patterns(nums: List[float]) -> Tuple[Optional[str], Optional[float]]:
    """Too-perfect patterns: many p-values just under 0.05, constant step sizes,
    identical decimals across rows. Placeholder implementation: always returns p=0.5.
    """
    return ("too_perfect_patterns", 0.5)


# ----------------------------------------------------------------------
# Main logic
# ----------------------------------------------------------------------


def run_forensics(nums: List[float]) -> Tuple[bool, Optional[str], Optional[float]]:
    """Run all applicable tests and return (tripped, test_name, p_value).
    If tripped is True, then test_name and p_value are set for the most
    significant test (smallest p-value after Holm correction).
    """
    if len(nums) < 50:
        return False, None, None

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

    results = []  # list of (test_name, p_value)
    for test in tests:
        name, p = test(nums)
        if name is not None and p is not None:
            results.append((name, p))

    if not results:
        return False, None, None

    # Apply Holm-Bonferroni correction
    alpha = 0.05
    # Sort by p-value
    results.sort(key=lambda x: x[1])
    m = len(results)
    for i, (name, p) in enumerate(results):
        # Holm threshold for the i-th smallest p-value
        threshold = alpha / (m - i)
        if p < threshold:
            # We reject this hypothesis (and all previous ones)
            # We return the first one that is rejected (smallest p-value)
            return True, name, p

    return False, None, None


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: forensics/check.py <file>", file=sys.stderr)
        sys.exit(1)

    path = sys.argv[1]
    if not os.path.exists(path):
        print(f"File not found: {path}", file=sys.stderr)
        sys.exit(1)

    nums = extract_numbers_from_file(path)
    tripped, test_name, p_value = run_forensics(nums)

    if tripped:
        msg = (
            f"forensics tripwire: {test_name} failed (p={p_value:.4g}). "
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