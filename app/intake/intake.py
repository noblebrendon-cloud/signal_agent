import json
import hashlib
import os
import mimetypes
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional, List, Set

import yaml

# --- Configuration ---
ROOT = Path(__file__).resolve().parents[2] # Adjusted for app/intake/intake.py
CONFIG_PATH = ROOT / "config.yaml"
DATA_DIR = ROOT / "data"
INTAKE_DIR = DATA_DIR / "intake"
INTAKE_LEDGER = INTAKE_DIR / "intake.jsonl"
INTAKE_TEXT_DIR = INTAKE_DIR / "text"
INTAKE_SUMMARY = INTAKE_DIR / "INTAKE_LOG.md"

# Exclusion Rules
EXCLUDE_DIRS = {
    '.git', '.venv', '__pycache__', 'node_modules', 'site-packages',
    'dist', 'build', 'outputs', 'intake'
}
MAX_FILE_SIZE_MB = 50

# --- Helper Functions ---

def get_file_sha256(path: Path) -> str:
    """Calculate SHA256 of a file."""
    sha256 = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            sha256.update(chunk)
    return sha256.hexdigest()

def get_text_sha256(text: str) -> str:
    """Calculate SHA256 of a string."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def normalize_text(text: str) -> str:
    """Normalize newlines and strip null bytes."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\x00", "") # Strip null bytes
    return text.strip()

