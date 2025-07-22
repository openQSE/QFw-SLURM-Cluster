# V0042RollupStats


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**hourly** | [**V0042RollupStatsHourly**](V0042RollupStatsHourly.md) |  | [optional] 
**daily** | [**V0042RollupStatsDaily**](V0042RollupStatsDaily.md) |  | [optional] 
**monthly** | [**V0042RollupStatsMonthly**](V0042RollupStatsMonthly.md) |  | [optional] 

## Example

```python
from openapi_client.models.v0042_rollup_stats import V0042RollupStats

# TODO update the JSON string below
json = "{}"
# create an instance of V0042RollupStats from a JSON string
v0042_rollup_stats_instance = V0042RollupStats.from_json(json)
# print the JSON string representation of the object
print(V0042RollupStats.to_json())

# convert the object into a dict
v0042_rollup_stats_dict = v0042_rollup_stats_instance.to_dict()
# create an instance of V0042RollupStats from a dict
v0042_rollup_stats_from_dict = V0042RollupStats.from_dict(v0042_rollup_stats_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


