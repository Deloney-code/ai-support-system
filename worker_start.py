import os
import sys

if __name__ == '__main__':
    os.execvp('celery', [
        'celery',
        '-A', 'core',
        'worker',
        '--loglevel=info',
        '--pool=solo'
    ])