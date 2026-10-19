"""`gethired` 콘솔 진입점. 명령은 cli.py (`python -m app`도 같다)."""
import sys

from . import cli


def main(argv: list[str] | None = None) -> None:
    sys.exit(cli.main(argv))


if __name__ == "__main__":
    main()
