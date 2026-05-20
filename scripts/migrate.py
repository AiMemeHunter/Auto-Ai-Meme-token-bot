"""
Alembic migration runner helper.
"""
import subprocess
import sys


def main():
    """Run Alembic migrations."""
    cmd = ["alembic", "upgrade", "head"]
    if len(sys.argv) > 1:
        if sys.argv[1] == "create":
            msg = sys.argv[2] if len(sys.argv) > 2 else "auto migration"
            cmd = ["alembic", "revision", "--autogenerate", "-m", msg]
        elif sys.argv[1] == "downgrade":
            cmd = ["alembic", "downgrade", sys.argv[2] if len(sys.argv) > 2 else "-1"]

    print(f"Running: {' '.join(cmd)}")
    subprocess.run(cmd)


if __name__ == "__main__":
    main()
