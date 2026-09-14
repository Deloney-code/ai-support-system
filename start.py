import os
import sys


def main() -> None:
    # If START_COMMAND=worker, run Celery instead of daphne
    if os.environ.get('START_COMMAND') == 'worker':
        sys.stdout.write("start.py: launching celery worker\n")
        sys.stdout.flush()
        os.execvp(
            'celery',
            ['celery', '-A', 'core', 'worker', '--loglevel=info', '--pool=solo']
        )
        return

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