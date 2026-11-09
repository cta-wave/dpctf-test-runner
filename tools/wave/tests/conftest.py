# The WPT-fork root (tools/localpaths.py) inserts vendored third_party
# packages (six 1.13, attrs 18.1, more-itertools, ...) at the front of
# sys.path. Several of these predate Python 3.12+ import machinery and
# modern dependency APIs, and they shadow the installed versions required
# by pytest plugins and hypothesis. The tools.wave modules under test do
# not use them, so remove every third_party path before test modules
# import.
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_THIRD_PARTY = os.path.normpath(os.path.join(_HERE, "..", "..", "third_party"))


def _is_vendored(path):
    if not path:
        return False
    return os.path.normpath(os.path.abspath(path)).startswith(_THIRD_PARTY)


sys.path = [p for p in sys.path if not _is_vendored(p)]

# Drop any vendored modules that were already imported so re-imports
# resolve to the installed versions.
for _name in list(sys.modules):
    if _name == "six" or _name.startswith("six.") \
            or _name == "attr" or _name.startswith("attr.") \
            or _name == "more_itertools" or _name.startswith("more_itertools."):
        del sys.modules[_name]
