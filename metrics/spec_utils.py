"""
comparison_code.py — Dafny code comparison and specification extraction utilities.

Provides functions for:
- Removing comments and specifications from Dafny code
- Extracting method specifications (requires/ensures clauses)
- Injecting assertions for spec comparison between GT and LLM code
"""

import re
import os


class bcolors:
    WARNING = '\033[93m'
    ENDC = '\033[0m'


def _strip_literals_and_comments(line: str) -> str:
    """Remove string literals and comments from a line for brace counting."""
    line = re.sub(r'"(\\.|[^"\\])*"', '""', line)
    line = re.sub(r'//.*', '', line)
    line = re.sub(r'/\*.*?\*/', '', line)
    return line


_dafny_comment_re = re.compile(
    r'''
      //.*?$          |   # single line comment
      /\*.*?\*/       |   # block comment
      "(?:\\.|[^"\\])*"   |   # string literal
      '(?:\\.|[^'\\])*'     # character literal
    ''',
    re.X | re.S | re.M
)


def remove_comments(code: str) -> str:
    """Remove all comments from Dafny source code."""
    def _repl(m: re.Match) -> str:
        if m.group(0).startswith(('"', "'")):
            return m.group(0)
        return ''
    return _dafny_comment_re.sub(_repl, code)


def remove_complex_specs(code: str, remove_keywords: list[str]) -> str:
    """Remove multi-line, block, and 'by' specifications."""
    lines = code.split('\n')
    keep_lines = []
    i = 0
    n = len(lines)
    spec_pattern = re.compile(r'^\s*(' + '|'.join(re.escape(k) for k in remove_keywords) + r')\b')
    while i < n:
        line = lines[i]
        if spec_pattern.match(line) and ('{' in line or re.search(r'\bby\b', line)):
            brace_balance = line.count('{') - line.count('}')
            i += 1
            while i < n and brace_balance > 0:
                brace_balance += lines[i].count('{') - lines[i].count('}')
                i += 1
            continue
        elif spec_pattern.match(line) and '(' in line:
            brace_balance = line.count('(') - line.count(')')
            i += 1
            while i < n and brace_balance > 0:
                brace_balance += lines[i].count('(') - lines[i].count(')')
                i += 1
            continue
        elif spec_pattern.match(line) and '[' in line:
            brace_balance = line.count('[') - line.count(']')
            i += 1
            while i < n and brace_balance > 0:
                brace_balance += lines[i].count('[') - lines[i].count(']')
                i += 1
            continue
        else:
            keep_lines.append(line)
            i += 1
    return '\n'.join(keep_lines)


def remove_specs(code: str, remove_keywords: list[str]) -> str:
    """Remove all single-line specifications."""
    stop_kw = ["requires", "ensures", "decreases", "reads", "modifies", 'invariant']
    next_method = ['method', 'function', 'constructor', 'lemma', 'class', 'predicate', 'two_state', 'ghost']

    kept_lines = []
    lines = code.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        line = line.lstrip()
        if any(line.startswith(kw) for kw in stop_kw):
            i += 1
            while i < len(lines):
                nxt = lines[i].lstrip()
                if (any(nxt.startswith(kw) for kw in remove_keywords)
                        or any(nxt.startswith(kw) for kw in next_method)
                        or nxt.startswith("{")):
                    break
                i += 1
            if i >= 1 and lines[i-1].strip().endswith("{"):
                kept_lines.append("{")
        elif any(line.startswith(kw) for kw in remove_keywords):
            i += 1
            while not line.rstrip().endswith(";") and i < len(lines) - 1:
                i += 1
                line = lines[i].lstrip()
        else:
            kept_lines.append(line)
            i += 1
    return '\n'.join(kept_lines)


def emptyline_remove(code: str) -> str:
    """Remove all empty lines from code."""
    if not code:
        return ''
    return '\n'.join([l for l in code.split('\n') if l.strip() != ''])


