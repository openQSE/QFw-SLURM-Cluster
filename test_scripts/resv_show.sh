#!/bin/bash

CONTAINER_NAME=slurmctld


docker exec $CONTAINER_NAME scontrol show res
#docker exec $CONTAINER_NAME scontrol show res --json

# scontrol create reservation user=alan,brenda \
#     starttime=noon duration=60 flags=daily nodecnt=10

