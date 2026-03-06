"""
subset_reward.py — Dafny subset specification reward.

Key function: strip_specs_and_inject_asserts(gt_code, ex_code, key)
  Returns modified Dafny code that, when verified, checks whether the
  LLM-generated specifications are a valid subset of the ground truth.
  (Re-exported from spec_utils.)

Also provides execute_diff_location() for running Dafny on the result.
"""

import re
import os
import random
import hashlib

from dafny_parser import *
from spec_utils import *
from concurrent.futures import ThreadPoolExecutor, as_completed
from equiv_reward import *


def create_subset_check(gt_code, gen_code):
    return strip_specs_and_inject_asserts(gt_code, gen_code, "one_score")


def no_only_ensures_equiv_for_any_method(complete_code):
    """Check that no method has only a self-equivalent ensures clause."""
    equiv_pattern = re.compile(r'\s*(\w+)\s*==\s*\1\s*')
    specs = extract_specs(complete_code)
    for key, value in specs.items():
        if len(value['ensures']) == 1 and equiv_pattern.search(value["ensures"][0]):
            return False
    return True


def check_no_cheat_by_ensure_true(complete_code):
    """Check that code does not cheat by using 'ensures true' or 'ensures false'."""
    complete_ensures = extract_tosearch(complete_code, r'ensures\s+(true|false)')
    if len(complete_ensures) != 0:
        return False
    return True