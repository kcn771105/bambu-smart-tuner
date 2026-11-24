"""直接运行：python cli.py analyze 工程.3mf  （等价 python -m core.cli）"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.cli import main   # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
