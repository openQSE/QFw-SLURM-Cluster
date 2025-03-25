#!/bin/bash


#    -H "X-SLURM-USER-NAME: sgrundy" \
#    -H "X-SLURM-USER-TOKEN: $TOKEN" \
#    -H "Authorization: Bearer $TOKEN" \

TOKEN=${SLURM_JWT:-x}

#Content-Type: application/json
#X-SLURM-USER-NAME: <your_username>
#X-SLURM-USER-TOKEN: <your_jwt>

#    -H "Authorization: Bearer $TOKEN" \


curl -v -X POST http://localhost:6820/slurm/v0.0.39/job/submit \
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

