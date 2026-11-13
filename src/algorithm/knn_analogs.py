import os
import json
import numpy as np
import pandas as pd

# Make sure the script always looks for its files in its own folder
os.chdir(os.path.dirname(os.path.abspath(__file__)))


# ======================================================================
# SETTINGS - change the numbers here if you want different behaviour
# ======================================================================

EARTH_FILE = "Earths_Locations_clean.csv"
REF_FILE = "moon_mars_reference_clean.csv"

BODIES = ["Moon", "Mars"]

TOP_N = 10                  # how many sites are in the "top" list
CAP = 3.0                   # largest allowed scaled value (stops one extreme number from dominating)
RATIO_RECOMMENDED = 1.10    # distance within 10% of the best site  -> Recommended
RATIO_ACCEPTABLE = 1.20     # distance within 20% of the best site  -> Acceptable (further = Not recommended)
WEAK_FRACTION = 0.85        # a condition is "weak" if the site is in the worst 15% of all sites on it

# How important each group of conditions is (must add up to 1.0)
GROUP_WEIGHTS = {
    "temperature": 0.30,
    "atmosphere": 0.25,
    "radiation": 0.25,
    "moisture": 0.15,
    "terrain": 0.05,
}

# Which columns belong to which group
GROUP_FEATURES = {
    "temperature": ["temp_avg", "temp_max", "temp_min"],
    "atmosphere": ["pressure", "wind"],
    "radiation": ["solar_radiation", "uv_index"],
    "moisture": ["humidity", "rainfall"],
    "terrain": ["elevation"],
}

# One flat list with all 10 condition columns
FEATURES = []
for group_name in GROUP_FEATURES:
    for feature in GROUP_FEATURES[group_name]:
        FEATURES.append(feature)


# ======================================================================
# STEP 1: LOADING AND PREPARING THE DATA
# ======================================================================

def load():
    """Read both files and work out how to scale the data."""
    earth = pd.read_csv(EARTH_FILE)
    ref = pd.read_csv(REF_FILE)
    ref = ref.set_index("body")          # now we can ask for ref.loc["Moon"] or ref.loc["Mars"]

    # The "typical" value and the "spread" of each condition, measured on Earth only
    median = earth[FEATURES].median()
    q25 = earth[FEATURES].quantile(0.25)
    q75 = earth[FEATURES].quantile(0.75)
    iqr = q75 - q25                      # spread of the middle 50% of the sites

    return earth, ref, median, iqr


def get_feature_weights(group_weights=GROUP_WEIGHTS):
    """
    Turn group weights into one weight per column.
    A group's weight is split equally between its columns.
    Example: temperature = 0.30 and has 3 columns, so each column gets 0.10.
    """
    weights = []
    for group_name in GROUP_FEATURES:
        columns = GROUP_FEATURES[group_name]
        weight_per_column = group_weights[group_name] / len(columns)
        for column in columns:
            weights.append(weight_per_column)
    return np.array(weights)


def scale(table, median, iqr, use_cap=True):
    """
    Put the conditions on a comparable scale.
    Each value becomes "how many spreads away from the typical Earth value it is".
    If use_cap is True, values are limited to between -CAP and +CAP.
    """
    scaled = (table[FEATURES] - median) / iqr
    if use_cap:
        scaled = scaled.clip(-CAP, CAP)
    return scaled.to_numpy()


# ======================================================================
# STEP 2: RANKING THE SITES (the kNN part)
# ======================================================================

def rank_sites(earth, ref, body, median, iqr, group_weights=GROUP_WEIGHTS):
    """
    Measure how close every Earth site is to one body (Moon or Mars)
    and return ALL sites sorted from closest to furthest.
    """
    weights = get_feature_weights(group_weights)

    earth_scaled = scale(earth, median, iqr)                 # table: 187 sites x 10 conditions
    body_scaled = scale(ref.loc[[body]], median, iqr)[0]     # the 10 values of the Moon (or Mars)

    # Weighted distance, step by step:
    differences = earth_scaled - body_scaled     # difference on every condition
    squared = differences ** 2                   # square it so negatives don't cancel positives
    weighted = weights * squared                 # important conditions count more
    totals = weighted.sum(axis=1)                # add the 10 conditions together for each site
    distances = np.sqrt(totals)                  # square root = the final distance

    best_distance = distances.min()

    # Decide the status of each site
    statuses = []
    for distance in distances:
        if distance <= best_distance * RATIO_RECOMMENDED:
            statuses.append("Recommended")
        elif distance <= best_distance * RATIO_ACCEPTABLE:
            statuses.append("Acceptable")
        else:
            statuses.append("Not recommended")

    result = earth.copy()
    result.insert(0, "site_id", range(1, len(earth) + 1))    # a fixed id for every site
    result["distance"] = distances
    result["similarity_score"] = 100 * best_distance / distances   # best site = 100
    result["status"] = statuses

    result = result.sort_values("distance", kind="stable")   # closest first
    result = result.reset_index(drop=True)
    result.insert(0, "rank", range(1, len(result) + 1))      # rank 1 = closest
    result["in_top10"] = result["rank"] <= TOP_N
    return result


