# V0042RollupStatsMonthly


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**count** | **int** | Number of monthly rollups since last_run | [optional] 
**last_run** | **int** | Last time monthly rollup ran (UNIX timestamp) | [optional] 
**duration** | [**V0042RollupStatsMonthlyDuration**](V0042RollupStatsMonthlyDuration.md) |  | [optional] 

## Example

```python
from openapi_client.models.v0042_rollup_stats_monthly import V0042RollupStatsMonthly

# TODO update the JSON string below
json = "{}"
# create an instance of V0042RollupStatsMonthly from a JSON string
v0042_rollup_stats_monthly_instance = V0042RollupStatsMonthly.from_json(json)
# print the JSON string representation of the object
print(V0042RollupStatsMonthly.to_json())

# convert the object into a dict
v0042_rollup_stats_monthly_dict = v0042_rollup_stats_monthly_instance.to_dict()
# create an instance of V0042RollupStatsMonthly from a dict
v0042_rollup_stats_monthly_from_dict = V0042RollupStatsMonthly.from_dict(v0042_rollup_stats_monthly_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


