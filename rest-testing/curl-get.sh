#!/bin/bash


#    -H "X-SLURM-USER-NAME: sgrundy" \
#    -H "X-SLURM-USER-TOKEN: $TOKEN" \

TOKEN=${SLURM_JWT:-x}

#    -H "Authorization: Bearer $TOKEN" \

curl -v -X GET \
    -H "X-SLURM-USER-NAME: sgrundy" \
    -H "X-SLURM-USER-TOKEN: $TOKEN" \
    http://localhost:6820/slurm/v0.0.39/nodes
#    http://slurmrestd:6820/slurm/v0.0.41/nodes

#    http://localhost:6820/slurm/v0.0.41/nodes
#    http://localhost:6820/slurm/v0.0.41/reservations
#    http://localhost:6820/slurm/v0.0.41/job/6
#    http://localhost:6820/slurm/v0.0.41/jobs

