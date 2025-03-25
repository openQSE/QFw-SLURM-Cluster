#!/bin/bash


#    -H "X-SLURM-USER-NAME: sgrundy" \
#    -H "X-SLURM-USER-TOKEN: $TOKEN" \
#    -H "Authorization: Bearer $TOKEN" \

#TOKEN=${SLURM_JWT:-x}

#Content-Type: application/json
#X-SLURM-USER-NAME: <your_username>
#X-SLURM-USER-TOKEN: <your_jwt>

# scontrol token username=sgrundy
TOKEN=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJleHAiOjE3NDI5MjAwMTAsImlhdCI6MTc0MjkxODIxMCwic3VuIjoic2dydW5keSJ9.eiy_yzN8EBxp-L3YOH7V_3j4GUPcRVK5hm6YmDKObf0

#    -H "Authorization: Bearer $TOKEN" \

SCURL="docker exec -u sgrundy -ti slurmrestd curl "

$SCURL -v -X POST http://localhost:6820/slurm/v0.0.39/job/submit \
    -H "Content-Type: application/json" \
    -H "X-SLURM-USER-NAME: sgrundy" \
    -H "X-SLURM-USER-TOKEN: $TOKEN" \
    -d '{
        "job": {
	      "script": "#!/bin/bash --login\n echo \"testing api ${HELLO}\" ",
	      "name": "DummyJob",
	      "current_working_directory": "/tmp",
	      "environment": [
		"HELLO=world"
	      ],
	      "nodes": "1",
	      "tasks": 1,
	      "time_limit": 10,
              }
     }'

