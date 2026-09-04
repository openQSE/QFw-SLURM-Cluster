#!/bin/bash

set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
slurm_config="${repo_dir}/slurm.conf"
compose_config="${repo_dir}/docker-compose.yml"
user_profile="${repo_dir}/config/qfw-user-profile.sh"

for node in nwqsim-head nwqsim-worker-1 nwqsim-worker-2 iqm-head; do
	grep -q "^NodeName=${node} " "${slurm_config}"
	grep -q "^  ${node}:$" "${compose_config}"
done

grep -q '^PartitionName=normal .*Nodes=c\[1-8\]' "${slurm_config}"
grep -q '^PartitionName=qfw-services .*AllowGroups=root' "${slurm_config}"
grep -q '^NodeName=nwqsim-head .*qpm-nwqsim' "${slurm_config}"
grep -q '^NodeName=nwqsim-worker-1 .*qpm-nwqsim' "${slurm_config}"
grep -q '^NodeName=nwqsim-worker-2 .*qpm-nwqsim' "${slurm_config}"
grep -q '^NodeName=iqm-head .*qpm-iqm-ornl-20q' "${slurm_config}"
grep -q '^set root /opt/qfw/openmpi$' "${repo_dir}/modulefiles/openmpi"
grep -q '^export QFW_SIMULATOR_NODES=nwqsim-head,nwqsim-worker-1,nwqsim-worker-2$' \
	"${user_profile}"

if grep '^PartitionName=normal ' "${slurm_config}" |
	grep -Eq 'nwqsim|iqm-head'; then
	echo "service node leaked into the normal partition" >&2
	exit 1
fi

echo "QFw service topology configuration passed"
