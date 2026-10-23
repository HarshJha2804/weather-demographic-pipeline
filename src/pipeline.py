import subprocess
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
MAIN_SCRIPT = PROJECT_DIR / "scripts" / "main.py"

if __name__ == "__main__":
    subprocess.run(
        [sys.executable, str(MAIN_SCRIPT)],
        cwd=PROJECT_DIR,
        check=True,
    )
    print("\nPipeline completed successfully!")