class IntakeSystem:
    def __init__(
        self,
        mode: str = "NORMAL",
        scan_roots: Optional[List[Path]] = None,
        only_ext: Optional[str] = None,
        explicit_roots: bool = False,
    ):
        self.mode = mode
        self.scan_roots = [p.resolve() for p in (scan_roots or [ROOT])]
        self.only_ext = only_ext.lower() if only_ext else None
        self.explicit_roots = explicit_roots
        self.ledger_cache: Dict[str, str] = {} # path -> source_sha256
        self.stats = {
            "total": 0, "supported": 0, "ingested": 0,
            "skipped_unchanged": 0, "skipped_ignored": 0, "errors": 0
        }
        self.setup_directories()
        self.load_ledger()

        # Log Posture Shift if MOD
        if self.mode == "MOD":
            self.log_posture_shift()

    def setup_directories(self):
        INTAKE_DIR.mkdir(parents=True, exist_ok=True)
        INTAKE_TEXT_DIR.mkdir(parents=True, exist_ok=True)

    def load_ledger(self):
        """Load the last seen state from the JSONL ledger for idempotency."""
        if not INTAKE_LEDGER.exists():
            return

        # Read the file line by line; later entries overwrite earlier ones for the same path
        try:
            with open(INTAKE_LEDGER, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        entry = json.loads(line)
                        if entry.get("status") == "success":
                            self.ledger_cache[entry["source_path"]] = entry["source_sha256"]
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            print(f"Warning: Could not read ledger: {e}")

    def append_event(self, event: Dict[str, Any]):
        """Append an event to the JSONL ledger."""
        # Ensure timestamp is first
        if "timestamp" not in event:
            event = {"timestamp": datetime.now(timezone.utc).isoformat(), **event}

        with open(INTAKE_LEDGER, "a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")

    def log_posture_shift(self):
        """Explicitly log the transition to MOD mode (Integrity Mode)."""
        print(">>> POSTURE SHIFT: MOD MODE (INTEGRITY FIRST) <<<")
        self.append_event({
            "event_type": "POSTURE_SHIFT",
            "mode": "MOD",
            "integrity_check": "full_provenance",
            "message": "System entering Integrity Mode. All actions explicit.",
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

    def should_skip_path(self, path: Path) -> bool:
        """Check against exclude directories."""
        if not self.explicit_roots:
            try:
                rel = path.relative_to(ROOT)
                for part in rel.parts:
                    if part in EXCLUDE_DIRS:
                        return True
            except ValueError:
                pass # path not relative to root
        return False

    def extract_pdf(self, path: Path) -> str:
        try:
             from app.intake.extract_pdf_text import extract_pdf_text
             return extract_pdf_text(path)
        except ImportError:
             # Fallback to pypdf if module missing (or raise, user chose pdfminer path)
             # But user said "don't mix". So let's stick to the new module.
             raise RuntimeError("pdfminer extraction module not found")

    def extract_docx(self, path: Path) -> str:
        try:
            import docx
        except ImportError as e:
            raise RuntimeError("DOCX extraction requires python-docx. Install with: pip install python-docx") from e
        doc = docx.Document(path)
        # Simple paragraph extraction; could expand to tables if needed
        return "\n".join([p.text for p in doc.paragraphs])

    def extract_epub(self, path: Path) -> str:
        import ebooklib
        from ebooklib import epub
        from bs4 import BeautifulSoup
        book = epub.read_epub(path)
        chapters = []
        # Attempt to iterate in spine order
        for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
            soup = BeautifulSoup(item.get_body_content(), 'html.parser')
            text = soup.get_text()
            if text.strip():
                chapters.append("--- CHAPTER ---")
                chapters.append(text)
        return "\n\n".join(chapters)

    def extract_text_content(self, path: Path) -> str:
        """Router for text extraction."""
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            return self.extract_pdf(path)
        elif suffix == ".docx":
            return self.extract_docx(path)
        elif suffix == ".epub":
            return self.extract_epub(path)
        elif suffix in {".txt", ".md", ".json", ".yaml", ".yml", ".py", ".sh", ".js", ".css", ".html"}:
            return path.read_text(encoding="utf-8", errors="ignore")
        else:
            raise ValueError(f"Unsupported format: {suffix}")

    def process_file(self, path: Path):
        self.stats["total"] += 1
        try:
            rel_path = str(path.relative_to(ROOT)).replace("\\", "/") # POSIX style paths in JSON
        except ValueError:
            rel_path = str(path)

        # 1. Ignore Checks
        if self.should_skip_path(path):
            self.stats["skipped_ignored"] += 1
            return

        # 2. Size Check
        size_bytes = path.stat().st_size
        if size_bytes > MAX_FILE_SIZE_MB * 1024 * 1024:
            self.append_event({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "source_path": rel_path,
                "status": "skipped_too_large",
                "size_bytes": size_bytes,
                "error_message": f"File exceeds {MAX_FILE_SIZE_MB}MB"
            })
            self.stats["skipped_ignored"] += 1
            return

        # 3. Supported Extension Check
        supported_exts = {".pdf", ".docx", ".epub", ".txt", ".md", ".py"}
        if path.suffix.lower() not in supported_exts:
            # Silent skip or log as unsupported? User said "Only include extensions you support"
            # We will just skip silently to avoid spamming the log with random assets
            return

        self.stats["supported"] += 1

        try:
            # 4. Idempotency Check
            current_hash = get_file_sha256(path)
            last_hash = self.ledger_cache.get(rel_path)

            if last_hash == current_hash:
                self.stats["skipped_unchanged"] += 1
                if self.mode == "MOD":
                    # In MOD mode, even skipped files are explicitly noted if re-verified
                    pass

                self.append_event({
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "source_path": rel_path,
                    "source_sha256": current_hash,
                    "status": "skipped_unchanged",
                    "doc_type": path.suffix.lower()[1:],
                    "mode": self.mode
                })
                return

            # 5. Extraction
            print(f"Ingesting: {rel_path} [{self.mode}]")
            raw_text = self.extract_text_content(path)
            text = normalize_text(raw_text)

            if not text:
                raise ValueError("Extracted text is empty")

            text_hash = get_text_sha256(text)
            out_filename = f"{text_hash}.txt"
            out_path = INTAKE_TEXT_DIR / out_filename

            # 6. Storage (CAS)
            if not out_path.exists():
                with open(out_path, "w", encoding="utf-8") as f:
                    f.write(text)

            # 7. Log Success
            self.append_event({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "source_path": rel_path,
                "source_sha256": current_hash,
                "size_bytes": size_bytes,
                "mtime": path.stat().st_mtime,
                "doc_type": path.suffix.lower()[1:],
                "status": "success",
                "extractor": "standard_v1",
                "text_output_path": f"text/{out_filename}",
                "text_chars": len(text),
                "text_sha256": text_hash,
                "error_message": None,
                "mode": self.mode
            })
            self.stats["ingested"] += 1

            # Update cache
            self.ledger_cache[rel_path] = current_hash

        except Exception as e:
            self.stats["errors"] += 1
            print(f"Error processing {rel_path}: {e}")
            error_event: Dict[str, Any] = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "source_path": rel_path,
                "status": "error",
                "error_message": str(e),
                "mode": self.mode
            }
            if path.suffix.lower() == ".docx":
                error_event["extractor"] = "docx_v1"
            self.append_event(error_event)

    def run(self):
        print(f"Starting Intake v2 Scan... Mode: {self.mode}")
        for scan_root in self.scan_roots:
            print(f"Scanning ROOT: {scan_root}")

        # Recursive walk
        for scan_root in self.scan_roots:
            for path in scan_root.rglob("*"):
                if not path.is_file():
                    continue
                if self.only_ext and path.suffix.lower() != self.only_ext:
                    continue
                self.process_file(path)

        print("\n--- Scan Complete ---")
        print(json.dumps(self.stats, indent=2))

        # Optional: Generate Markdown Summary
        self.generate_summary()

    def generate_summary(self):
        """Generate a human-readable summary from the ledger."""
        try:
            with open(INTAKE_SUMMARY, "w", encoding="utf-8") as f:
                f.write(f"# Intake Summary\n")
                f.write(f"Generated: {datetime.now(timezone.utc).isoformat()}\n")
                f.write(f"Mode: {self.mode}\n\n")
                f.write("| Status | Count |\n|---|---|\n")
                for k, v in self.stats.items():
                    f.write(f"| {k} | {v} |\n")
        except Exception:
            pass

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="SignalAgent Intake System")
    parser.add_argument("--mode", default="NORMAL", choices=["NORMAL", "MOD"], help="Execution Mode (NORMAL or MOD)")
    parser.add_argument("--root", action="append", help="Optional scan root path (repeatable)")
    parser.add_argument("--only-ext", choices=["pdf"], help="Optional extension filter")
    args = parser.parse_args()

    scan_roots: List[Path] = [ROOT]
    if args.root:
        scan_roots = []
        for raw_root in args.root:
            resolved_root = Path(raw_root).expanduser().resolve()
            if not resolved_root.exists():
                parser.error(f"--root path does not exist: {resolved_root}")
            if not resolved_root.is_dir():
                parser.error(f"--root path is not a directory: {resolved_root}")
            scan_roots.append(resolved_root)

    only_ext = None
    if args.only_ext:
        only_ext = f".{args.only_ext.lower()}"

    agent = IntakeSystem(
        mode=args.mode,
        scan_roots=scan_roots,
        only_ext=only_ext,
        explicit_roots=bool(args.root),
    )
    agent.run()
