import requests
import json

SLURM_API_URL = "http://localhost:6820/slurm/v0.0.39/job/submit"

MY_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJleHAiOjE3NDI5MTkxODUsImlhdCI6MTc0MjkxNzM4NSwic3VuIjoic2dydW5keSJ9.Yxx0YujM8NaWDonddVekPuLWSxLZelcImHEHnAblYZQ"


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
else:
    print(f"Failed to submit job: {response.status_code} {response.text}")

print("Done")
