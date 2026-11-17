"""Print the builder page catalog as JSON."""

import json

from shadowsim.cli.catalog import listed_actions, listed_measurements, listed_states
from shadowsim.cli.run import _page_limits


def main() -> None:
    """Write states, measurements, actions, and page limits to stdout."""
    payload = {
        "limits": _page_limits(),
        "states": listed_states(),
        "measures": listed_measurements(),
        "actions": listed_actions(),
    }
    print(json.dumps(payload))


if __name__ == "__main__":
    main()
