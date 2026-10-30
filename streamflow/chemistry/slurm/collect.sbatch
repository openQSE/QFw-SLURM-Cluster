#!/bin/bash
#SBATCH --job-name=sf-collect
#SBATCH --account=qfw-test
#SBATCH --partition=normal
#SBATCH --nodelist=c3
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --time=00:05:00

set -euo pipefail
{{ streamflow_command }}
