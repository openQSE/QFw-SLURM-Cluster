#!/bin/bash


#    -H "X-SLURM-USER-NAME: sgrundy" \
#    -H "X-SLURM-USER-TOKEN: $TOKEN" \

#TOKEN=${SLURM_JWT:-x}

# scontrol token username=sgrundy
TOKEN=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJleHAiOjE3NDI5MjAwMTAsImlhdCI6MTc0MjkxODIxMCwic3VuIjoic2dydW5keSJ9.eiy_yzN8EBxp-L3YOH7V_3j4GUPcRVK5hm6YmDKObf0

#    -H "Authorization: Bearer $TOKEN" \

SCURL="docker exec -u sgrundy -ti slurmrestd curl "

$SCURL -v -X GET \
    -H "X-SLURM-USER-NAME: sgrundy" \
    -H "X-SLURM-USER-TOKEN: $TOKEN" \
    http://localhost:6820/slurm/v0.0.39/nodes
#    http://slurmrestd:6820/slurm/v0.0.41/nodes

#    http://localhost:6820/slurm/v0.0.41/nodes
#    http://localhost:6820/slurm/v0.0.41/reservations
#    http://localhost:6820/slurm/v0.0.41/job/6
#    http://localhost:6820/slurm/v0.0.41/jobs

