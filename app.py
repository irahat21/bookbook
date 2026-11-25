"""BookOrbit AI - start the desktop app.  Run:  .venv/bin/python app.py
(Run .venv/bin/python seed.py first to create demo data in data/.)"""
from bookorbit.app_context import build_context
from bookorbit.ui.main_window import MainWindow


def main() -> None:
    ctx = build_context()
    if not ctx.fs.load("books"):
        print("No data found - run `.venv/bin/python seed.py` first.")
    MainWindow(ctx).mainloop()


if __name__ == "__main__":
    main()
