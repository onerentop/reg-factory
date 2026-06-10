import os
import sys

# Ensure project root is first on sys.path so 'outlook_hybrid' resolves to
# the top-level package, not this tests sub-package.
_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _root not in sys.path:
    sys.path.insert(0, _root)
