# V0041OpenapiSlurmdbdJobsRespJobsInnerDerivedExitCode

Highest exit code of all job steps

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**status** | **List[str]** | Status given by return code | [optional] 
**return_code** | [**V0041OpenapiSlurmdbdJobsRespJobsInnerDerivedExitCodeReturnCode**](V0041OpenapiSlurmdbdJobsRespJobsInnerDerivedExitCodeReturnCode.md) |  | [optional] 
**signal** | [**V0041OpenapiSlurmdbdJobsRespJobsInnerDerivedExitCodeSignal**](V0041OpenapiSlurmdbdJobsRespJobsInnerDerivedExitCodeSignal.md) |  | [optional] 

## Example

```python
from openapi_client.models.v0041_openapi_slurmdbd_jobs_resp_jobs_inner_derived_exit_code import V0041OpenapiSlurmdbdJobsRespJobsInnerDerivedExitCode

# TODO update the JSON string below
json = "{}"
# create an instance of V0041OpenapiSlurmdbdJobsRespJobsInnerDerivedExitCode from a JSON string
v0041_openapi_slurmdbd_jobs_resp_jobs_inner_derived_exit_code_instance = V0041OpenapiSlurmdbdJobsRespJobsInnerDerivedExitCode.from_json(json)
# print the JSON string representation of the object
print(V0041OpenapiSlurmdbdJobsRespJobsInnerDerivedExitCode.to_json())

# convert the object into a dict
v0041_openapi_slurmdbd_jobs_resp_jobs_inner_derived_exit_code_dict = v0041_openapi_slurmdbd_jobs_resp_jobs_inner_derived_exit_code_instance.to_dict()
# create an instance of V0041OpenapiSlurmdbdJobsRespJobsInnerDerivedExitCode from a dict
v0041_openapi_slurmdbd_jobs_resp_jobs_inner_derived_exit_code_from_dict = V0041OpenapiSlurmdbdJobsRespJobsInnerDerivedExitCode.from_dict(v0041_openapi_slurmdbd_jobs_resp_jobs_inner_derived_exit_code_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