def hint_remove(
    original_code: str,
    remove_keywords: list[str] = ['requires', 'ensures', 'invariant', 'assert',
                                   'modifies', 'assume', 'reads', 'decreases'],
) -> str:
    """Remove all Dafny specifications (multi-line, block, by, and single-line)."""
    code = remove_specs(original_code, remove_keywords)
    code = emptyline_remove(code)
    return code


def extract_clauses(block: str, keyword: str) -> list[str]:
    """Extract all clauses starting with keyword from a Dafny code block."""
    lines = block.splitlines()
    clauses = []
    i = 0
    stop_kw = ["requires", "ensures", "decreases", "reads", "modifies"]

    while i < len(lines):
        line = lines[i].lstrip()
        if line.strip().startswith("{"):
            break
        if line.startswith(keyword):
            collected = [line[len(keyword):].strip()]
            i += 1
            while i < len(lines):
                nxt = lines[i].lstrip()
                if any(nxt.startswith(kw) for kw in stop_kw):
                    break
                collected.append(nxt)
                i += 1
            clause_text = " ".join(p for p in collected if p).strip()
            if clause_text.endswith("{"):
                clause_text = clause_text[:-1]
            clauses.append(clause_text)
        else:
            i += 1
    return clauses or []


def extract_specs(dafny_code: str):
    """
    Returns a dict:
      { method_name: {"requires": [...], "ensures": [...]} }
    """
    def find_method_signature_end(code, start_pos):
        pos = start_pos
        next_method_pattern = re.compile(
            r'^\s*(?:method|function|constructor|lemma|class|predicate|two_state|ghost)\s+\w+'
        )
        match = next_method_pattern.match(code[pos:])
        end_pos = pos + match.start() if match else len(code)

        while pos < end_pos:
            if code[pos] == '{':
                line_start = code.rfind('\n', 0, pos) + 1
                before_brace = code[line_start:pos].strip()
                if before_brace == '':
                    return pos + 1
            pos += 1
        return -1

    specs = {}
    sig_re = re.compile(
        r'((?:ghost\s+)?(?:method|function)\s+(\w+))',
        re.DOTALL | re.MULTILINE
    )

    parts = []
    for match in sig_re.finditer(dafny_code):
        name = match.group(2)
        start_pos = match.start()
        end_pos = find_method_signature_end(dafny_code, match.end())
        if end_pos != -1:
            parts.append({
                'match': match, 'name': name,
                'start': start_pos, 'end': end_pos,
            })

    for part in parts:
        name = part['name']
        block = dafny_code[part['start']:part['end']-1]
        reqs = extract_clauses(block, 'requires')
        enss = extract_clauses(block, 'ensures')
        specs[name] = {"requires": reqs, "ensures": enss}

    return specs


def conj(exprs):
    """Parenthesize and &&-join a list of expressions."""
    exprs = ["(" + exp.strip(";") + ")" for exp in exprs]
    return "(" + " && ".join(exprs) + ")"


def count_members(dafny_code: str):
    """Count the number of functions and methods."""
    sig_re = re.compile(r'((?:ghost\s+)?(?:method|function)\s+(\w+)[^{]*{)', re.MULTILINE)
    all_sigs = sig_re.findall(dafny_code)
    counts = {"non-ghost": 0, "ghost": 0}
    count = 0
    for full_sig, name in all_sigs:
        count += 1
        sig = full_sig.strip()
        if sig.startswith("ghost method") or sig.startswith("ghost function"):
            counts["ghost"] += 1
        elif sig.startswith("method") or sig.startswith("function"):
            counts["non-ghost"] += 1
    return counts, count


