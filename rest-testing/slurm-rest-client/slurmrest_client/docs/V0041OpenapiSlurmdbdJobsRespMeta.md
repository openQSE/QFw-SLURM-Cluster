# V0041OpenapiSlurmdbdJobsRespMeta

Slurm meta values

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**plugin** | [**V0042OpenapiMetaPlugin**](V0042OpenapiMetaPlugin.md) |  | [optional] 
**client** | [**V0042OpenapiMetaClient**](V0042OpenapiMetaClient.md) |  | [optional] 
**command** | **List[str]** | CLI command (if applicable) | [optional] 
**slurm** | [**V0042OpenapiMetaSlurm**](V0042OpenapiMetaSlurm.md) |  | [optional] 

## Example

```python
from openapi_client.models.v0041_openapi_slurmdbd_jobs_resp_meta import V0041OpenapiSlurmdbdJobsRespMeta

# TODO update the JSON string below
json = "{}"
# create an instance of V0041OpenapiSlurmdbdJobsRespMeta from a JSON string
v0041_openapi_slurmdbd_jobs_resp_meta_instance = V0041OpenapiSlurmdbdJobsRespMeta.from_json(json)
# print the JSON string representation of the object
print(V0041OpenapiSlurmdbdJobsRespMeta.to_json())

# convert the object into a dict
v0041_openapi_slurmdbd_jobs_resp_meta_dict = v0041_openapi_slurmdbd_jobs_resp_meta_instance.to_dict()
# create an instance of V0041OpenapiSlurmdbdJobsRespMeta from a dict
v0041_openapi_slurmdbd_jobs_resp_meta_from_dict = V0041OpenapiSlurmdbdJobsRespMeta.from_dict(v0041_openapi_slurmdbd_jobs_resp_meta_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


