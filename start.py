import os
import sys


def main() -> None:
    port = os.environ.get("PORT")
    if not port:
        sys.stderr.write("start.py: PORT environment variable is not set\n")
        sys.exit(1)
    try:
        int(port)
    except ValueError:
        sys.stderr.write(f"start.py: PORT={port!r} is not a valid integer\n")
        sys.exit(1)

    sys.stdout.write(f"start.py: launching daphne on 0.0.0.0:{port}\n")
    sys.stdout.flush()

    os.execvp(
        "daphne",
        ["daphne", "-b", "0.0.0.0", "-p", port, "core.asgi:application"],
    )


if __name__ == "__main__":
    main()
