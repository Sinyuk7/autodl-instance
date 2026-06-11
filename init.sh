#!/bin/bash
# Deprecated source checkout entrypoint.

set -e

cat >&2 <<'EOF'
init.sh is no longer a runtime entrypoint.

Install and run the packaged CLI instead:
  uv tool install autodl-instance
  autodl config set userdata-repo git@github.com:username/my-comfyui-backup.git
  autodl setup
EOF

exit 1
