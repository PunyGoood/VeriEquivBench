"""
equiv_reward.py — GT spec-to-code equivalence check for Dafny programs.

Provides create_spec_to_code_check() which injects verification methods
to check that code correctly implements its specification.
"""

import re
import os
import sys

try:
    from dafny_parser import (
        is_fuzzy_match,
        extract_solution,
        extract_input,
        extract_think_process,
        check_no_cheat_by_more_assume,
        tidy_dafny_code,
    )
except ImportError:
    from .dafny_parser import (
        is_fuzzy_match,
        extract_solution,
        extract_input,
        extract_think_process,
        check_no_cheat_by_more_assume,
        tidy_dafny_code,
    )

from spec_utils import *


class bcolors:
    WARNING = '\033[93m'
    ENDC = '\033[0m'


def get_returns(signature: str, body: str) -> str:
    """Extract return variable names and types from a method signature."""
    ret_clause = re.search(r'returns\s*\(\s*([^)]*)\)', signature)
    if not ret_clause:
        return None, None, None
    ret_vars_str = ret_clause.group(1)
    var_parts = split_top_level(ret_vars_str)
    var_names = [p.split(':', 1)[0].strip() for p in var_parts]
    var_types = []
    for p in var_parts:
        if len(p.split(':', 1)) > 1:
            var_types.append(p.split(':', 1)[1].strip())
        else:
            var_types.append(None)
    value_names = [f"val_{i}" for i in range(len(var_names))]
    return var_names, value_names, var_types


def get_inputs(signature: str, body: str) -> tuple:
    """Extract input parameter names and types from a method signature."""
    method_pattern = re.search(
        r'method\s+(?:\{:axiom\}\s+)?([^<(]+?)(?:<[^>]*>)?\s*\(([^)]*)\)', signature
    )
    if not method_pattern:
        print(f"{bcolors.WARNING}No method signature found: {signature}{bcolors.ENDC}")
        return [], []

    params_str = method_pattern.group(2).strip()
    if not params_str:
        return [], []

    param_parts = split_top_level(params_str)
    input_var_names = []
    input_var_types = []

    for param in param_parts:
        param = param.strip()
        if param:
            var_name = param.split(':', 1)[0].strip()
            input_var_names.append(var_name)
            if len(param.split(':', 1)) > 1:
                input_var_types.append(param.split(':', 1)[1].strip())
            else:
                input_var_types.append(None)

    return input_var_names, input_var_types


def generated_check_in_place_method(method_text, specs, full_signature, name):
    """Generate a check method for in-place (no return) methods."""
    input_var_names, input_var_types = get_inputs(full_signature, method_text)
    if input_var_names is None or input_var_types is None:
        return None, None

    asssumptions = specs[name]["requires"]
    indent = "  "
    inputs = ",".join(input_var_names)

    input_var_names = [input_var_names[i] for i in range(len(input_var_names))
                       if "array" in input_var_types[i] or "map" in input_var_types[i]]
    value_names = [f"val_{i}" for i in range(len(input_var_names))]
    input_var_types = [input_var_types[i] for i in range(len(input_var_types))
                       if "array" in input_var_types[i] or "map" in input_var_types[i]]

    new_signature = "\n" + full_signature.replace(name, f"{name}_check") + "\n"
    for input_var in input_var_names:
        new_signature += f"modifies {input_var} \n"
    new_signature += "\n{\n"

    for var, type_name in zip(value_names, input_var_types):
        new_signature += f"{indent}var {var} := new {type_name};\n"
    for item in asssumptions:
        new_signature += f"{indent}assume {item};\n"

    asssumptions = specs[name]["ensures"]
    for item in asssumptions:
        for input_var, value in zip(input_var_names, value_names):
            def replace_var_not_in_old(text, var, replacement):
                result = ""
                i = 0
                while i < len(text):
                    if text[i:i+4] == 'old(':
                        paren_count = 1
                        j = i + 4
                        while j < len(text) and paren_count > 0:
                            if text[j] == '(':
                                paren_count += 1
                            elif text[j] == ')':
                                paren_count -= 1
                            j += 1
                        result += text[i:j]
                        i = j
                    else:
                        if (text[i:i+len(var)] == var
                                and (i == 0 or not text[i-1].isalnum())
                                and (i+len(var) >= len(text) or not text[i+len(var)].isalnum())):
                            result += replacement
                            i += len(var)
                        else:
                            result += text[i]
                            i += 1
                return result

            result = replace_var_not_in_old(item, input_var, value)
            new_signature += f"{indent}assume {result};\n"

    new_signature += f"{indent}{name}({inputs});\n"
    for val, var, type_name in zip(value_names, input_var_names, input_var_types):
        if "array" in type_name:
            new_signature += f"{indent}assert {var}.Length == {val}.Length;\n"
            new_signature += f"{indent}assert forall i :: 0 <= i < {var}.Length ==> {var}[i] == {val}[i];\n"
        elif "map" in type_name:
            new_signature += f"{indent}assert forall k :: k in {var}.Keys ==> k in {val}.Keys && {var}[k] == {val}[k];\n"
            new_signature += f"{indent}assert forall k :: k in {val}.Keys ==> k in {var}.Keys && {var}[k] == {val}[k];\n"
        else:
            new_signature += f"{indent}assert {var} == {val};\n"
    new_signature += "\n}\n"
    return new_signature, full_signature


