import requests
import json

#SLURM_API_URL = "http://localhost:6820/slurm/v0.0.39/job/submit"
SLURM_API_URL = "http://localhost:6820/slurm/v0.0.43/job/submit"

MY_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJleHAiOjE3NTEwNjg5MTYsImlhdCI6MTc1MTA2NzExNiwic3VuIjoicm9vdCJ9.u6SG176t9FEkon7ArtWTqDBT2ROYhglvnkvoYQvoZPw"



HEADERS = {
        "Content-type": "application/json",
        "X-SLURM-USER-NAME": "sgrundy",
        "X-SLURM-USER-TOKEN": MY_TOKEN
}

#                "hostname; date ; sleep 5 ; date; "
#                "echo \"Goodbye.\"; ",
payload = {
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
}

#payload = json.dumps(job_script)

# Submit the job
response = requests.post(SLURM_API_URL, headers=HEADERS, json=payload)

#print("=====RESPONSE======")
#print(response.json())
#print("=========")

if response.status_code == 200:
    print("Job submitted successfully!")
    print(json.dumps(response.json(), indent=4))

    data = response.json() # Convert to JSON dictionary

    jid = data['job_id']
    print(f"New Job_ID: {jid}")
else:
    print(f"Failed to submit job: {response.status_code} {response.text}")

print("Done")
