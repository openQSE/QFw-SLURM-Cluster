#!/bin/bash

TOKEN=${SLURM_JWT:-x}

# I can not use this user in header,
# but get the token as 3t4 (i fail auth).
# Fix is to leave this out of the header.
#
#  -H "X-SLURM-USER-NAME: sgrundy" \
#
set -xe

curl \
  -X GET \
  http://localhost:6820/slurm/v0.0.43/reservations \
  -H "Content-Type: application/json" \
  -H "X-SLURM-USER-TOKEN: $TOKEN"
