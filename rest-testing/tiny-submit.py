import requests
import json
import os

SLURM_API_URL = "http://localhost:6820/slurm/v0.0.39/job/submit"

if 'SLURM_JWT' in os.environ:
    MY_TOKEN = os.environ.get('SLURM_JWT')
    print(f"FOUND TOKEN IN ENV:\n {MY_TOKEN}")
else:
    MY_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJleHAiOjE3NDI5MzYzOTMsImlhdCI6MTc0MjkzNDU5Mywic3VuIjoic2dydW5keSJ9.HFZd56WeYMvX4jrx3D9OADo2TV24EOdIBFzZYNkXe2w"
    print(f"TRY A DEFAULT TOKEN:\n {MY_TOKEN}")


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

if response.status_code == 200:
    print("Job submitted successfully!")
    print(json.dumps(response.json(), indent=4))
    #data = json.loads(response.json())  # Convert JSON string to a dictionary
    data = response.json()
    jid = data['job_id']
    jstat = data['result']['error_code']
    print(f"DBG: Job_ID: {jid}  Job_Status: {jstat}  Response-Code: {response.status_code}")
else:
    print(f"Failed to submit job: {response.status_code} {response.text}")

print("Done")
