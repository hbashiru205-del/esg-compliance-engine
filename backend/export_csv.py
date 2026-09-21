"""CSV export: one row per question/answer pair."""
import csv
import io

_FORMULA = ("=", "+", "-", "@", "\t", "\r")


def _cell(value) -> str:
    """Stop spreadsheet apps from running a cell that starts like a formula."""
    text = "" if value is None else str(value)
    return "'" + text if text.startswith(_FORMULA) else text


def build_csv(pairs) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["#", "Question", "Answer", "Cited sources"])
    for n, p in enumerate(pairs, 1):
        w.writerow([n, _cell(p["question"]), _cell(p["answer"]),
                    _cell("; ".join(p.get("citations") or []))])
    # BOM so Excel reads accents and symbols as UTF-8.
    return ("\ufeff" + buf.getvalue()).encode("utf-8")
