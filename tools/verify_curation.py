import shutil
import sys
import time
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]
CURATION_DIR = ROOT / "app" / "hq" / "curation"
STAGING_DIR = ROOT / "data" / "intake" / "_test_staging"
PROCESSED_DIR = ROOT / "data" / "processed"

def run(cmd):
    import subprocess
    print(f"$ {' '.join(cmd)}")
    subprocess.run(cmd, check=True)

def test_curation():
    print("=== Testing Curation System ===")
    
    # Setup
    if STAGING_DIR.exists():
        shutil.rmtree(STAGING_DIR)
    STAGING_DIR.mkdir(parents=True)
    
    test_file = STAGING_DIR / "test_doc.md"
    test_file.write_text("# Test Document\nUnique content " + datetime.now().isoformat())
    
    print(f"Created test file: {test_file}")
    
    # Run Curation
    run([sys.executable, str(CURATION_DIR / "curate.py"), "--path", str(test_file)])
    
    # Verify
    # Expect file to be moved to processed/ (per new rules.yaml for .md files)
    # The default rules say: docs_processed -> data/processed
    # So we look in data/processed
    found = list(PROCESSED_DIR.glob("test_doc__*.md"))
    if found:
        print(f"PASS: File curated to {found[0]}")
        # Cleanup
        found[0].unlink()
    else:
        print(f"FAIL: File not found in {PROCESSED_DIR}")
        # Debug: list what is there
        print("Contents of processed:")
        for f in PROCESSED_DIR.glob("*"):
            print(f" - {f}")
        sys.exit(1)

    # Test Duplicate Logic
    print("\n=== Testing Duplicate Logic ===")
    test_file.write_text("DUPLICATE CONTENT")
    
    # First pass
    run([sys.executable, str(CURATION_DIR / "curate.py"), "--path", str(test_file)])
    first_curated = list(PROCESSED_DIR.glob("test_doc__*.md"))[0]
    
    # Restore file for second pass
    test_file.write_text("DUPLICATE CONTENT")
    
    # Second pass
    run([sys.executable, str(CURATION_DIR / "curate.py"), "--path", str(test_file)])
    
    # Verify file still exists in staging (skipped)
    if test_file.exists():
        print("PASS: Duplicate file skipped (remains in source)")
        test_file.unlink()
    else:
        print("FAIL: Duplicate file was removed/processed again")
        sys.exit(1)
        
    first_curated.unlink()
    shutil.rmtree(STAGING_DIR)
    print("\nALL TESTS PASSED")

if __name__ == "__main__":
    test_curation()