def parse_method(m, code):
    """Return (start, end, no_braces) for a matched method in code."""
    hdr_start = m.start()

    def find_method_body_start(code, start_pos):
        section = code[start_pos:]
        lines = section.split('\n')
        current_pos = 0
        for i, line in enumerate(lines):
            if line.strip().startswith('{') or line.strip().endswith("{"):
                brace_pos = line.find('{')
                return start_pos + current_pos + brace_pos, False

            if any(line.strip().startswith(kw) for kw in
                   ['method', 'function', 'constructor', 'lemma', 'class',
                    'predicate', 'two_state', 'ghost']):
                return start_pos + current_pos, True
            current_pos += len(line) + 1
        return -1, None

    method_body_start, no_braces = find_method_body_start(code, m.end())

    if method_body_start == -1:
        return None, None, None

    if no_braces:
        return hdr_start, method_body_start, no_braces

    brace_idx = method_body_start
    depth, i = 1, brace_idx + 1
    while i < len(code) and depth > 0:
        if code[i] == '{':
            depth += 1
        elif code[i] == '}':
            depth -= 1
        i += 1

    if depth != 0:
        print(f"{bcolors.WARNING}Unmatched braces for method parsing! Depth: {depth}{bcolors.ENDC}")
        return None, None, None

    return hdr_start, i, no_braces


def split_top_level(s: str, sep: str = ',') -> list[str]:
    """Split string s on sep at top-level, ignoring separators inside (), <>, [], {}."""
    parts = []
    buf = []
    depth = {'(': 0, ')': 0, '<': 0, '>': 0, '[': 0, ']': 0, '{': 0, '}': 0}
    matching = {')': '(', '>': '<', ']': '[', '}': '{'}
    for ch in s:
        if ch in '(<[{':
            depth[ch] += 1
        elif ch in ')}]>':
            depth[matching[ch]] -= 1
        if ch == sep and all(v == 0 for v in depth.values()):
            parts.append(''.join(buf).strip())
            buf = []
        else:
            buf.append(ch)
    if buf:
        parts.append(''.join(buf).strip())
    return parts


