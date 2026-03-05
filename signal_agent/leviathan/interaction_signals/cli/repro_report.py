"""repro_report.py -- CLI to test stream replicability (v0.5 hardening)."""
import argparse, sys, hashlib, json, pathlib
import subprocess

def _hash_file(path: pathlib.Path) -> str:
    if not path.exists():
        return ""
    h = hashlib.sha256()
    with path.open("rb") as f:
        h.update(f.read())
    return h.hexdigest()

def main(argv: list[str] | None = None) -> int:
    repo_root = pathlib.Path(__file__).resolve().parent.parent.parent.parent.parent
    
    p = argparse.ArgumentParser(description="Reproducibility Report")
    p.add_argument("--out-dir", type=str, default=".", help="Output directory")
    args = p.parse_args(argv)
    
    out_dir = pathlib.Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    
    run1_path = out_dir / "run1.jsonl"
    run2_path = out_dir / "run2.jsonl"
    
    cmd_base = [sys.executable, "-m", "signal_agent.leviathan.interaction_signals.cli.run_stream"]
    
    # Run 1
    if run1_path.exists():
        run1_path.unlink()
    cmd1 = cmd_base + ["--ledger", str(run1_path)]
    subprocess.run(cmd1, cwd=repo_root, check=True)
    
    # Run 2
    if run2_path.exists():
        run2_path.unlink()
    cmd2 = cmd_base + ["--ledger", str(run2_path)]
    subprocess.run(cmd2, cwd=repo_root, check=True)
    
    # Compare
    hash1 = _hash_file(run1_path)
    hash2 = _hash_file(run2_path)
    
    summary = {
        "run1_sha256": hash1,
        "run2_sha256": hash2,
        "identical": hash1 == hash2
    }
    
    diff_path = out_dir / "diff.txt"
    if hash1 == hash2:
        with diff_path.open("w", encoding="utf-8") as f:
            f.write("")
    else:
        # Find first differing line
        with run1_path.open("r", encoding="utf-8") as f1, run2_path.open("r", encoding="utf-8") as f2:
            lines1 = f1.readlines()
            lines2 = f2.readlines()
            
            diff_line = -1
            for i in range(max(len(lines1), len(lines2))):
                if i >= len(lines1) or i >= len(lines2) or lines1[i] != lines2[i]:
                    diff_line = i
                    break
        
        with diff_path.open("w", encoding="utf-8") as f:
            if diff_line != -1:
                f.write(f"First difference at line {diff_line}\n")
            else:
                f.write("Files differ but logic error in diffing.\n")
                
    with (out_dir / "summary.json").open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
        
    print(f"Reproducibility report generated in {out_dir}")
    print(f"Identical: {summary['identical']}")
    return 0 if summary['identical'] else 1

if __name__ == "__main__":
    sys.exit(main())
