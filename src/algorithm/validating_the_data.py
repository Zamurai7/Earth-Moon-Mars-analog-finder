import numpy as np
import pandas as pd

# We reuse the ranking code from the main file
from knn_analogs import BODIES, GROUP_WEIGHTS, TOP_N, load, rank_sites

CHANGE = 0.20               # how much we move each weight (20%)
STABLE_MIN_OVERLAP = 8      # at least 8 of the original top 10 must stay in the top 10 to call it "stable"


def get_top10_ids(ranked):
    """Return the site ids of the top 10 sites."""
    ids = []
    for _, row in ranked.head(TOP_N).iterrows():
        ids.append(int(row["site_id"]))
    return ids


def get_rank_lookup(ranked):
    """Return a dictionary: site_id -> rank."""
    lookup = {}
    for _, row in ranked.iterrows():
        lookup[int(row["site_id"])] = int(row["rank"])
    return lookup


def get_status_lookup(ranked):
    """Return a dictionary: site_id -> status (Recommended / Acceptable / Not recommended)."""
    lookup = {}
    for _, row in ranked.iterrows():
        lookup[int(row["site_id"])] = row["status"]
    return lookup


def make_changed_weights(group_to_change, change):
    """
    Copy the normal group weights, change one of them, then rescale
    so that all the weights add up to 1 again.
    Example: temperature 0.30 with -20% becomes 0.24; the total is then 0.94,
    so every weight is divided by 0.94.
    """
    new_weights = dict(GROUP_WEIGHTS)
    new_weights[group_to_change] = new_weights[group_to_change] * (1 + change)

    total = 0
    for group_name in new_weights:
        total = total + new_weights[group_name]

    for group_name in new_weights:
        new_weights[group_name] = new_weights[group_name] / total
    return new_weights


def main():
    earth, ref, median, iqr = load()

    summary_rows = []        # one row per test
    stability_tables = []    # one table per body

    for body in BODIES:

        # ---- the original ranking (normal weights) ----
        base = rank_sites(earth, ref, body, median, iqr)
        base_ranks = get_rank_lookup(base)
        base_status = get_status_lookup(base)
        base_top10 = get_top10_ids(base)
        base_first_site = int(base.iloc[0]["site_id"])
        all_site_ids = list(base["site_id"])          # all ids, in original rank order

        all_scenario_ranks = [base_ranks]             # ranks from every test (original first)
        top10_counts = {}                             # site_id -> in how many tests it was top 10
        for site_id in all_site_ids:
            top10_counts[int(site_id)] = 0

        number_of_tests = 0

        # ---- change each weight group down and up ----
        for group_name in GROUP_WEIGHTS:
            for change in [-CHANGE, +CHANGE]:
                number_of_tests = number_of_tests + 1

                new_weights = make_changed_weights(group_name, change)
                new = rank_sites(earth, ref, body, median, iqr, new_weights)

                new_ranks = get_rank_lookup(new)
                new_status = get_status_lookup(new)
                new_top10 = get_top10_ids(new)
                all_scenario_ranks.append(new_ranks)

                for site_id in new_top10:
                    top10_counts[site_id] = top10_counts[site_id] + 1

                # How many of the original top 10 are still in the top 10?
                overlap = 0
                for site_id in base_top10:
                    if site_id in new_top10:
                        overlap = overlap + 1

                # Biggest rank change among the original top 10
                biggest_shift = 0
                for site_id in base_top10:
                    shift = abs(new_ranks[site_id] - base_ranks[site_id])
                    if shift > biggest_shift:
                        biggest_shift = shift

                # How many sites changed status?
                status_changes = 0
                for site_id in all_site_ids:
                    if new_status[int(site_id)] != base_status[int(site_id)]:
                        status_changes = status_changes + 1

                # How similar is the whole ranking? (1.0 = identical order)
                old_list = []
                new_list = []
                for site_id in all_site_ids:
                    old_list.append(base_ranks[int(site_id)])
                    new_list.append(new_ranks[int(site_id)])
                correlation = np.corrcoef(old_list, new_list)[0, 1]

                first_site = int(new.iloc[0]["site_id"])
                scenario_name = group_name + " " + format(change * 100, "+.0f") + "%"

                summary_rows.append({
                    "body": body,
                    "scenario": scenario_name,
                    "top10_overlap": overlap,
                    "top1_same": first_site == base_first_site,
                    "top1_name": new.iloc[0]["Name"],
                    "max_rank_shift_in_top10": biggest_shift,
                    "rank_correlation": round(float(correlation), 3),
                    "status_changes": status_changes,
                })

        # ---- stability of each site across all tests ----
        stability_rows = []
        for _, row in base.iterrows():
            site_id = int(row["site_id"])

            ranks_seen = []
            for scenario in all_scenario_ranks:
                ranks_seen.append(scenario[site_id])

            baseline_rank = base_ranks[site_id]
            times_in_top10 = top10_counts[site_id]

            # keep only sites that matter (top 20, or ever in a top 10)
            if baseline_rank <= 20 or times_in_top10 > 0:
                stability_rows.append({
                    "body": body,
                    "site_id": site_id,
                    "Name": row["Name"],
                    "baseline_rank": baseline_rank,
                    "best_rank": min(ranks_seen),
                    "worst_rank": max(ranks_seen),
                    "top10_in_scenarios": times_in_top10,
                    "always_top10": times_in_top10 == number_of_tests,
                })
        stability_tables.append(pd.DataFrame(stability_rows))

    # ---- save the files ----
    summary = pd.DataFrame(summary_rows)
    stability = pd.concat(stability_tables)
    summary.to_csv("validation_summary.csv", index=False)
    stability.to_csv("validation_site_stability.csv", index=False)

    # ---- print a report on screen ----
    pd.set_option("display.width", 200)
    for body in BODIES:
        body_summary = summary[summary["body"] == body]
        body_stability = stability[stability["body"] == body]

        worst_test = body_summary.loc[body_summary["top10_overlap"].idxmin()]
        top1_unchanged = int(body_summary["top1_same"].sum())

        print("\n=== " + body + " (weights moved by +-" + format(CHANGE, ".0%") + ", " +
              str(len(body_summary)) + " tests) ===")
        columns_to_show = ["scenario", "top10_overlap", "top1_same", "max_rank_shift_in_top10",
                           "rank_correlation", "status_changes"]
        print(body_summary[columns_to_show].to_string(index=False))
        print("Top-1 site unchanged in " + str(top1_unchanged) + "/" + str(len(body_summary)) + " tests")
        print("Lowest top-10 overlap: " + str(worst_test["top10_overlap"]) + "/" + str(TOP_N) +
              " (when " + worst_test["scenario"] + ")")

        always_names = []
        for _, row in body_stability.iterrows():
            if row["always_top10"]:
                always_names.append(row["Name"])
        print("Always in top 10 (" + str(len(always_names)) + "): " + ", ".join(always_names))

        if worst_test["top10_overlap"] >= STABLE_MIN_OVERLAP:
            print("Verdict: STABLE")
        else:
            print("Verdict: SENSITIVE to weights")


if __name__ == "__main__":
    main()