def strip_specs_and_inject_asserts_new(gt_code: str, ex_code: str, key: str = "one_score") -> str:
    """
    Generate a new Dafny file comparing specs between GT and LLM codes.

    key:
      requires  — compare if requirements of LLM code are weaker than GT
      ensures   — compare post-conditions under intersection of requirements
      one_score — requirements weaker AND post-conditions stronger
    """
    ex_code = remove_comments(ex_code)
    gt_code = remove_comments(gt_code)
    gt_specs = extract_specs(gt_code)
    ex_specs = extract_specs(ex_code)

    gt_code = re.sub(r'^```dafny.*$', '', gt_code, flags=re.MULTILINE)
    gt_code = re.sub(r'^```\s*$', '', gt_code, flags=re.MULTILINE)
    stripped = gt_code

    def inject_before_implicit_return(method_text, signature, meth, no_braces):
        return_pattern = re.compile(
            r'((?:ghost\s+)?function\s+(\w+).*?\:\s*\((\w+)\:.*?\)\s*\n)', re.MULTILINE
        )
        return_var = return_pattern.search(method_text)
        if return_var:
            gt = gt_specs.get(meth, {"requires": [], "ensures": []})
            ex = ex_specs.get(meth, {"requires": [], "ensures": []})
            gt_conj = conj(gt["requires"])
            ex_conj = conj(ex["requires"])
            if key == "requires":
                assertion = f"ensures {gt_conj} ==> {ex_conj} \n"
            elif key == "ensures":
                if gt["ensures"] == []:
                    assertion = "ensures true \n"
                elif ex["ensures"] == []:
                    assertion = "ensures false \n"
                else:
                    gt_conj_ensures = conj(gt["ensures"])
                    ex_conj_ensures = conj(ex["ensures"])
                    assertion = f"ensures {gt_conj_ensures} <== {ex_conj_ensures} \n"
            elif key == "one_score":
                if gt["ensures"] == []:
                    assertion = "ensures true \n"
                elif ex["ensures"] == []:
                    assertion = "ensures false \n"
                else:
                    gt_conj_ensures = conj(gt["ensures"])
                    ex_conj_ensures = conj(ex["ensures"])
                    assertion = f"ensures {gt_conj} ==> {ex_conj} \n ensures {gt_conj} ==> ({gt_conj_ensures} <== {ex_conj_ensures}) \n"
                    if ex["requires"] == []:
                        assertion = f"ensures {gt_conj_ensures} <== {ex_conj_ensures} \n"
                    if gt["requires"] == [] and ex["requires"] != []:
                        assertion = "ensures false\n"
            else:
                print(f"{bcolors.WARNING}Condition comparison key cannot be recognized!{bcolors.ENDC}")

            if ex["ensures"] == ["true"]:
                assertion = "ensures false \n"

            equiv_pattern = re.compile(r'\s*(\w+)\s*==\s*\1\s*')
            if len(ex['ensures']) == 1 and equiv_pattern.search(ex["ensures"][0]) and len(gt["ensures"]) > 1:
                assertion = "ensures false \n"
            sig_end = return_var.end()
            return method_text[:sig_end] + assertion + method_text[sig_end:]
        else:
            return method_text

    def inject(method_text, signature, meth, no_braces):
        gt = gt_specs.get(meth, {"requires": [], "ensures": []})
        ex = ex_specs.get(meth, {"requires": [], "ensures": []})
        gt_conj = conj(gt["requires"])
        ex_conj = conj(ex["requires"])
        if key == "requires":
            assertion = f"assert {gt_conj} ==> {ex_conj};\n"
        elif key == "ensures":
            if gt["ensures"] == []:
                assertion = "assert true;\n"
            elif ex["ensures"] == []:
                assertion = "assert false;\n"
            else:
                gt_conj_ensures = conj(gt["ensures"])
                ex_conj_ensures = conj(ex["ensures"])
                assertion = f"assert {gt_conj_ensures} <== {ex_conj_ensures};\n"
        elif key == "one_score":
            if gt["ensures"] == []:
                assertion = "assert true; \n"
            elif ex["ensures"] == []:
                assertion = "assert false; \n"
            else:
                gt_conj_ensures = conj(gt["ensures"])
                ex_conj_ensures = conj(ex["ensures"])
                assertion = f"assert {gt_conj} ==> {ex_conj}; \n assert {gt_conj} ==> ({gt_conj_ensures} <== {ex_conj_ensures}); \n"
                if ex["requires"] == []:
                    assertion = f"assert {gt_conj_ensures} <== {ex_conj_ensures};\n"
                if gt["requires"] == [] and ex["requires"] != []:
                    assertion = "assert false;\n"
        else:
            print(f"{bcolors.WARNING}Condition comparison key cannot be recognized!{bcolors.ENDC}")

        lines = method_text.split('\n')
        full_signature = ""
        for line in lines:
            full_signature += line.strip() + "\n"
            if line.strip().startswith('{') or line.strip().endswith("{"):
                full_signature = full_signature.split('{')[0].strip()
                break

        full_signature = full_signature.split("ensure")[0]
        name = ""
        for j in full_signature.split("\n"):
            name = name + j + "\n"
            if "return" in j:
                break
        if "return" in name:
            name = name.split("return")[1]
            if ":" in name and "(" in name:
                names = name.split("(")[1]
                new_body = full_signature + "{\n"
                for temp_name in names.split(":")[:-1]:
                    if "," in temp_name:
                        temp_name = temp_name.split(",")[1]
                    temp_name = temp_name.strip()
                    new_body += f"{temp_name}:=*;\n"
                new_body = new_body + assertion + "}"
            else:
                print("Format Error!")
                print(full_signature)
        else:
            new_body = full_signature + "{\n" + assertion + "}"

        return new_body

    pattern = re.compile(r'((?:ghost\s+)?(?:method|function)\s+(?:\{:axiom\}\s+)?(\w+))', re.MULTILINE)

    matches = []
    for m in pattern.finditer(stripped):
        start, end, no_braces = parse_method(m, stripped)
        if start is None:
            continue
        sig, name = m.group(1), m.group(2)
        matches.append((start, end, no_braces, sig, name))

    result = stripped
    for start, end, no_braces, sig, name in reversed(matches):
        full = result[start:end]
        if 'function' in sig:
            continue
        else:
            gt = gt_specs.get(name, {"requires": [], "ensures": []})
            ex = ex_specs.get(name, {"requires": [], "ensures": []})
            new_block = inject(full, sig, name, no_braces)
        result = result[:start] + new_block + result[end:]

    return result


# Alias for backward compatibility
strip_specs_and_inject_asserts = strip_specs_and_inject_asserts_new