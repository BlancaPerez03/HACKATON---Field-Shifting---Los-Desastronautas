# pytest loads this file before the tests. Adding the project folder to sys.path lets the tests
# write `from backend import ...` without installing the project as a package.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
