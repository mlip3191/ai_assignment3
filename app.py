"""AI Jukebox entry point. Run with: python app.py"""

from __future__ import annotations

from pathlib import Path

from jukebox.ui.launch import serve


def main() -> None:
    serve(Path(__file__).resolve().parent)


if __name__ == "__main__":
    main()
