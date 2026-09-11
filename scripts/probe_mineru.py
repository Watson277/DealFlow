"""Upload one PDF to MinerU and inspect its original artifacts, without RAG ingestion."""

from __future__ import annotations

import argparse
import json
import os
import time
import zipfile
from collections import Counter
from pathlib import Path
from uuid import uuid4

import httpx
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
API = "https://mineru.net/api/v4"


def save_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def inspect_artifacts(folder: Path) -> dict:
    inventory = []
    for path in sorted(folder.rglob("*")):
        if not path.is_file():
            continue
        item = {"file": path.relative_to(folder).as_posix(), "bytes": path.stat().st_size}
        if path.suffix.lower() == ".json":
            value = json.loads(path.read_text(encoding="utf-8-sig"))
            item["root_type"] = type(value).__name__
            if isinstance(value, dict):
                item["root_keys"] = list(value)
            if isinstance(value, list):
                item["length"] = len(value)
                records = [v for v in value if isinstance(v, dict)]
                item["record_keys"] = sorted({key for v in records for key in v})
                item["block_types"] = dict(Counter(str(v.get("type")) for v in records))
            # A bounded preview; the full original JSON is also preserved.
            item["preview"] = json.dumps(value, ensure_ascii=False)[:3000]
        elif path.suffix.lower() == ".md":
            text = path.read_text(encoding="utf-8-sig")
            item["characters"] = len(text)
            item["preview"] = text[:3000]
        inventory.append(item)
    return {"files": inventory}


def unpack(archive: Path, folder: Path) -> None:
    with zipfile.ZipFile(archive) as zipped:
        members = zipped.infolist()
        if sum(m.file_size for m in members) > 1024**3:
            raise ValueError("ZIP expands beyond the 1 GiB inspection limit")
        for member in members:
            target = (folder / member.filename).resolve()
            if not target.is_relative_to(folder.resolve()) or "\\" in member.filename:
                raise ValueError("Unsafe ZIP member path")
        zipped.extractall(folder)


def api_call(client: httpx.Client, method: str, path: str, token: str, **kwargs) -> dict:
    response = client.request(
        method, API + path, headers={"Authorization": f"Bearer {token}"}, **kwargs
    )
    if response.status_code != 200:
        raise RuntimeError(f"MinerU API HTTP {response.status_code}")
    body = response.json()
    if body.get("code") != 0:
        raise RuntimeError(f"MinerU API rejected request (code={body.get('code')})")
    return body["data"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path, nargs="?")
    parser.add_argument("--model", choices=["vlm", "pipeline"], default="vlm")
    parser.add_argument("--output", type=Path, default=ROOT / "data/mineru-probe")
    parser.add_argument("--batch-id", help="Resume polling an existing uploaded batch")
    parser.add_argument("--inspect", type=Path, help="Inspect an extracted folder offline")
    parser.add_argument("--wait-seconds", type=int, default=1800)
    args = parser.parse_args()
    if args.inspect:
        report = inspect_artifacts(args.inspect)
        save_json(args.inspect.parent / "inspection.json", report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return
    env = dotenv_values(ROOT / ".env")
    token = os.getenv("MINERU_API_TOKEN") or env.get("MINERU_API_TOKEN")
    if not token or not token.strip():
        parser.error("Set MINERU_API_TOKEN in the project .env or environment first")
    if args.wait_seconds <= 0:
        parser.error("--wait-seconds must be positive")
    if not args.batch_id:
        if not args.pdf or not args.pdf.is_file() or args.pdf.suffix.lower() != ".pdf":
            parser.error("Provide an existing local PDF")
        if args.pdf.stat().st_size > 200 * 1024**2:
            parser.error("PDF exceeds 200 MiB")
    run_dir = args.output.resolve() / (time.strftime("%Y%m%d-%H%M%S") + "-" + uuid4().hex[:8])
    run_dir.mkdir(parents=True)
    started = time.monotonic()
    # Authorization belongs only to MinerU API calls, never signed storage URLs.
    # The storage client also handles the download after the API client closes.
    with httpx.Client(timeout=120, follow_redirects=True) as storage:  # noqa: SIM117
        with httpx.Client(timeout=60, follow_redirects=False) as client:
            batch_id = args.batch_id
            if not batch_id:
                data = api_call(
                    client,
                    "POST",
                    "/file-urls/batch",
                    token,
                    json={
                        "files": [{"name": args.pdf.name}],
                        "model_version": args.model,
                        "enable_table": True,
                        "enable_formula": True,
                        "language": "ch",
                    },
                )
                batch_id = data["batch_id"]
                save_json(
                    run_dir / "request.json",
                    {
                        "batch_id": batch_id,
                        "filename": args.pdf.name,
                        "model": args.model,
                    },
                )
                print(f"Batch: {batch_id}; uploading PDF", flush=True)
                with args.pdf.open("rb") as source:
                    response = storage.put(data["file_urls"][0], content=source)
                if not response.is_success:
                    raise RuntimeError(f"Upload failed: HTTP {response.status_code}")
            print(f"Output: {run_dir}\nResume with --batch-id {batch_id}", flush=True)
            deadline = time.monotonic() + args.wait_seconds
            while time.monotonic() < deadline:
                data = api_call(client, "GET", f"/extract-results/batch/{batch_id}", token)
                results = data.get("extract_result", [])
                if len(results) > 1:
                    raise ValueError("This probe supports one file per batch")
                result = results[0] if results else {}
                state = result.get("state", "pending")
                print(
                    f"{time.monotonic() - started:.1f}s: {state} "
                    f"{result.get('extract_progress', {})}",
                    flush=True,
                )
                if state == "failed":
                    raise RuntimeError("MinerU parsing failed; inspect the task in MinerU console")
                if state == "done":
                    break
                time.sleep(5)
            else:
                raise TimeoutError(f"Polling timed out; resume batch {batch_id}")
            archive = run_dir / "result.zip"
            with storage.stream("GET", result["full_zip_url"]) as response:
                if not response.is_success:
                    raise RuntimeError(f"Download failed: HTTP {response.status_code}")
                with archive.open("wb") as target:
                    size = 0
                    for chunk in response.iter_bytes():
                        size += len(chunk)
                        if size > 1024**3:
                            raise ValueError("Download exceeds 1 GiB")
                        target.write(chunk)
    folder = run_dir / "artifacts"
    unpack(archive, folder)
    report = inspect_artifacts(folder)
    report.update(batch_id=batch_id, elapsed_seconds=round(time.monotonic() - started, 2))
    save_json(run_dir / "inspection.json", report)
    for item in report["files"]:
        print(f"{item['file']} ({item['bytes']} bytes)")
    print(f"Inspect JSON structure and previews: {run_dir / 'inspection.json'}")


if __name__ == "__main__":
    try:
        main()
    except httpx.HTTPError as exc:
        raise SystemExit(f"Network failure: {type(exc).__name__}; no credentials printed") from None
