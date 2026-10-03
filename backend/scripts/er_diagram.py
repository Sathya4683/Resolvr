"""
Draws the entity relationship diagram straight from the SQLAlchemy models with ERAlchemy,
so the picture can't drift from the code. Needs graphviz (`dot`) installed for png/pdf.

    cd backend
    python scripts/er_diagram.py ../docs/er_diagram.png        # image
    python scripts/er_diagram.py ../docs/er_diagram.md         # mermaid markdown
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eralchemy import render_er  # noqa: E402

from app import models  # noqa: E402,F401  (registers every table on Base.metadata)
from app.db import Base  # noqa: E402


def main() -> None:
    out = sys.argv[1] if len(sys.argv) > 1 else "er_diagram.png"
    #markdown output becomes a mermaid erDiagram block, everything else goes through graphviz
    mode = "mermaid_er" if out.endswith(".md") else "auto"
    render_er(Base.metadata, out, mode=mode, title="Resolvr data model")
    print(f"written {out}")


if __name__ == "__main__":
    main()
