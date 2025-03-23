#!/bin/bash

CONTAINER_NAME=slurmctld
THE_USER=sgrundy
NUM_NODES=1

resvname="${1:-x}"

if [ "${resvname}" == 'x' ] ; then
    echo "Usage: $0 RESERVATION_NAME"
    echo "ERROR: Invalid reservation name '$resvname'"
    exit 1
fi

#docker exec -ti -u sgrundy slurmctld salloc -N 1 --reservation=sgrundy_1

docker exec -ti -u ${THE_USER} $CONTAINER_NAME \
    salloc -N 1 --reservation=${resvname}


