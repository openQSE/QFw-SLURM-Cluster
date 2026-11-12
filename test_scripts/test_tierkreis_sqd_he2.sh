#!/bin/bash
set -euo pipefail

for target in directory nwqsim gateway; do
    docker exec slurmctld qfw-site-services start --target "${target}"
done

docker exec -i --user user-a --env HOME=/workspace/home/user-a \
    --env OPENSSL_armcap=0 \
    --env QFW_VENV=/workspace/qfw-container-base/tierkreis-sc-demo/.runtime/venv \
    --workdir /workspace/qfw-container-base/tierkreis-sc-demo \
    slurmctld bash -s <<'EOF'
set -euo pipefail
if [[ ! -r test/sqd-e2e.py ]]; then
    echo "Missing test/sqd-e2e.py in the demo checkout; update it and rerun ./tools/setup-tierkreis-demo.sh." >&2
    exit 1
fi
source /opt/openqse/qfw/bin/qfw-activate --venv "${QFW_VENV}"
exec "${QFW_VENV}/bin/python" test/sqd-e2e.py
EOF
