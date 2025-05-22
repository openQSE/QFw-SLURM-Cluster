#!/bin/sh
#
#SBATCH --job-name=hellosleep
#SBATCH --output=job-hellosleep.%J.out
##SBATCH --ntasks=1
#SBATCH --time=00:01:00
#SBATCH --partition=normal

#-- DONE WITH ENV SETUP --

echo -n "[`date`] HELLO from "
hostname

echo "[`date`] Sleep 10..."
srun -n 1 sleep 10

echo -n "[`date`] GOODBYE from "
hostname
