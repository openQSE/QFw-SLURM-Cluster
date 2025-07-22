# V0042KillJobsRespJobError


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**string** | **str** | String error encountered signaling job | [optional] 
**code** | **int** | Numeric error encountered signaling job | [optional] 
**message** | **str** | Error message why signaling job failed | [optional] 

## Example

```python
from openapi_client.models.v0042_kill_jobs_resp_job_error import V0042KillJobsRespJobError

# TODO update the JSON string below
json = "{}"
# create an instance of V0042KillJobsRespJobError from a JSON string
v0042_kill_jobs_resp_job_error_instance = V0042KillJobsRespJobError.from_json(json)
# print the JSON string representation of the object
print(V0042KillJobsRespJobError.to_json())

# convert the object into a dict
v0042_kill_jobs_resp_job_error_dict = v0042_kill_jobs_resp_job_error_instance.to_dict()
# create an instance of V0042KillJobsRespJobError from a dict
v0042_kill_jobs_resp_job_error_from_dict = V0042KillJobsRespJobError.from_dict(v0042_kill_jobs_resp_job_error_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


