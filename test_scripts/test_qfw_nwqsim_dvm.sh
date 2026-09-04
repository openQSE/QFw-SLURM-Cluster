#!/bin/bash

set -euo pipefail

cluster_container="${QFW_SLURM_CONTROLLER:-slurmctld}"
dvm_uri="${QFW_NWQSIM_DVM_URI:-/var/lib/qfw-site-services/qpm/nwqsim/prte_dvm/dvm-uri}"

output="$(docker exec nwqsim-head bash -lc "
export MODULEPATH=/etc/modulefiles:/usr/share/Modules/modulefiles:/usr/share/modulefiles
module load libfabric openmpi nwqsim
prun --allow-run-as-root \\
  --dvm file:${dvm_uri} \\
  --map-by ppr:1:node \\
  --np 2 \\
  --host nwqsim-head,nwqsim-worker-1 \\
  /opt/openqse/nwqsim/bin/circuit_runner.nwqsim \\
  --qasm_string \$'OPENQASM 2.0;\\ninclude \"qelib1.inc\";\\nqreg q[20];\\ncreg c[20];\\nh q[0];\\nmeasure q -> c;\\n' \\
  --shots 16 \\
  --backend MPI \\
  --verbose
")"

grep -q 'nqubits:20' <<<"${output}"
grep -q 'n_nodes:2' <<<"${output}"
grep -q 'Measurement (tests=16)' <<<"${output}"

docker exec "${cluster_container}" sinfo -h -n \
	'nwqsim-head,nwqsim-worker-1,nwqsim-worker-2' \
	-o '%N %T' | grep -q 'idle'

echo "NWQSim two-host DVM execution passed"
