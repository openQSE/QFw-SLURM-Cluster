# Source this file to have easy command aliases
# to the docker based slurm commands.

# silence annoying macOS docker msgs
export DOCKER_CLI_HINTS=false

CONTAINER_NAME=slurmctld

alias sinfo="docker exec -ti ${CONTAINER_NAME} sinfo "
alias scontrol="docker exec -ti ${CONTAINER_NAME} scontrol "
alias salloc="docker exec -ti ${CONTAINER_NAME} salloc "
alias squeue="docker exec -ti ${CONTAINER_NAME} squeue "
alias srun="docker exec -ti ${CONTAINER_NAME} srun"
alias sbatch="docker exec -ti ${CONTAINER_NAME} -w /mnt sbatch "
alias scurl="docker exec -ti slurmrestd curl "
