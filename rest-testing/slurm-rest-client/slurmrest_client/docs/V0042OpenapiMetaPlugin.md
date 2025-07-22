# V0042OpenapiMetaPlugin


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**type** | **str** | Slurm plugin type (if applicable) | [optional] 
**name** | **str** | Slurm plugin name (if applicable) | [optional] 
**data_parser** | **str** | Slurm data_parser plugin | [optional] 
**accounting_storage** | **str** | Slurm accounting plugin | [optional] 

## Example

```python
from openapi_client.models.v0042_openapi_meta_plugin import V0042OpenapiMetaPlugin

# TODO update the JSON string below
json = "{}"
# create an instance of V0042OpenapiMetaPlugin from a JSON string
v0042_openapi_meta_plugin_instance = V0042OpenapiMetaPlugin.from_json(json)
# print the JSON string representation of the object
print(V0042OpenapiMetaPlugin.to_json())

# convert the object into a dict
v0042_openapi_meta_plugin_dict = v0042_openapi_meta_plugin_instance.to_dict()
# create an instance of V0042OpenapiMetaPlugin from a dict
v0042_openapi_meta_plugin_from_dict = V0042OpenapiMetaPlugin.from_dict(v0042_openapi_meta_plugin_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


