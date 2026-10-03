import csv
import io

from fastapi import HTTPException, UploadFile, status

from app.config import settings


def read_upload(file: UploadFile, allowed_ext: tuple[str, ...]) -> str:
    name = (file.filename or "").lower()
    if not name.endswith(allowed_ext):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Expected a {' or '.join(allowed_ext)} file")
    limit = settings.max_upload_mb * 1024 * 1024
    data = file.file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, f"File is over {settings.max_upload_mb} MB")
    try:
        #utf-8-sig also handles the BOM excel likes to add
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "File must be UTF-8 text") from None


def read_csv(file: UploadFile, required: set[str], max_rows: int) -> list[dict]:
    text = read_upload(file, (".csv",))
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "CSV has no header row")
    headers = {h.strip().lower() for h in reader.fieldnames}
    missing = required - headers
    if missing:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Missing column(s): {', '.join(sorted(missing))}")

    rows = []
    for row in reader:
        rows.append({(k or "").strip().lower(): (v or "").strip() for k, v in row.items()})
        if len(rows) > max_rows:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Too many rows, the limit is {max_rows}")
    if not rows:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "CSV has no rows")
    return rows
