# V0042OpenapiMetaSlurm


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**version** | [**V0042OpenapiMetaSlurmVersion**](V0042OpenapiMetaSlurmVersion.md) |  | [optional] 
**release** | **str** | Slurm release string | [optional] 
**cluster** | **str** | Slurm cluster name | [optional] 

## Example

```python
from openapi_client.models.v0042_openapi_meta_slurm import V0042OpenapiMetaSlurm

# TODO update the JSON string below
json = "{}"
# create an instance of V0042OpenapiMetaSlurm from a JSON string
v0042_openapi_meta_slurm_instance = V0042OpenapiMetaSlurm.from_json(json)
# print the JSON string representation of the object
print(V0042OpenapiMetaSlurm.to_json())

# convert the object into a dict
v0042_openapi_meta_slurm_dict = v0042_openapi_meta_slurm_instance.to_dict()
# create an instance of V0042OpenapiMetaSlurm from a dict
v0042_openapi_meta_slurm_from_dict = V0042OpenapiMetaSlurm.from_dict(v0042_openapi_meta_slurm_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


