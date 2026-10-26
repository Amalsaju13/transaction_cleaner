# Line-by-line / block-by-block code walkthrough

This guide follows `transaction_cleaner.py` from top to bottom. Blank lines only separate logical sections.

## 1. Interpreter line and module description

- `#!/usr/bin/env python3`: on Unix-like systems, lets the file run with Python 3 when marked executable.
- The triple-quoted string is a module docstring: a short description of the program.

## 2. Imports

- `argparse`: reads command-line options such as the input path and output paths.
- `csv`: safely reads/writes CSV, including quoted values like `"1,470.00"`.
- `json`: writes the machine-readable report.
- `re`: validates comma-grouped numeric strings and strips currency symbols.
- `Counter`: counts normalized statuses.
- `defaultdict`: groups records by transaction ID and duplicate fingerprint without manually creating each list.
- `datetime`: validates dates and converts them to ISO format.
- `Decimal` and `InvalidOperation`: handle monetary values accurately and catch invalid numeric text.

## 3. Constants

- `VALID_STATUSES` is the exact accepted business status set.
- `DATE_FORMATS` lists accepted date layouts. `strptime` validates both layout and calendar date.
- `REQUIRED_COLUMNS` ensures the input file contains every field the program needs before processing starts.

## 4. `normalize_name(value)`

- `(value or "")` turns `None` into an empty string so missing cells do not crash the program.
- `.split()` separates on any whitespace and also collapses repeated spaces/tabs/newlines.
- `" ".join(...)` rejoins the parts with one ordinary space.
- `.title()` makes capitalization consistent.
- The original name is stored separately, so normalization does not destroy the input value.

Example: `" priya   menon "` becomes `"Priya Menon"`.

## 5. `parse_date(value)`

- Strip surrounding whitespace.
- Try each known format in order.
- `datetime.strptime(value, date_format)` parses and validates the date.
- `.date().isoformat()` emits `YYYY-MM-DD`.
- `except ValueError: continue` means one failed format does not stop the remaining formats being tried.
- `return None` means no format accepted the value; the caller then flags it as invalid.

The slash date rule is an explicit assumption: `03/09/2026` means 3 September 2026, not March 9.

## 6. `parse_amount(value)`

- Strip whitespace and reject empty cells or placeholders such as `N/A`.
- `re.sub(...)` removes common currency symbols; this does not perform currency conversion.
- If commas appear, `re.fullmatch(...)` checks that they follow thousands grouping, e.g. `1,470.00`. `1,47,0` is rejected rather than guessed.
- Commas are removed after validation, making `1,470.00` become `1470.00`.
- `Decimal(cleaned)` converts the string without introducing binary floating-point rounding.
- `InvalidOperation` catches strings such as `oops`.
- `.is_finite()` rejects `NaN` and infinity.
- `amount < 0` rejects negative values. Zero is deliberately allowed.
- `.quantize(Decimal("0.01"))` standardizes output to two decimal places.
- `None` signals an invalid amount to the caller.

## 7. `clean_status(value)`

- Strip spaces and apply `.casefold()` for case-insensitive matching.
- Return the lowercase status if it is in `VALID_STATUSES`.
- Otherwise return `unknown`, which the main function records as an issue.

## 8. `main()` — command-line options

- `ArgumentParser(...)` creates the command-line interface.
- `input` is optional and defaults to `input.csv`.
- `--cleaned` defaults to `cleaned.csv`.
- `--report` defaults to `report.json`.
- `parse_args()` reads the actual values supplied by the user.

## 9. Reading and validating the input

- `open(..., newline="", encoding="utf-8-sig")` handles CSV newlines and a possible UTF-8 byte-order mark.
- `csv.DictReader` maps each row into a dictionary keyed by the header names.
- If no header exists, the program stops with a clear error.
- `REQUIRED_COLUMNS - set(reader.fieldnames)` finds missing required headers.
- If required columns are missing, the program stops rather than silently producing misleading output.
- `list(reader)` loads rows because duplicate detection requires comparing records across the whole file.

## 10. First pass — normalize each row and collect duplicates

- `cleaned_rows` stores processed row dictionaries.
- `transaction_id_rows` groups all records sharing the same transaction ID.
- `fingerprint_rows` groups records whose normalized details suggest the same real-world transaction.
- `enumerate(input_rows, start=2)` tracks source line numbers; line 1 is the header.
- `raw.get(...)` safely reads fields.
- The original customer name is retained; a separate normalized name is created.
- IDs are stripped of surrounding spaces.
- `parse_amount`, `parse_date`, and `clean_status` apply the dedicated parsing rules.
- `issues` starts as an empty list, then gets one code for each failed check. Because it is a list, one row can carry several issue codes.
- Missing ID and customer name are checked explicitly.
- Invalid amount/date and unknown status are each checked independently.

### Duplicate fingerprint

The fingerprint contains:
1. normalized customer name, case-insensitive;
2. parsed amount;
3. normalized ISO date;
4. order ID, case-insensitive;
5. normalized status.

Transaction ID is intentionally not included, because this check looks for matching real-world details even when IDs differ. Rows with missing required fingerprint fields do not enter probable-duplicate matching.

- `record` is a dictionary containing both normalized values and flags used later.
- Each record is appended to `cleaned_rows`.
- Records with a non-empty ID are added to their ID group.
- Records with a complete fingerprint are added to their fingerprint group.

## 11. Second pass — repeated transaction IDs

- `duplicate_id_groups` counts groups with more than one row.
- `duplicate_id_rows` counts all rows inside those repeated-ID groups.
- For each group with length greater than one, every member is marked `duplicate_transaction_id = True` and gets the issue code `duplicate_transaction_id`.
- The program invalidates every row in a repeated-ID group because it cannot safely decide which ID-bearing record is correct.

## 12. Probable duplicate matching

- Each fingerprint group with more than one row is a probable duplicate group.
- `len(records) - 1` counts extra copies beyond the first record.
- `records[1:]` skips the first record and marks later matches as probable duplicates.
- A probable duplicate receives the `probable_duplicate_transaction` issue.
- This is a heuristic. The first row is the canonical record only for this automated process; business review may still be needed.

## 13. Validity and output formatting

- `is_valid` is true only when `issues` is empty.
- `issues_text` joins all issue codes with semicolons for a readable CSV cell.
- `amount_text` is blank when the amount could not be parsed; otherwise it is formatted to exactly two decimals.
- `output_columns` defines a stable, predictable output column order.
- `csv.DictWriter` handles quoting and commas correctly.
- The output loop writes exactly one output row per input row.
- Boolean values are written as lowercase `true`/`false`, which are easy to inspect and parse.

## 14. Report counts and revenue

- `valid_rows` and `invalid_rows` split all processed records by `is_valid`.
- `sum(..., Decimal("0.00"))` totals valid paid rows and valid refund rows using exact decimal arithmetic.
- Net revenue is paid total minus refund total. Pending, cancelled, unknown, and all invalid rows are excluded.
- `Counter` counts normalized statuses across all rows, including invalid rows.
- The report records input/valid/invalid counts and a reconciliation boolean.
- Duplicate counts distinguish groups from rows, avoiding confusion between “number of duplicate groups” and “number of affected rows”.
- `json.dump(..., indent=2)` writes readable JSON, and the final newline is conventional for text files.
- The three `print` calls give a short terminal summary after successful output generation.

## 15. Main guard

`if __name__ == "__main__":` calls `main()` only when the file is executed directly. If another Python file imports this module to reuse its functions, it will not automatically process a CSV.
