#!/bin/bash

TOKEN=${SLURM_JWT:-x}


#    -H "X-SLURM-USER-NAME: sgrundy" \
set -xe

curl -v -X GET \
    -H "X-SLURM-USER-TOKEN: $TOKEN" \
    -o slurm_openapi.json \
    http://localhost:6820/openapi.json

# This will dump the 'slurm_openapi.json' file.
# Starting with slurm-25.05, the create reservation endpoint
# is at /slurm/v0.0.43/reservation'
