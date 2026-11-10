#!/bin/bash
set -euo pipefail

for target in directory nwqsim gateway; do
    docker exec slurmctld qfw-site-services start --target "${target}"
done

docker exec -i --user user-a --env HOME=/workspace/home/user-a \
    --env OPENSSL_armcap=0 \
    --workdir /workspace/qfw-container-base/tierkreis-sc-demo \
    slurmctld bash -s <<'EOF'
set -euo pipefail
source /opt/openqse/qfw/bin/qfw-activate --venv /opt/openqse/qfw-venv
tkr run -g tkr.graphs.sqd:workflow -i examples/sqd_he2_input.json \
    --config runtime.toml --profile qfw-slurm --timeout 86400 -o
EOF
