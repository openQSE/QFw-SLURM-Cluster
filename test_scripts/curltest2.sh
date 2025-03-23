#!/bin/bash

TOKEN_FILE=/tmp/token9

if [ ! -f "${TOKEN_FILE}" ] ; then
	echo "Error: $! '${TOKEN_FILE}'"
	exit 1
fi

TOKEN=$(cat $TOKEN_FILE | tr -d '\n')

echo "Using TOKEN: '${TOKEN}'"
curl -H "Authorization: Bearer $TOKEN" http://localhost:6820/slurm/v0.0.41/nodes


#curl -v -H "Authorization: Bearer $TOKEN" #http://localhost:6820/slurm/v0.0.41/status
