"""Keep debug output on for individual runs and opt out for suite runs."""
import os


def debug_print(*args, **kwargs):
    if os.environ.get('MOBILE_AGENT_DEBUG', '1').strip().lower() not in {'0', 'false', 'off'}:
        print(*args, **kwargs)
