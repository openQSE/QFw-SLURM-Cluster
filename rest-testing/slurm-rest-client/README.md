
Steps
----

 1. Get OpenAPI schema
    ```
    ./curl-get-openapi-json.sh
    ```

 2. Generate client from schema
    ```
      openapi-generator generate \
            -i slurm_openapi.json \
            -g python \
            -o slurmrest_client
    ```

 3. Install generated client (in edit/devel mode)
    ```
       # Create/activate virtual env
      python3 -m venv venv
      source venv/bin/activate
    ```
    ```
      cd slurmrest_client
      pip install -e .
    ```

 4. Use genreated client
    ```
      from slurmrest_client import ApiClient, Configuration
      from slurmrest_client.api.job_api import JobApi

      # Configure API client (modify host if needed)
      config = Configuration(host="http://localhost:6820")
      client = ApiClient(configuration=config)

      # Initialize API instance
      job_api = JobApi(client)

      # Get job list
      jobs = job_api.get_jobs()
      print(jobs)

    ```

 5. Submit a job
    ```
     from slurmrest_client.models import JobSubmitRequest

     job_request = JobSubmitRequest(script="echo Hello, Slurm!")
     response = job_api.submit_job(job_request)
     print(response)

    ```

 6. Authentication
    ```
      config.api_key['X-SLURM-USER-TOKEN'] = 'your_token_here'
    ```

 7. See full API
    ```
     dir(job_api)
    ```

