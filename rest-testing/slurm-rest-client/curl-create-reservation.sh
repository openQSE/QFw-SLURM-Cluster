#!/bin/bash

TOKEN=${SLURM_JWT:-x}

#########
# NOTE:
#   scontrol show reservations
#   scontrol delete ReservationName=xyz
#########

######
# XXX: I can not use this user in header,
#      but get the token as 3t4 (i fail auth).
#      Fix is to leave this out of the header.
#
#  -H "X-SLURM-USER-NAME: sgrundy" \
######

#      "flags": [],

#      "start_time": "'$(date -v+1M +%s)'",
#2025-07-23T02:40:03
set -xe

#      "start_time": "'$(date -d "+1 minute" +%s)'",
curl -v \
    -X POST \
    http://localhost:6820/slurm/v0.0.43/reservation \
    -H "Content-Type: application/json" \
    -H "X-SLURM-USER-TOKEN: $TOKEN" \
    -d '{
      "name": "myreservation",
      "users": ["sgrundy"],
      "start_time": "2025-07-23T02:40:03",
      "duration": 600,
      "node_count": 1
    }'

