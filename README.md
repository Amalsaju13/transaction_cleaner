# Messy Transactions — CSV Cleaner

## Requirements
- Python 3.9 or newer (the program uses only the Python standard library).
- No `pip install` commands or third-party packages are required.

## Files
- `transaction_cleaner.py`: complete program.
- `input.csv`: input data file (use the provided CSV).
- `cleaned.csv`: generated normalized data, one output row per input row.
- `report.json`: generated reconciliation and revenue report.

## Run

Put `transaction_cleaner.py` and `input.csv` in the same folder, then run:

```bash
python transaction_cleaner.py
```

If your input has another path/name:

```bash
python transaction_cleaner.py path/to/input.csv
```

Optional output paths:

```bash
python transaction_cleaner.py input.csv --cleaned cleaned.csv --report report.json
```

On Windows, `py transaction_cleaner.py` can be used if `python` is not the command registered on your system.

## What the program does

1. **Names:** keeps `customer_name_original` exactly as supplied by the CSV field, and creates `customer_name_normalized` by trimming leading/trailing whitespace, collapsing repeated whitespace, and applying title case. Thus `" priya   menon "` becomes `Priya Menon`. This is a matching aid, not proof that two names belong to the same person.
2. **Dates:** emits valid dates as ISO `YYYY-MM-DD`. It supports `YYYY-MM-DD`, `YYYY/MM/DD`, `DD-MM-YYYY`, and `DD/MM/YYYY`. Invalid calendar dates and unrecognized strings become blank and add `invalid_or_unrecognized_date`.
3. **Amounts:** uses `Decimal` to avoid binary floating-point money errors. It accepts values such as `1470`, `1,470.00`, and values prefixed by common symbols (`₹`, `$`, `€`, `£`). It rejects blank, `N/A`, malformed comma grouping, non-numeric text, non-finite values, and negative values. Zero is allowed. Invalid amounts are blank in `cleaned.csv`.
4. **Statuses:** strips whitespace and lowercases the four known values: `paid`, `pending`, `cancelled`, `refund`. Anything else becomes `unknown` and invalidates the row.
5. **Validity:** every input row is emitted. `is_valid` is `true` only if no issue was found. `issues` contains semicolon-separated issue codes; multiple issues can be recorded for one row.
6. **Duplicates:** every row in a repeated non-empty transaction-ID group receives `duplicate_transaction_id` and is invalid. A probable duplicate is detected using normalized customer name, amount, normalized date, order ID, and status. The first matching fingerprint is treated as canonical; later matches receive `probable_duplicate_transaction` and are invalid. Transaction-ID duplicates and probable duplicates are reported separately, and a row can be in both categories.

## Report definitions and reconciliation

- `input_rows` is the number of data records read, excluding the header.
- `valid_rows + invalid_rows` must equal `input_rows`; `row_count_reconciles` reports this check.
- Duplicate group counts count groups, while duplicate row counts count rows or extra repeated rows as their names specify.
- `net_revenue` = sum of amounts from valid `paid` rows minus amounts from valid `refund` rows. `pending`, `cancelled`, and `unknown` statuses are excluded. Invalid rows are excluded from revenue to avoid trusting questionable records.
- The `status_counts` values describe normalized statuses across all rows, including invalid rows.

## Assumptions and limitations

- **Slash dates:** `DD/MM/YYYY` is assumed for slash-separated dates such as `03/09/2026`. This is a deliberate dataset-level assumption because `03/09/2026` alone is ambiguous between March 9 and September 3. If the source system's locale is not known, a stricter policy would mark such ambiguous dates invalid instead.
- **Name normalization:** title case and whitespace cleanup do not resolve spelling variations, initials, or different people with the same name.
- **Probable duplicates:** the fingerprint is a heuristic, not a guarantee. Matching fields may occasionally represent a legitimate repeat purchase; different values may also hide a duplicate.
- **Amounts:** currency symbols are removed but no currency conversion is performed. All values are assumed to be in the same currency.
- **Duplicate IDs:** all records sharing an ID are invalidated because the program cannot confidently determine which record is correct.

## Edge case tested

The supplied dataset contains `TX0066` with amount `oops`. The amount parser rejects it without crashing, writes a blank normalized amount, marks the row invalid, and includes `invalid_amount` in its issue list. The dataset also includes a negative amount and an impossible date (`2026-15-08`), which are rejected independently.
