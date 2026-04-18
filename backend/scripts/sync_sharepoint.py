"""Sync klantenkaarten from SharePoint or a local Excel file.

Usage:
  # From local Excel:
  python scripts/sync_sharepoint.py --file klantenkaart.xlsx --klant 10001

  # From SharePoint (requires SP_* env vars):
  python scripts/sync_sharepoint.py --sharepoint --folder "Klantenkaarten" --klant 10001
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sqlmodel import Session  # noqa: E402

from kwabo.db.session import engine, init_db  # noqa: E402
from kwabo.db.seed import seed  # noqa: E402
from kwabo.integrations.sharepoint import SharePointClient, sync_from_excel  # noqa: E402


async def main() -> None:
    parser = argparse.ArgumentParser(description="Sync klantenkaarten")
    parser.add_argument("--file", help="Lokaal .xlsx bestand")
    parser.add_argument("--klant", required=True, help="Navision klantnr")
    parser.add_argument("--sharepoint", action="store_true", help="Download vanuit SharePoint")
    parser.add_argument("--folder", default="", help="SharePoint folder pad")
    parser.add_argument("--sp-file", default="", help="Specifiek bestand in SharePoint folder")
    args = parser.parse_args()

    init_db()

    if args.file:
        xlsx = Path(args.file).read_bytes()
    elif args.sharepoint:
        client = SharePointClient()
        if args.sp_file:
            file_path = f"{args.folder}/{args.sp_file}" if args.folder else args.sp_file
        else:
            files = await client.list_files(args.folder)
            xlsx_files = [f for f in files if f["name"].endswith((".xlsx", ".xls"))]
            if not xlsx_files:
                print(f"Geen Excel bestanden gevonden in '{args.folder}'")
                sys.exit(1)
            print(f"Gevonden: {[f['name'] for f in xlsx_files]}")
            file_path = f"{args.folder}/{xlsx_files[0]['name']}" if args.folder else xlsx_files[0]["name"]
        print(f"Downloading {file_path}...")
        xlsx = await client.download_file(file_path)
    else:
        print("Geef --file of --sharepoint")
        sys.exit(1)

    with Session(engine) as s:
        result = sync_from_excel(s, args.klant, xlsx)
    print(f"Klant {args.klant}: {result['mappings']} mappings, {result['prijzen']} prijzen")
    if result["errors"]:
        print(f"  Fouten: {result['errors']}")


if __name__ == "__main__":
    asyncio.run(main())