# ======================================================================
# STEP 3: WARNINGS
# ======================================================================

def add_warnings(ranked, ref, body, median, iqr):
    """
    A site can be close overall but still be bad on one condition
    (for example the right temperature but a very high elevation).
    This adds warning columns that point those weak conditions out.
    """
    # Scaled values WITHOUT the cap, so small differences are not hidden
    sites_scaled = scale(ranked, median, iqr, use_cap=False)
    body_scaled = scale(ref.loc[[body]], median, iqr, use_cap=False)[0]

    # For each condition: how far is each site from the body?
    gaps = np.abs(sites_scaled - body_scaled)
    gap_table = pd.DataFrame(gaps, columns=FEATURES)

    # Turn the gaps into positions between 0 and 1.
    # 0.90 means "further away than 90% of all sites on this condition".
    position = gap_table.rank(pct=True)

    levels = []
    weak_names = []
    texts = []
    details = []

    for i, row in ranked.iterrows():

        # 1) find the conditions where this site is in the worst 15%
        weak = []
        for feature in FEATURES:
            if position.at[i, feature] > WEAK_FRACTION:
                weak.append(feature)

        # 2) order them from the weakest to the least weak
        ordered = []
        remaining = list(weak)
        while len(remaining) > 0:
            worst = remaining[0]
            for feature in remaining:
                if position.at[i, feature] > position.at[i, worst]:
                    worst = feature
            ordered.append(worst)
            remaining.remove(worst)
        weak = ordered

        # 3) collect the numbers for each weak condition
        info = []
        for feature in weak:
            info.append({
                "feature": feature,
                "site_value": round(float(row[feature]), 3),
                "reference_value": round(float(ref.at[body, feature]), 3),
            })

        # 4) decide the warning level
        if row["status"] == "Not recommended":
            level = "n/a"
            text = "Not recommended overall"
        elif len(weak) == 0:
            level = "none"
            text = ""
        else:
            # count in how many different groups the weak conditions are
            groups_with_weakness = 0
            for group_name in GROUP_FEATURES:
                group_is_weak = False
                for feature in GROUP_FEATURES[group_name]:
                    if feature in weak:
                        group_is_weak = True
                if group_is_weak:
                    groups_with_weakness = groups_with_weakness + 1

            if groups_with_weakness >= 2:
                level = "high"
            else:
                level = "caution"

            pieces = []
            for item in info:
                piece = (item["feature"] + " (site " + str(item["site_value"]) +
                         " vs " + body + " " + str(item["reference_value"]) + ")")
                pieces.append(piece)
            text = "Weak on: " + ", ".join(pieces)

        levels.append(level)
        weak_names.append("; ".join(weak))
        texts.append(text)
        details.append(info)

    ranked["warning_level"] = levels
    ranked["weak_conditions"] = weak_names
    ranked["warning_text"] = texts
    ranked["_weak_details"] = details      # temporary column, only used for the JSON file
    return ranked


# ======================================================================
# STEP 4: WHERE DOES "NOT RECOMMENDED" START?
# ======================================================================

def cutoff_info(ranked):
    """Count the statuses and find the exact rank where 'Not recommended' begins."""
    best_distance = ranked["distance"].min()
    cutoff_distance = best_distance * RATIO_ACCEPTABLE

    recommended = int((ranked["status"] == "Recommended").sum())
    acceptable = int((ranked["status"] == "Acceptable").sum())
    not_recommended = int((ranked["status"] == "Not recommended").sum())
    usable = recommended + acceptable

    return {
        "recommended": recommended,
        "acceptable": acceptable,
        "not_recommended": not_recommended,
        "last_usable_rank": usable,
        "first_not_recommended_rank": usable + 1,
        "cutoff_distance": round(float(cutoff_distance), 4),
    }


# ======================================================================
# STEP 5: SANITY CHECK
# ======================================================================

