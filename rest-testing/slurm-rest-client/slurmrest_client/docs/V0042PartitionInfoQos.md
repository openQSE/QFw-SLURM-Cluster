# V0042PartitionInfoQos


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**allowed** | **str** | AllowQOS | [optional] 
**deny** | **str** | DenyQOS | [optional] 
**assigned** | **str** | QOS | [optional] 

## Example

```python
from openapi_client.models.v0042_partition_info_qos import V0042PartitionInfoQos

# TODO update the JSON string below
json = "{}"
# create an instance of V0042PartitionInfoQos from a JSON string
v0042_partition_info_qos_instance = V0042PartitionInfoQos.from_json(json)
# print the JSON string representation of the object
print(V0042PartitionInfoQos.to_json())

# convert the object into a dict
v0042_partition_info_qos_dict = v0042_partition_info_qos_instance.to_dict()
# create an instance of V0042PartitionInfoQos from a dict
v0042_partition_info_qos_from_dict = V0042PartitionInfoQos.from_dict(v0042_partition_info_qos_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


