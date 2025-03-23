#!/bin/bash

CONTAINER_NAME=slurmctld

resvname="${1:-x}"

if [ "${resvname}" == 'x' ] ; then
    echo "Usage: $0 RESERVATION_NAME"
    echo "ERROR: Invalid reservation name '$resvname'"
    exit 1
fi

docker exec $CONTAINER_NAME \
    scontrol delete ReservationName=${resvname}
rc=$?

if [ $rc == 0 ] ; then
    echo "SUCCESS"
else
    echo "ERROR ($rc)"
fi
exit $rc

