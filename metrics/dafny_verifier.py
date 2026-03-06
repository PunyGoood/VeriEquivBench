"""
dafny_verifier.py — GT score Dafny verification helper.

Copied from wash_data/cot_sft_data/process_score.py so that the
metrics/ folder has zero imports outside itself.
"""

import re
import os
import logging
from typing import List, Dict

import tempfile
import subprocess
import functools
from concurrent.futures import ThreadPoolExecutor, as_completed


def dafny_verify_gt_score(
        command_def: list[str],
        dafny_dict: dict,
        code_field: str = 'code_processed',
        log_file: str = None) -> str:
    """
    Two-pass verification for GT score:
    1. Try `dafny verify <file>`
    2. Fallback to `dafny <file>`
    """
    if log_file:
        logging.basicConfig(
            filename=log_file,
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            filemode='a'
        )
    else:
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )

    with tempfile.NamedTemporaryFile(suffix='.dfy', delete=False) as temp_file:
        temp_file.write(dafny_dict[code_field].encode('utf-8'))
        dafny_file = temp_file.name
        logging.info(f"Created temporary file: {dafny_file}")
    try:
        cmd_2 = command_def + ["verify"] + [dafny_file]
        logging.info(f"Running command: {' '.join(cmd_2)}")
        result_2 = subprocess.run(
            cmd_2,
            capture_output=True,
            text=True,
            check=True,
            timeout=60
        )
        if re.search(" 0 error", result_2.stdout):
            dafny_dict['v_state'] = 1
            return "PARSE_OK"
        else:
            dafny_dict['v_state'] = 0
            logging.info(f"Failed.")
    except Exception as e:
        dafny_dict['v_state'] = 0
        if hasattr(e, 'stdout') and " 0 error" in e.stdout:
            dafny_dict['v_state'] = 1
            logging.info(f"Passed.")
            return "PARSE_OK"
    except FileNotFoundError:
        logging.error("dafny not found in PATH")
        dafny_dict['v_state'] = 0
        return "EXECUTION_ERROR"

    try:
        cmd = command_def + [dafny_file]
        logging.info(f"Running command: {' '.join(cmd)}")
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
            timeout=60
        )
        if " 0 error" in result.stdout:
            dafny_dict['v_state'] = 1
            return "PARSE_OK"
        else:
            dafny_dict['v_state'] = 0
            logging.info(f"Failed.")
            return "PARSE_ERROR"
    except Exception as e:
        dafny_dict['v_state'] = 0
        if hasattr(e, 'stdout') and " 0 error" in e.stdout:
            dafny_dict['v_state'] = 1
            logging.info(f"Passed.")
            return "PARSE_OK"
        else:
            return "PARSE_ERROR"
    finally:
        if os.path.exists(dafny_file):
            os.remove(dafny_file)


def parallel_version_gt_score(
        command_def: list[str],
        dafny_codes: list[dict],
        code_field: str = 'code_processed',
        log_file: str = None,
        max_workers: int = 4,
        whole_list: bool = False,
    ) -> List[Dict]:
    """Parallel GT score verification."""
    bound_func = functools.partial(dafny_verify_gt_score,
                                   command_def,
                                   code_field=code_field,
                                   log_file=log_file)

    parse_ok_list = []
    total_list = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_dict = {executor.submit(bound_func, dafny_code): dafny_code
                          for dafny_code in dafny_codes}

        for future in as_completed(future_to_dict):
            original_dict = future_to_dict[future]
            original_dict['parse_state'] = 0
            try:
                status = future.result()
                if (status == "PARSE_OK"
                        and re.search(r'method\s+\w+\s*\([^)]*\)',
                                      original_dict[code_field])):
                    parse_ok_list.append(original_dict)
                    original_dict['parse_state'] = 1
            except Exception as e:
                logging.error(f"A future raised an exception for index "
                              f"{original_dict.get('index', 'N/A')}: {e}")
            total_list.append(original_dict)

    if whole_list:
        return parse_ok_list, total_list
    else:
        return parse_ok_list
