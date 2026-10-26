#!/usr/bin/env python3
"""Clean messy transaction CSV data using only the Python standard library."""

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation


VALID_STATUSES = {"paid", "pending", "cancelled", "refund"}
DATE_FORMATS = (
    "%Y-%m-%d",  # 2026-09-03
    "%Y/%m/%d",  # 2026/09/03 (year first is unambiguous)
    "%d-%m-%Y",  # 03-09-2026 (day first)
    "%d/%m/%Y",  # 03/09/2026 (assumed day first; see README)
)
REQUIRED_COLUMNS = {
    "transaction_id", "customer_name", "amount", "transaction_date", "status", "order_id"
}


def normalize_name(value):
    """Return a comparison/display form while preserving the raw input elsewhere."""
    # Collapse repeated whitespace, trim the ends, and make capitalization consistent.
    return " ".join((value or "").split()).title()


def parse_date(value):
    """Parse only explicitly supported formats; return ISO date or None."""
    value = (value or "").strip()
    for date_format in DATE_FORMATS:
        try:
            return datetime.strptime(value, date_format).date().isoformat()
        except ValueError:
            continue
    return None


def parse_amount(value):
    """Convert common numeric strings to Decimal; invalid or negative amounts fail."""
    raw = (value or "").strip()
    if not raw or raw.casefold() in {"n/a", "na", "null", "none"}:
        return None

    # Remove common currency symbols and surrounding whitespace.
    cleaned = re.sub(r"[₹$€£]", "", raw).strip()
    # Accept comma grouping such as 1,470.00, but reject malformed grouping.
    if "," in cleaned:
        if not re.fullmatch(r"[+-]?\d{1,3}(,\d{3})+(\.\d+)?", cleaned):
            return None
        cleaned = cleaned.replace(",", "")

    # Decimal avoids binary floating-point rounding for money.
    try:
        amount = Decimal(cleaned)
    except InvalidOperation:
        return None

    if not amount.is_finite() or amount < 0:
        return None
    return amount.quantize(Decimal("0.01"))


def clean_status(value):
    """Normalize known statuses; unknown values become 'unknown' and cause an issue."""
    status = (value or "").strip().casefold()
    if status in VALID_STATUSES:
        return status
    return "unknown"


