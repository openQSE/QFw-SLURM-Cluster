#!/bin/bash
#SBATCH --job-name=sf-chemistry
#SBATCH --account=qfw-test
#SBATCH --partition=normal
#SBATCH --nodelist=c2
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --time=00:10:00
#SBATCH --qpu=ornl-iqm-20q
#SBATCH --workload-kind=hybrid
#SBATCH --circ-count=32000
#SBATCH --max-qubits=10
#SBATCH --max-depth=1000
#SBATCH --max-shots=4096

set -euo pipefail
{{ streamflow_command }}
