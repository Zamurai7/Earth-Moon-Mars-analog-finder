# Analog Finder – Output Format (for app development)

The algorithm (`knn_analogs.py`) writes three files. They contain the same data in different shapes.
Every Earth site is ranked **twice**: once against Moon conditions and once against Mars conditions.

| File | Use it for |
|---|---|
| `results.json` | Main file for the app (nested, one list per body) |
| `all_results.csv` | Every site, both bodies (374 rows = 187 sites x 2) |
| `top10_results.csv` | Only the top 10 per body (20 rows) |

## results.json

```
{
  "settings": { top_n, group_weights{}, recommended_within, acceptable_within, weak_condition_worst_fraction },
  "targets": {
    "Moon": { "reference_conditions": {...}, "cutoff": {...}, "sites": [ ... ] },
    "Mars": { same structure }
  }
}
```

### targets.<Body>.cutoff  (where "not recommended" starts)
| Field | Meaning |
|---|---|
| recommended / acceptable / not_recommended | number of sites in each status |
| last_usable_rank | last rank that is still Recommended or Acceptable |
| first_not_recommended_rank | rank where "Not recommended" begins |
| cutoff_distance | distance value above which a site is Not recommended |

### targets.<Body>.sites[]  (sorted by rank, 1 = closest; 187 entries)
| Field | Type | Meaning |
|---|---|---|
| rank | int | 1 = closest to the body's conditions |
| site_id | int | Stable id of the Earth site (row number in Earths_Locations_clean.csv) |
| name, analog_type | string | Site name and type (Impact Crater, Dunes, Volcanic Eruption) |
| labeled_as | "Moon" / "Mars" | The label from the original data (not the result) |
| lat, lon | float | Coordinates |
| distance | float | Weighted distance to the body (lower = closer) |
| similarity_score | float | 100 x (best distance / this distance). Best site = 100 |
| status | string | "Recommended" (within 10% of best), "Acceptable" (within 20%), "Not recommended" (beyond) |
| in_top10 | bool | true for ranks 1-10 |
| warning_level | string | "none", "caution" (weak in 1 condition group), "high" (weak in 2+ groups), "n/a" (site is Not recommended) |
| warning_text | string | Human-readable warning, empty if none |
| weak_conditions[] | list | `{feature, site_value, reference_value}` for each weak condition |
| conditions{} | object | The 10 condition values of the site |

Condition keys: temp_avg, temp_max, temp_min, pressure, wind, solar_radiation, uv_index, humidity, rainfall, elevation.
Units: temperature degC, pressure kPa, wind m/s, solar_radiation W/m2, humidity %, rainfall mm/day, elevation m.

## CSV columns
`all_results.csv` and `top10_results.csv` share the same columns:
target (Moon/Mars), rank, site_id, Name, AnalogType, AnalogBody (original label), Lat, Lon, distance,
similarity_score, status, in_top10, warning_level, weak_conditions (names joined by "; "), warning_text,
then the 10 condition columns.

## Suggested UI logic
- Show top 10: filter `in_top10 == true` (or load `top10_results.csv`).
- Show all: list every site, grey out `status == "Not recommended"`.
- Show a badge from `warning_level` and the `warning_text` on tap.

## Validation files (internal, not needed by the app)
- `validation_summary.csv`: how the ranking changes when each weight is moved by +-20%.
- `validation_site_stability.csv`: best/worst rank each site reaches under those changes.
