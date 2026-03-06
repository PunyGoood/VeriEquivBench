"""
Data formatting utilities: extraction, fuzzy matching, and Dafny code tidying.
"""

import re
from typing import Optional, Tuple


def _extract_tosearch(code: str, pattern: str) -> set:
    """Extract matches for a regex pattern from code."""
    compiled = re.compile(pattern)
    return set(compiled.findall(code))

# Public alias for backward compatibility
extract_tosearch = _extract_tosearch


def is_fuzzy_match(original: str, modified: str) -> bool:
    """
    Check if modified is original with inserted lines and/or whitespace changes.

    Returns True if every non-empty line of original appears in modified in order.
    """
    original_lines = [line.strip() for line in original.splitlines() if line.strip()]
    modified_lines = [line.strip() for line in modified.splitlines() if line.strip()]
    j = 0
    for orig_line in original_lines:
        while j < len(modified_lines) and modified_lines[j] != orig_line:
            j += 1
        if j >= len(modified_lines):
            return False
        j += 1
    return True


def extract_input(solution_str: str) -> Optional[str]:
    """Extract input from solution string (before Assistant, in ```dafny block)."""
    if "Assistant:" in solution_str:
        solution_str = solution_str.split("Assistant:", 1)[0]
    elif "<|im_start|>assistant" in solution_str:
        solution_str = solution_str.split("<|im_start|>assistant", 1)[0]
    else:
        return None

    if "Below is the program:" not in solution_str:
        return None
    solution_str = solution_str.split("Below is the program:")[1]

    think_pattern = r'```dafny(.*?)<\|im_end\|>'
    matches = list(re.finditer(think_pattern, solution_str, re.DOTALL))
    if matches:
        final_answer = matches[-1].group(1).strip()
        final_answer = final_answer.replace('```dafny', '').replace('```', '').strip()
        return final_answer
    return None


def extract_think_process(solution_str: str) -> Optional[str]:
    """Extract think process from solution string (between Assistant and ```dafny)."""
    if "Assistant:" in solution_str:
        solution_str = solution_str.split("Assistant:", 1)[1]
    elif "<|im_start|>assistant" in solution_str:
        solution_str = solution_str.split("<|im_start|>assistant", 1)[1]
    else:
        return None

    think_pattern = r'<think>(.*?)```dafny'
    matches = list(re.finditer(think_pattern, solution_str, re.DOTALL))
    if matches:
        final_answer = matches[-1].group(1).strip()
        final_answer = final_answer.replace('```dafny', '').strip()
        return final_answer
    return None


def extract_solution(solution_str: str) -> Optional[str]:
    """Extract Dafny code from solution string (from <answer> or ```dafny blocks)."""
    if "Assistant:" in solution_str:
        solution_str = solution_str.split("Assistant:", 1)[1]
    elif "<|im_start|>assistant" in solution_str:
        solution_str = solution_str.split("<|im_start|>assistant", 1)[1]
    else:
        return None

    # Try <answer>...</answer>
    answer_pattern = r'<answer>(.*?)</answer>'
    matches = list(re.finditer(answer_pattern, solution_str, re.DOTALL))
    if matches:
        final_answer = _clean_extracted_code(matches[-1].group(1).strip())
        return final_answer

    # Try <answer>...<|im_end|>
    answer_pattern = r'<answer>(.*?)<\|im_end\|>'
    matches = list(re.finditer(answer_pattern, solution_str, re.DOTALL))
    if matches:
        final_answer = _clean_extracted_code(matches[-1].group(1).strip())
        return final_answer

    # Try ```dafny...```
    answer_pattern = r'```dafny(.*?)```'
    matches = list(re.finditer(answer_pattern, solution_str, re.DOTALL))
    if matches:
        final_answer = _clean_extracted_code(matches[-1].group(1).strip())
        return final_answer

    # Try ```dafny...<|im_end|>
    answer_pattern = r'```dafny(.*?)<\|im_end\|>'
    matches = list(re.finditer(answer_pattern, solution_str, re.DOTALL))
    if matches:
        final_answer = _clean_extracted_code(matches[-1].group(1).strip())
        return final_answer

    return None


def _clean_extracted_code(code: str) -> str:
    """Clean extracted code string."""
    code = code.replace('```dafny', '').replace('```', '').strip().strip("`")
    code = code.replace('<|im_start|>', '').strip()
    # Truncate at last <|im_end|> if present
    im_end_matches = list(re.finditer(r'(.*?)<\|im_end\|>', code, re.DOTALL))
    if im_end_matches:
        code = im_end_matches[-1].group(1).strip()
    return code


def tidy_dafny_code(dafny_code: str) -> str:
    """Normalize and tidy Dafny code (braces, indentation)."""
    dafny_code = re.sub(r'\s*{\s*', ' \n{\n', dafny_code)
    dafny_code = re.sub(r'\s*}\s*', '\n}\n', dafny_code)

    lines = dafny_code.splitlines()
    indented_lines = []
    indent_level = 0

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        if re.match(r'^\s*(function|method|ghost|ensures|requires|invariant|while|if|else|return|assume)\s', stripped):
            if re.match(r'^\s*(function|method|ghost|assume)\s', stripped):
                indented_lines.append(' ' * indent_level + stripped)
                indent_level += 4
            else:
                indented_lines.append(' ' * indent_level + stripped)
        elif stripped == '}':
            indent_level -= 4
            indented_lines.append(' ' * indent_level + stripped)
        else:
            indented_lines.append(' ' * indent_level + stripped)

    tidy_code = '\n'.join(indented_lines)
    tidy_code = re.sub(r'(\b(?:ensures|requires|invariant|ensuresforall|ensuresexists|assume)\b)', r'\n\1', tidy_code)
    tidy_code = re.sub(r'\n\s*\n', '\n\n', tidy_code)

    lines = tidy_code.split('\n')
    indent_level = 0
    formatted_lines = []

    for line in lines:
        line = line.strip()
        if line.endswith('{'):
            formatted_lines.append('    ' * indent_level + line)
            indent_level += 1
        elif line.endswith('}'):
            indent_level -= 1
            formatted_lines.append('    ' * indent_level + line)
        elif line == '':
            formatted_lines.append('')
        else:
            formatted_lines.append('    ' * indent_level + line)

    return '\n'.join(formatted_lines)


def check_no_cheat_by_more_assume(complete_code: str, answer: str) -> Tuple[bool, Optional[list]]:
    """
    Check that answer does not add assume statements beyond those in complete_code.

    Returns (True, None) if ok; (False, missing_assumes) if answer has extra assumes.
    """
    complete_assumes = _extract_tosearch(complete_code, r'assume' + r' (.*?);')
    answer_assumes = _extract_tosearch(answer, r'assume' + r' (.*?);')
    complete_assumes = {x.split('//')[0].strip() for x in complete_assumes}
    answer_assumes = {x.split('//')[0].strip() for x in answer_assumes}

    missing_assumes = [a for a in answer_assumes if a not in complete_assumes]
    if missing_assumes:
        return False, missing_assumes
    return True, None
