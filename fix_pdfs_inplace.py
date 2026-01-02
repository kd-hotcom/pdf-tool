#!/usr/bin/env python3
# fix_pdfs_inplace.py
# Rekursiv PDFs mit qpdf "linearize" reparieren – ohne Duplikate (in-place).
# KD Info

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

def find_qpdf(explicit: str | None) -> str:
    if explicit:
        p = Path(explicit)
        if p.exists():
            return str(p)
        raise FileNotFoundError(f"qpdf nicht gefunden unter: {explicit}")

    which = shutil.which("qpdf")
    if which:
        return which

    raise FileNotFoundError(
        "qpdf wurde nicht gefunden. Installiere qpdf und stelle sicher, dass es im PATH ist,\n"
        "oder gib den Pfad an: --qpdf \"C:\\\\Program Files\\\\qpdf\\\\bin\\\\qpdf.exe\""
    )

def run_qpdf(qpdf: str, src: Path, tmp_out: Path, mode: str) -> None:
    # mode: "linearize" oder "disable_object_streams"
    if mode == "linearize":
        cmd = [qpdf, "--linearize", str(src), str(tmp_out)]
    elif mode == "disable_object_streams":
        cmd = [qpdf, "--object-streams=disable", str(src), str(tmp_out)]
    else:
        raise ValueError(f"Unbekannter Modus: {mode}")

    # qpdf schreibt Fehler nach stderr und liefert !=0 bei Problemen
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        msg = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(msg or f"qpdf returncode={proc.returncode}")

def is_pdf_file(path: Path) -> bool:
    # schnell & robust: Endung + kurzer Magic-Header Check
    if path.suffix.lower() != ".pdf":
        return False
    try:
        with path.open("rb") as f:
            head = f.read(5)
        return head == b"%PDF-"
    except Exception:
        return False

def fix_one_pdf(qpdf: str, pdf_path: Path, mode: str, dry_run: bool) -> tuple[bool, str]:
    # Returns (changed, status_message)
    if dry_run:
        return False, "DRY-RUN"

    # temp im gleichen Verzeichnis, damit replace() auf demselben Volume atomar ist
    tmp_name = f".{pdf_path.name}.qpdf_tmp"
    tmp_path = pdf_path.with_name(tmp_name)

    # Sicherheit: falls ein altes Temp-File liegt, entfernen
    try:
        if tmp_path.exists():
            tmp_path.unlink()
    except Exception:
        pass

    try:
        run_qpdf(qpdf, pdf_path, tmp_path, mode)

        # Plausibilitätscheck: Temp muss existieren und nicht 0 Byte sein
        if not tmp_path.exists() or tmp_path.stat().st_size < 10:
            raise RuntimeError("Temp-Ausgabe ist ungültig/leer.")

        # Atomarer Austausch (Windows: ersetzt, wenn Datei nicht gelockt ist)
        # Wenn PDF gerade offen ist, scheitert replace() -> wir melden das sauber.
        tmp_path.replace(pdf_path)
        return True, "OK"

    except Exception as e:
        # Temp aufräumen
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except Exception:
            pass
        return False, f"FEHLER: {e}"

def iter_pdfs(root: Path):
    # Skip typischen Krempel
    skip_dirs = {"$recycle.bin", "system volume information", ".git", ".svn", "__pycache__"}
    for dirpath, dirnames, filenames in os.walk(root):
        # Verzeichnisse filtern
        dirnames[:] = [d for d in dirnames if d.lower() not in skip_dirs]
        for fn in filenames:
            p = Path(dirpath) / fn
            if is_pdf_file(p):
                yield p

def main():
    ap = argparse.ArgumentParser(
        description="Rekursiv PDFs in-place mit qpdf fixen (keine Duplikate)."
    )
    ap.add_argument("root", help="Wurzelordner, der rekursiv durchsucht wird.")
    ap.add_argument("--qpdf", help="Pfad zur qpdf.exe (wenn nicht im PATH).", default=None)
    ap.add_argument(
        "--mode",
        choices=["linearize", "disable_object_streams"],
        default="linearize",
        help="Fix-Methode: linearize (Standard) oder object-streams deaktivieren (Holzhammer).",
    )
    ap.add_argument("--dry-run", action="store_true", help="Nur anzeigen, nichts ändern.")
    ap.add_argument("--quiet", action="store_true", help="Weniger Ausgabe.")
    args = ap.parse_args()

    root = Path(args.root).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        print(f"Ungültiger Ordner: {root}", file=sys.stderr)
        sys.exit(2)

    try:
        qpdf = find_qpdf(args.qpdf)
    except Exception as e:
        print(str(e), file=sys.stderr)
        sys.exit(2)

    total = 0
    fixed = 0
    failed = 0

    for pdf in iter_pdfs(root):
        total += 1
        changed, status = fix_one_pdf(qpdf, pdf, args.mode, args.dry_run)
        if status.startswith("OK"):
            fixed += 1
        elif status.startswith("DRY-RUN"):
            pass
        else:
            failed += 1

        if not args.quiet:
            print(f"{pdf}  ->  {status}")

    print("\n--- Ergebnis ---")
    print(f"Gefunden: {total}")
    print(f"Gefixt:   {fixed}{' (dry-run)' if args.dry_run else ''}")
    print(f"Fehler:   {failed}")

    # Exitcode wie früher üblich: 0 wenn alles sauber, 1 wenn irgendwas schiefging
    sys.exit(0 if failed == 0 else 1)

if __name__ == "__main__":
    main()
