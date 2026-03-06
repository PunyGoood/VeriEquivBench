import json
import sys
import os
import re
import hashlib

from subset_reward import *
from equiv_reward import *
from dafny_verifier import parallel_version_gt_score

METRICS_DIR = os.path.dirname(os.path.abspath(__file__))
output_dir = os.path.join(METRICS_DIR, "logs")
os.makedirs(output_dir, exist_ok=True)


def process_data(data_dir):
    """Load dafny_code_final.dfy from every code_*/rollout_* subfolder."""
    data_list = []
    for folder in os.listdir(data_dir):
        if not folder.startswith("code"):
            continue
        index = int(folder.split("_")[1])
        for rollout in os.listdir(os.path.join(data_dir, folder)):
            if not rollout.startswith("rollout"):
                continue
            fpath = os.path.join(data_dir, folder, rollout, "dafny_code_final.dfy")
            if not os.path.exists(fpath):
                continue
            with open(fpath, "r") as f:
                data = f.read()
            data_list.append({"index": index, "rollout": rollout, "data": data})
    return data_list


def gt_score(data_list, log_dir=None):
    """Score 3 — GT spec-to-code equivalence check."""
    gt_score_list = []
    for data in data_list:
        code = data["data"]
        try:
            new_dafny = create_spec_to_code_check(code)
            print(f"new_dafny: {new_dafny}")
        except Exception as e:
            print(f"Error in create_spec_to_code_check: {e}")
            new_dafny = None
        data["new_dafny"] = new_dafny
        gt_score_list.append({
            "index": data["index"],
            "rollout": data["rollout"],
            "data": data["data"],
            "new_dafny": new_dafny,
        })

    verify_ok_list, total_list = parallel_version_gt_score(
        command_def=["dafny"],
        dafny_codes=gt_score_list,
        code_field="new_dafny",
        log_file=os.path.join(output_dir, "veri_code.log"),
        max_workers=32,
        whole_list=True,
    )
    idx_total_list = {}
    for item in total_list:
        idx_total_list.setdefault(item["index"], []).append(item)

    score_list = []
    for items in idx_total_list.values():
        scores = []
        for item in items:
            if item["new_dafny"] is not None and re.search(r'method\s+\w+\s*\([^)]*\)', item["new_dafny"]):
                scores.append(item["parse_state"])
            else:
                scores.append(0)
        if log_dir and max(scores) == 1:
            for item in items:
                if item["parse_state"] == 1:
                    os.makedirs(os.path.join(log_dir, str(item["index"])), exist_ok=True)
                    with open(os.path.join(log_dir, str(item["index"]), item["rollout"] + ".dfy"), "w") as f:
                        f.write(item["new_dafny"])
        score_list.append(max(scores))

    total_items = len(score_list)
    passed_items = sum(score_list)
    pct = passed_items / total_items if total_items > 0 else 0
    print(f"GT verification: {passed_items} out of {total_items} items ({pct:.2%}) passed the parse check.")


def subset_reward(data_list):
    """Score 4 — subset specification reward.

    Uses create_subset_check(gt_code, gen_code) to produce a Dafny file
    that checks whether the LLM specs are a valid subset of the GT specs,
    then runs verification via parallel_version_gt_score.
    """
    idx_data_list = {}
    for item in data_list:
        idx_data_list.setdefault(item["index"], []).append(item)

    subset_score_list = []
    gt_file = os.path.join(METRICS_DIR, "opt_216_comp_items.json")
    if not os.path.exists(gt_file):
        print(f"WARNING: GT file not found at {gt_file}, skipping subset_reward.")
        return

    with open(gt_file, "r") as f:
        gt_data = json.load(f)

    index_gt_data = {}
    for item in gt_data:
        label = item["gt_no_comment"]
        label = re.search(r'method\s+\w+\s*\([^)]*\)', label).group(0)
        label = hashlib.sha256(label.encode()).hexdigest()
        index_gt_data[label] = item["gt_no_comment"]

    # Build subset-check Dafny code for each sample
    subset_codes = []
    for idx, items in idx_data_list.items():
        match_string = items[0]["data"]
        match = re.search(r'method\s+\w+\s*\([^)]*\)', match_string)
        if match:
            match_string = match.group(0)
        else:
            continue
        match_string = hashlib.sha256(match_string.encode()).hexdigest()
        if match_string not in index_gt_data:
            continue
        gt_code = index_gt_data[match_string]

        for item in items:
            try:
                new_dafny = create_subset_check(gt_code, item["data"])
            except Exception as e:
                print(f"Error in create_subset_check: {e}")
                new_dafny = None
            subset_codes.append({
                "index": item["index"],
                "rollout": item["rollout"],
                "data": item["data"],
                "new_dafny": new_dafny,
            })

    if not subset_codes:
        print("No subset reward data to verify.")
        return

    verify_ok_list, total_list = parallel_version_gt_score(
        command_def=["dafny"],
        dafny_codes=subset_codes,
        code_field="new_dafny",
        log_file=os.path.join(output_dir, "subset_check.log"),
        max_workers=32,
        whole_list=True,
    )

    idx_total_list = {}
    for item in total_list:
        idx_total_list.setdefault(item["index"], []).append(item)

    for items in idx_total_list.values():
        scores = []
        for item in items:
            if item["new_dafny"] is not None:
                scores.append(item.get("parse_state", 0))
            else:
                scores.append(0)
        if scores:
            subset_score_list.append(max(scores))

    total_items = len(subset_score_list)
    passed_items = sum(subset_score_list)
    pct = passed_items / total_items if total_items > 0 else 0
    print(f"Subset verification: {passed_items} out of {total_items} items ({pct:.2%}) passed the parse check.")