def sanity_check(earth, median, iqr):
    """
    Checks the kNN makes sense: for each Earth site we hide its label,
    look at its K nearest neighbours, and guess Moon/Mars by majority vote.
    """
    weights = get_feature_weights()
    earth_scaled = scale(earth, median, iqr)
    labels = earth["AnalogBody"].to_numpy()

    print("\nSanity check (guessing the Moon/Mars label of each Earth site from its neighbours):")
    for k in [3, 5, 7, 9, 11]:
        correct = 0
        for i in range(len(earth_scaled)):
            distances = np.sqrt((weights * (earth_scaled - earth_scaled[i]) ** 2).sum(axis=1))
            distances[i] = np.inf                         # ignore the site itself
            nearest = np.argsort(distances)[:k]           # positions of the k closest sites

            moon_votes = 0
            for position in nearest:
                if labels[position] == "Moon":
                    moon_votes = moon_votes + 1

            if moon_votes > k / 2:
                guess = "Moon"
            else:
                guess = "Mars"

            if guess == labels[i]:
                correct = correct + 1
        print("  K=" + str(k) + ": " + format(correct / len(earth_scaled), ".1%"))

    moon_share = np.mean(labels == "Moon")
    mars_share = np.mean(labels == "Mars")
    print("  (always guessing the majority label: " + format(max(moon_share, mars_share), ".1%") + ")")


# ======================================================================
# MAIN PROGRAM
# ======================================================================

def main():
    earth, ref, median, iqr = load()

    all_tables = []          # one ranked table per body, joined at the end
    json_data = {
        "settings": {
            "top_n": TOP_N,
            "group_weights": GROUP_WEIGHTS,
            "recommended_within": RATIO_RECOMMENDED,
            "acceptable_within": RATIO_ACCEPTABLE,
            "weak_condition_worst_fraction": round(1 - WEAK_FRACTION, 2),
        },
        "targets": {},
    }

    for body in BODIES:
        # rank all sites, then add warnings and the cutoff
        ranked = rank_sites(earth, ref, body, median, iqr)
        ranked = add_warnings(ranked, ref, body, median, iqr)
        cutoff = cutoff_info(ranked)

        # ---- build the list of sites for the JSON file ----
        sites = []
        for _, row in ranked.iterrows():
            conditions = {}
            for feature in FEATURES:
                conditions[feature] = round(float(row[feature]), 3)

            sites.append({
                "rank": int(row["rank"]),
                "site_id": int(row["site_id"]),
                "name": row["Name"],
                "analog_type": row["AnalogType"],
                "labeled_as": row["AnalogBody"],
                "lat": float(row["Lat"]),
                "lon": float(row["Lon"]),
                "distance": round(float(row["distance"]), 4),
                "similarity_score": round(float(row["similarity_score"]), 1),
                "status": row["status"],
                "in_top10": bool(row["in_top10"]),
                "warning_level": row["warning_level"],
                "warning_text": row["warning_text"],
                "weak_conditions": row["_weak_details"],
                "conditions": conditions,
            })

        reference_conditions = {}
        for feature in FEATURES:
            reference_conditions[feature] = float(ref.at[body, feature])

        json_data["targets"][body] = {
            "reference_conditions": reference_conditions,
            "cutoff": cutoff,
            "sites": sites,
        }

        # ---- table for the CSV files ----
        table = ranked.drop(columns="_weak_details")
        table.insert(0, "target", body)
        all_tables.append(table)

        # ---- print a short report on screen ----
        print("\n=== " + body + ": top " + str(TOP_N) + " ===")
        columns_to_show = ["rank", "Name", "similarity_score", "status", "warning_level"]
        print(ranked.head(TOP_N)[columns_to_show].round(1).to_string(index=False))
        print(body + " cutoff -> Recommended: " + str(cutoff["recommended"]) +
              ", Acceptable: " + str(cutoff["acceptable"]) +
              ", Not recommended: " + str(cutoff["not_recommended"]))
        print("  NOT recommended from rank " + str(cutoff["first_not_recommended_rank"]) +
              " (distance above " + str(cutoff["cutoff_distance"]) + ")")
        caution_count = int((ranked["warning_level"] == "caution").sum())
        high_count = int((ranked["warning_level"] == "high").sum())
        print("  Warnings among usable sites -> caution: " + str(caution_count) +
              ", high: " + str(high_count))

    # ---- save the files ----
    full = pd.concat(all_tables)
    column_order = ["target", "rank", "site_id", "Name", "AnalogType", "AnalogBody", "Lat", "Lon",
                    "distance", "similarity_score", "status", "in_top10", "warning_level",
                    "weak_conditions", "warning_text"]
    for feature in FEATURES:
        column_order.append(feature)
    full = full[column_order]
    full = full.round({"distance": 4, "similarity_score": 1})

    full.to_csv("all_results.csv", index=False)                       # every site, both bodies
    full[full["in_top10"]].to_csv("top10_results.csv", index=False)   # only the top 10 of each body

    with open("results.json", "w") as json_file:                      # file for the app developer
        json.dump(json_data, json_file, indent=2)

    sanity_check(earth, median, iqr)


if __name__ == "__main__":
    main()