def generate_check_method(match, stripped, specs):
    """Generate a check method for a given method match."""
    start, end, no_braces = parse_method(match, stripped)
    if start is None or end is None:
        return None, None
    method_text = stripped[start:end]
    sig, name = match.group(1), match.group(2)
    if "Main" in name:
        return None, None
    if name not in specs:
        return None, None

    lines = method_text.split('\n')
    full_signature = ""
    for line in lines:
        full_signature += line.strip() + " "
        if line.strip().startswith('{'):
            full_signature = full_signature.split('{')[0].strip()
            break

    if "returns" not in method_text:
        return generated_check_in_place_method(method_text, specs, full_signature, name)

    var_names, value_names, var_types = get_returns(full_signature, method_text)
    input_var_names, _ = get_inputs(full_signature, method_text)
    if var_names is None or value_names is None or input_var_names is None:
        return None, None

    new_signature = "\n" + full_signature.replace(name, f"{name}_check") + "\n{\n"
    asssumptions = specs[name]["requires"]
    asssumptions += specs[name]["ensures"]
    indent = "  "
    for var in var_names:
        new_signature += f"{indent}{var} := *;\n"
    for item in asssumptions:
        item = item.strip(";")
        new_signature += f"{indent}assume {item};\n"
    values = ",".join(value_names)
    inputs = ",".join(input_var_names)
    new_signature += f"{indent}var {values} :={name}({inputs});\n"
    for val, var, type_name in zip(value_names, var_names, var_types):
        if type_name is None:
            continue
        if "array" in type_name:
            new_signature += f"{indent}assert {var}.Length == {val}.Length;\n"
            new_signature += f"{indent}assert forall i :: 0 <= i < {var}.Length ==> {var}[i] == {val}[i];\n"
        elif "map" in type_name:
            new_signature += f"{indent}assert forall k :: k in {var}.Keys ==> k in {val}.Keys && {var}[k] == {val}[k];\n"
            new_signature += f"{indent}assert forall k :: k in {val}.Keys ==> k in {var}.Keys && {var}[k] == {val}[k];\n"
        else:
            new_signature += f"{indent}assert {var} == {val};\n"
    new_signature += "\n}\n"
    return new_signature, full_signature


def create_spec_to_code_check(code):
    """Inject check methods into Dafny code to verify spec-to-code equivalence."""
    code = remove_comments(code)
    specs = extract_specs(code)
    stripped = tidy_dafny_code(hint_remove(code))

    pattern = re.compile(r'(method\s+(?:\{:axiom\}\s+)?([^<(]+))', re.MULTILINE)
    for m in pattern.finditer(stripped):
        check_method, full_signature = generate_check_method(m, stripped, specs)
        if check_method is not None:
            match_method = re.search(m.group(1), code)
            if match_method is None:
                print(f"{bcolors.WARNING}No match method found: {m.group(1)}{bcolors.ENDC}")
                print(f"code: {code}")
                continue
            else:
                start, end, _ = parse_method(match_method, code)
                code = code[:end] + check_method + code[end:]

    return code