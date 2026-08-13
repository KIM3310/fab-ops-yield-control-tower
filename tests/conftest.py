"""Suite-wide non-production runtime profile."""

import os

# Tests exercise the credential-free synthetic demo unless an individual test
# explicitly switches to a fail-closed production profile.
os.environ.setdefault("SEMICONDUCTOR_OPS_MODE", "demo")