def main():
    parser = argparse.ArgumentParser(
        description="Clean transaction CSV data and create cleaned.csv and report.json."
    )
    parser.add_argument("input", nargs="?", default="input.csv",
                        help="input CSV path (default: input.csv)")
    parser.add_argument("--cleaned", default="cleaned.csv",
                        help="output CSV path (default: cleaned.csv)")
    parser.add_argument("--report", default="report.json",
                        help="output JSON path (default: report.json)")
    args = parser.parse_args()

    # Read the whole input so duplicate groups can be detected across all rows.
    with open(args.input, "r", newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)
        if reader.fieldnames is None:
            raise SystemExit("Input CSV is empty or has no header.")
        missing_columns = REQUIRED_COLUMNS - set(reader.fieldnames)
        if missing_columns:
            raise SystemExit("Missing required columns: " + ", ".join(sorted(missing_columns)))
        input_rows = list(reader)

    cleaned_rows = []
    transaction_id_rows = defaultdict(list)
    fingerprint_rows = defaultdict(list)

    # First pass: normalize fields and collect candidate duplicate groups.
    for row_number, raw in enumerate(input_rows, start=2):
        original_name = raw.get("customer_name", "")
        normalized_name = normalize_name(original_name)
        transaction_id = (raw.get("transaction_id") or "").strip()
        order_id = (raw.get("order_id") or "").strip()
        amount = parse_amount(raw.get("amount"))
        normalized_date = parse_date(raw.get("transaction_date"))
        status = clean_status(raw.get("status"))

        issues = []
        if not transaction_id:
            issues.append("missing_transaction_id")
        if not normalized_name:
            issues.append("missing_customer_name")
        if amount is None:
            issues.append("invalid_amount")
        if normalized_date is None:
            issues.append("invalid_or_unrecognized_date")
        if status == "unknown":
            issues.append("unknown_status")

        # A fingerprint ignores transaction ID and raw formatting. It is a candidate
        # duplicate when customer, amount, date, and order ID all match.
        fingerprint = None
        if normalized_name and amount is not None and normalized_date and order_id:
            fingerprint = (
                normalized_name.casefold(), str(amount), normalized_date, order_id.casefold(), status
            )

        record = {
            "source_row": row_number,
            "transaction_id": transaction_id,
            "customer_name_original": original_name,
            "customer_name_normalized": normalized_name,
            "amount": amount,
            "transaction_date": normalized_date or "",
            "status": status,
            "order_id": order_id,
            "issues": issues,
            "fingerprint": fingerprint,
            "duplicate_transaction_id": False,
            "probable_duplicate": False,
        }
        cleaned_rows.append(record)
        if transaction_id:
            transaction_id_rows[transaction_id].append(record)
        if fingerprint:
            fingerprint_rows[fingerprint].append(record)

    # Second pass: repeated IDs make every member of that ID group untrustworthy.
    duplicate_id_groups = 0
    duplicate_id_rows = 0
    for records in transaction_id_rows.values():
        if len(records) > 1:
            duplicate_id_groups += 1
            duplicate_id_rows += len(records)
            for record in records:
                record["duplicate_transaction_id"] = True
                record["issues"].append("duplicate_transaction_id")

    # Similar real-world duplicates: keep the first fingerprint occurrence as canonical;
    # flag subsequent occurrences. Rows with repeated IDs are counted separately too.
    probable_duplicate_groups = 0
    probable_duplicate_rows = 0
    for records in fingerprint_rows.values():
        if len(records) > 1:
            probable_duplicate_groups += 1
            probable_duplicate_rows += len(records) - 1
            for record in records[1:]:
                record["probable_duplicate"] = True
                record["issues"].append("probable_duplicate_transaction")

    # A row is valid only if it has no data-quality issues and is not a duplicate.
    for record in cleaned_rows:
        record["is_valid"] = not record["issues"]
        record["issues_text"] = ";".join(record["issues"])
        record["amount_text"] = "" if record["amount"] is None else format(record["amount"], ".2f")

    # Write one output record for every input row, preserving the raw customer name.
    output_columns = [
        "source_row", "transaction_id", "customer_name_original",
        "customer_name_normalized", "amount", "transaction_date", "status", "order_id",
        "is_valid", "issues"
    ]
    with open(args.cleaned, "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=output_columns)
        writer.writeheader()
        for record in cleaned_rows:
            writer.writerow({
                "source_row": record["source_row"],
                "transaction_id": record["transaction_id"],
                "customer_name_original": record["customer_name_original"],
                "customer_name_normalized": record["customer_name_normalized"],
                "amount": record["amount_text"],
                "transaction_date": record["transaction_date"],
                "status": record["status"],
                "order_id": record["order_id"],
                "is_valid": str(record["is_valid"]).lower(),
                "issues": record["issues_text"],
            })

    valid_rows = [record for record in cleaned_rows if record["is_valid"]]
    invalid_rows = [record for record in cleaned_rows if not record["is_valid"]]

    # Net revenue is paid amounts minus refunds, using valid rows only.
    paid_total = sum(
        (record["amount"] for record in valid_rows if record["status"] == "paid"),
        Decimal("0.00")
    )
    refund_total = sum(
        (record["amount"] for record in valid_rows if record["status"] == "refund"),
        Decimal("0.00")
    )
    net_revenue = paid_total - refund_total

    status_counts = Counter(record["status"] for record in cleaned_rows)
    report = {
        "input_rows": len(input_rows),
        "valid_rows": len(valid_rows),
        "invalid_rows": len(invalid_rows),
        "row_count_reconciles": len(input_rows) == len(valid_rows) + len(invalid_rows),
        "duplicate_counts": {
            "repeated_transaction_id_groups": duplicate_id_groups,
            "rows_with_repeated_transaction_id": duplicate_id_rows,
            "probable_duplicate_groups": probable_duplicate_groups,
            "probable_duplicate_extra_rows": probable_duplicate_rows,
        },
        "status_counts": dict(sorted(status_counts.items())),
        "revenue": {
            "definition": "valid paid amounts minus valid refund amounts; pending/cancelled/unknown excluded",
            "valid_paid_total": format(paid_total, ".2f"),
            "valid_refund_total": format(refund_total, ".2f"),
            "net_revenue": format(net_revenue, ".2f"),
        },
        "assumptions": [
            "Slash dates in DD/MM/YYYY format are interpreted day-first.",
            "Amounts must be non-negative numeric values; zero is allowed.",
            "Unknown statuses are normalized to 'unknown' and invalidate the row.",
            "Every row with a repeated transaction ID is invalidated.",
            "For probable duplicates, the first matching fingerprint is retained and later matches are invalidated.",
        ],
    }
    with open(args.report, "w", encoding="utf-8") as file:
        json.dump(report, file, indent=2, ensure_ascii=False)
        file.write("\n")

    print(f"Read {len(input_rows)} rows.")
    print(f"Valid: {len(valid_rows)} | Invalid: {len(invalid_rows)}")
    print(f"Net revenue: {format(net_revenue, '.2f')}")
    print(f"Wrote {args.cleaned} and {args.report}.")


if __name__ == "__main__":
    main()
