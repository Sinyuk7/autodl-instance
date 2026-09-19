#!/bin/bash
# Deprecated source checkout entrypoint.

set -e

cat >&2 <<'EOF'
init.sh is no longer a runtime entrypoint.

Install and run the packaged CLI instead:
  uv tool install --editable --force /root/autodl-instance
  autodl init
  autodl setup
EOF

exit 1
