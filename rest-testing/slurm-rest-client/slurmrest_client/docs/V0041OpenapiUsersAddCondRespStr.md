# V0041OpenapiUsersAddCondRespStr


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**added_users** | **str** | added_users | 
**meta** | [**V0041OpenapiSlurmdbdJobsRespMeta**](V0041OpenapiSlurmdbdJobsRespMeta.md) |  | [optional] 
**errors** | [**List[V0041OpenapiSlurmdbdJobsRespErrorsInner]**](V0041OpenapiSlurmdbdJobsRespErrorsInner.md) | Query errors | [optional] 
**warnings** | [**List[V0041OpenapiSlurmdbdJobsRespWarningsInner]**](V0041OpenapiSlurmdbdJobsRespWarningsInner.md) | Query warnings | [optional] 

## Example

```python
from openapi_client.models.v0041_openapi_users_add_cond_resp_str import V0041OpenapiUsersAddCondRespStr

# TODO update the JSON string below
json = "{}"
# create an instance of V0041OpenapiUsersAddCondRespStr from a JSON string
v0041_openapi_users_add_cond_resp_str_instance = V0041OpenapiUsersAddCondRespStr.from_json(json)
# print the JSON string representation of the object
print(V0041OpenapiUsersAddCondRespStr.to_json())

# convert the object into a dict
v0041_openapi_users_add_cond_resp_str_dict = v0041_openapi_users_add_cond_resp_str_instance.to_dict()
# create an instance of V0041OpenapiUsersAddCondRespStr from a dict
v0041_openapi_users_add_cond_resp_str_from_dict = V0041OpenapiUsersAddCondRespStr.from_dict(v0041_openapi_users_add_cond_resp_str_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


