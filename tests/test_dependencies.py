"""
test_dependencies.py — verify all packages in requirements.txt are importable.

This test reads requirements.txt, maps each pip package name to its Python
import name, and tries to import it. If a package is missing, the test fails
with a clear message naming the exact package to install.

This prevents the situation where the test suite passes silently while the
application crashes at startup due to a missing dependency.

To add a new dependency:
  1. Add it to requirements.txt
  2. If the pip name differs from the import name (e.g. pyserial → serial),
     add an entry to _PIP_TO_IMPORT below.
  3. Run the tests — they will fail immediately if you forgot to install it.
"""

import importlib
import os
import re
import pytest

# Pip package name → Python import name for packages where they differ.
# Packages not listed here are imported by replacing hyphens with underscores.
_PIP_TO_IMPORT = {
    "pyserial":   "serial",
    "paho-mqtt":  "paho.mqtt.client",
}

# Entries in requirements.txt that are not pip packages (skip them).
_SKIP = {"python"}


def _parse_requirements():
    """Return a list of (pip_name, import_name) tuples from requirements.txt."""
    req_path = os.path.join(os.path.dirname(__file__), '..', 'requirements.txt')
    if not os.path.exists(req_path):
        pytest.skip("requirements.txt not found")

    entries = []
    with open(req_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            # Strip version specifiers: "paho-mqtt>=2.0" → "paho-mqtt"
            pip_name = re.split(r'[~=<>!]', line)[0].strip()
            if pip_name.lower() in _SKIP:
                continue
            import_name = _PIP_TO_IMPORT.get(pip_name, pip_name.replace('-', '_'))
            entries.append((pip_name, import_name))
    return entries


_REQUIREMENTS = _parse_requirements()


@pytest.mark.parametrize("pip_name,import_name", _REQUIREMENTS,
                         ids=[r[0] for r in _REQUIREMENTS])
def test_dependency_importable(pip_name, import_name):
    """Each package listed in requirements.txt must be importable."""
    try:
        importlib.import_module(import_name)
    except ImportError:
        pytest.fail(
            f"Package '{pip_name}' (import as '{import_name}') is not installed. "
            f"Run: pip install {pip_name}"
        )
