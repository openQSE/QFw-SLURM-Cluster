# V0042PartitionInfoNodes


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**allowed_allocation** | **str** | AllocNodes | [optional] 
**configured** | **str** | Nodes | [optional] 
**total** | **int** | TotalNodes | [optional] 

## Example

```python
from openapi_client.models.v0042_partition_info_nodes import V0042PartitionInfoNodes

# TODO update the JSON string below
json = "{}"
# create an instance of V0042PartitionInfoNodes from a JSON string
v0042_partition_info_nodes_instance = V0042PartitionInfoNodes.from_json(json)
# print the JSON string representation of the object
print(V0042PartitionInfoNodes.to_json())

# convert the object into a dict
v0042_partition_info_nodes_dict = v0042_partition_info_nodes_instance.to_dict()
# create an instance of V0042PartitionInfoNodes from a dict
v0042_partition_info_nodes_from_dict = V0042PartitionInfoNodes.from_dict(v0042_partition_info_nodes_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


