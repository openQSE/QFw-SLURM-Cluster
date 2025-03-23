#!/bin/bash

CONTAINER_NAME=slurmctld

THE_USER=sgrundy
NUM_NODES=1
STARTTIME=now
DURATION=60

docker exec $CONTAINER_NAME \
    scontrol create reservation \
       user=${THE_USER} \
       starttime=${STARTTIME} \
       duration=${DURATION} \
       nodecnt=${NUM_NODES}

# scontrol create reservation user=alan,brenda \
#     starttime=noon duration=60 flags=daily nodecnt=10

