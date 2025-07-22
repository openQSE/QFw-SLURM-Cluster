# V0042JobComment


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**administrator** | **str** | Arbitrary comment made by administrator | [optional] 
**job** | **str** | Arbitrary comment made by user | [optional] 
**system** | **str** | Arbitrary comment from slurmctld | [optional] 

## Example

```python
from openapi_client.models.v0042_job_comment import V0042JobComment

# TODO update the JSON string below
json = "{}"
# create an instance of V0042JobComment from a JSON string
v0042_job_comment_instance = V0042JobComment.from_json(json)
# print the JSON string representation of the object
print(V0042JobComment.to_json())

# convert the object into a dict
v0042_job_comment_dict = v0042_job_comment_instance.to_dict()
# create an instance of V0042JobComment from a dict
v0042_job_comment_from_dict = V0042JobComment.from_dict(v0042_job_comment_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


