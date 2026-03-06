"""
Translate Python unit tests to Dafny and run them against Dafny code.

Takes Python test patterns like `assert candidate(args) == expected`, extracts
input-output pairs, generates a Dafny Main() method that runs the tests, and
executes with `dafny run`.
"""

dafny_data = "/dafny/data/train.json"

ORIGINAL_TEST = "/python/data/LeetCodeDataset-test.jsonl"
ORIGINAL_TRAIN = "/python/data/LeetCodeDataset-train.jsonl"

import json
from math import e
import os
import tempfile
import subprocess
import re
from typing import Dict, List, Any, Optional, Tuple
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

def load_leetcode_data(file_path: str) -> List[Dict[str, Any]]:
    """Load LeetCode data from JSON file."""
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def load_original_tests(file_path: str) -> Dict[int, Dict[str, Any]]:
    """Load original test data from JSONL file and index by question_id."""
    tests_by_id = {}
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                data = json.loads(line.strip())
                question_id = data.get('question_id')
                if question_id:
                    tests_by_id[question_id] = data
    return tests_by_id

def extract_dafny_code(dafny_no_comment: str) -> str:
    """Extract Dafny code from the dafny_no_comment field, removing markdown code blocks."""
    # Remove ```dafny and ``` markers
    code = dafny_no_comment.strip()
    if code.startswith('```dafny'):
        code = code[8:]
    if code.endswith('```'):
        code = code[:-3]
    return code.strip()

def execute_dafny_file(dafny_code: str, question_id: int) -> str:
    """Save Dafny code to a temporary file and return the file path."""
    # Create a temporary file with .dfy extension
    with tempfile.NamedTemporaryFile(suffix=f'_q{question_id}.dfy', delete=False) as temp_file:
        temp_file.write(dafny_code.encode('utf-8'))
        dafny_file = temp_file.name
    
    try:
        # Use the same approach as the working code
        cmd = ['dafny', "run", dafny_file, "--allow-warnings"]
        # Set up environment with proper PATH
        env = os.environ.copy()
        env['PATH'] = f"/home/yanchuanhao/.local/bin:/mnt/shared-storage-user/formalverification-shared/dafny:{env.get('PATH', '')}"
        
        # print(f"DEBUG: Running command: {' '.join(cmd)}")
        result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                env=env,
                timeout=600
        )
    except subprocess.TimeoutExpired:
        return False, "", "Execution timed out after 60 seconds"
    except FileNotFoundError:
        return False, "", "File Not Found."
    except Exception as e:
        return False, "", f"Error during execution: {str(e)}"
    finally:
        # Clean up temporary file
        if os.path.exists(dafny_file):
            os.remove(dafny_file)
    
    return result.returncode == 0, result.stdout, result.stderr


def extract_input_output_pairs(test_code: str) -> List[Dict[str, Any]]:
    """Extract input-output pairs from Python test code for Dafny main method generation."""
    test_cases = []
    
    # Find all assert statements with candidate calls
    # More precise pattern to avoid capturing extra text
    assert_pattern = r'assert\s+candidate\(([^)]+)\)\s*==\s*([^#\n]+?)(?:\s*#.*)?$'
    matches = re.findall(assert_pattern, test_code, re.MULTILINE)
    
    for input_str, expected_str in matches:
        try:
            # Parse input arguments
            input_args = input_str.strip()
            
            # Parse expected output - clean up the string first
            expected = expected_str.strip()
            
            # Remove any trailing comments or extra whitespace
            expected = re.sub(r'\s*#.*$', '', expected).strip()
            
            test_cases.append({
                'input': input_args,
                'expected': expected
            })
        except Exception as e:
            # If parsing fails, store as string
            test_cases.append({
                'input': input_str.strip(),
                'expected': expected_str.strip(),
                'parse_error': str(e)
            })
    
    return test_cases

def generate_dafny_main_method(dafny_code: str, test_cases: List[Dict[str, Any]], question_id: int) -> str:
    """Generate a Dafny main method that runs all test cases using print(A==B) approach."""
    
    # Extract the main method name from the Dafny code
    method_pattern = r'method\s+(\w+)\s*\('
    method_matches = re.findall(method_pattern, dafny_code)
    
    if not method_matches or len(method_matches) > 1:
        return None  # No method found, return original code
    
    main_method_name = method_matches[0]  # Use the first method found
    
    # Generate test cases for Dafny
    test_code_lines = []
    test_code_lines.append("")
    test_code_lines.append("// Generated test cases using print(A==B) approach")
    test_code_lines.append("method {:verify false} Main()")
    test_code_lines.append("{")
    test_code_lines.append("    var testCount := 0;")
    test_code_lines.append("")
    
    for i, test_case in enumerate(test_cases):
        test_code_lines.append(f"    // Test case {i + 1}")
        test_code_lines.append(f"    testCount := testCount + 1;")
        
        # Generate the method call
        input_args = test_case['input']
        expected = test_case['expected']
        
        # Convert Python-style arguments to Dafny format
        dafny_input = convert_python_args_to_dafny(input_args)
        
        # Check if we need to create array variables
        if '[' in input_args and ']' in input_args:
            # Extract list arguments and create array variables using bracket-aware parsing
            array_vars = []
            args_list = []
            
            # Parse arguments with bracket awareness
            j = 0
            current_arg = ""
            bracket_depth = 0
            
            while j < len(input_args):
                char = input_args[j]
                
                if char in '[({':
                    bracket_depth += 1
                elif char in '])}':
                    bracket_depth -= 1
                elif char == ',' and bracket_depth == 0:
                    # This is a top-level comma, so we've found an argument boundary
                    if current_arg.strip():
                        args_list.append(current_arg.strip())
                    current_arg = ""
                    j += 1
                    continue
                
                current_arg += char
                j += 1
            
            # Add the last argument
            if current_arg.strip():
                args_list.append(current_arg.strip())
            
            for j, arg in enumerate(args_list):
                arg = arg.strip()
                if '[' in arg and ']' in arg:
                    # This is a list argument
                    if '=' in arg:
                        list_content = arg.split('=')[1].strip()
                    else:
                        list_content = arg
                    
                    if list_content.startswith('[') and list_content.endswith(']'):
                        elements = [elem.strip() for elem in list_content[1:-1].split(',')]
                        if elements and elements[0] and "'" not in elements[0] and "[" not in elements[0]:
                            var_name = f"arr{i}_{j}"
                            test_code_lines.append(f"    var {var_name} := new int[{len(elements)}];")
                            for k, element in enumerate(elements):
                                test_code_lines.append(f"    {var_name}[{k}] := {element};")
                            array_vars.append(var_name)
                        elif elements and elements[0] and "[" in elements[0]:
                            elements = [elem.strip() for elem in list_content[1:-1].split('],')]
                            var_name_array = f"arr{i}_{j}"
                            test_code_lines.append(f"    var {var_name_array} := new array<int>[{len(elements)}][];")
                            for k, element in enumerate(elements):
                                var_name = f"arr{i}_{j}_{k}"
                                values = [elem.strip() for elem in element[1:].split(',')]
                                test_code_lines.append(f"    var {var_name} := new int[{len(values)}];")
                                for l, value in enumerate(values):
                                    value = value.strip("]")
                                    test_code_lines.append(f"    {var_name}[{l}] := {value};")
                                test_code_lines.append(f"    {var_name_array}[{k}] := {var_name};")
                            array_vars.append(var_name_array)
                        # elif elements and elements[0] and "seq<string>" in dafny_code:
                        #     var_name = f"arr{i}_{j}"
                        #     list_content = list_content.replace("'", '"')
                        #     test_code_lines.append(f"    var {var_name} := {list_content};")
                        #     array_vars.append(var_name)
                        # elif elements and elements[0] and "'" in elements[0]:
                        #     var_name = f"arr{i}_{j}"
                        #     # Replace all single quotes with double quotes in list_content
                        #     list_content = list_content.replace("'", '"')
                        #     elements = [elem.strip() for elem in list_content[1:-1].split(',')]
                        #     test_code_lines.append(f"    var {var_name} := new string[{len(elements)}];")
                        #     for k, element in enumerate(elements):
                        #         test_code_lines.append(f"    {var_name}[{k}] := {element};")
                        #     array_vars.append(var_name)
                        else:
                            var_name = f"arr{i}_{j}"
                            list_content = list_content.replace("'", '"')
                            test_code_lines.append(f"    var {var_name} := {list_content};")
                            array_vars.append(var_name)
                    else:
                        array_vars.append(arg)
                else:
                    if '=' in arg:
                        array_vars.append(arg.split('=')[1].strip())
                    else:
                        array_vars.append(arg)
                    
            # Create the method call with array variables
            method_args = ", ".join(array_vars)
            test_code_lines.append(f"    var result{i} := {main_method_name}({method_args});")
        else:
            test_code_lines.append(f"    var result{i} := {main_method_name}({dafny_input});")
        
        # Generate print statement for comparison result
        if isinstance(expected, bool):
            test_code_lines.append(f"    print(result{i} == {str(expected).lower()});")
        elif expected in ["True", "False"]:
            test_code_lines.append(f"    print(result{i} == {str(expected).lower()});")
        elif isinstance(expected, list):
            expected = expected.replace("[", "{").replace("]", "}")
            test_code_lines.append(f"    print(result{i} == {expected});")
        else:
            test_code_lines.append(f"    print(result{i} == {expected});")
        
        test_code_lines.append("")
    
    test_code_lines.append("    print(\"\\nTotal tests: \", testCount);")
    test_code_lines.append("}")
    
    # Append the generated main method to the original Dafny code
    enhanced_dafny_code = dafny_code + "\n" + "\n".join(test_code_lines)
    
    return enhanced_dafny_code

def convert_python_args_to_dafny(input_args: str) -> str:
    """Convert Python-style function arguments to Dafny format."""
    # This is a simplified conversion - may need more sophisticated parsing
    # for complex data structures
    
    # Handle common patterns
    # Need to properly parse arguments that may contain lists with commas
    dafny_args = []
    
    # Split by comma, but be careful about commas inside brackets
    i = 0
    current_arg = ""
    bracket_depth = 0
    
    while i < len(input_args):
        char = input_args[i]
        
        if char in '[({':
            bracket_depth += 1
        elif char in '])}':
            bracket_depth -= 1
        elif char == ',' and bracket_depth == 0:
            # This is a top-level comma, so we've found an argument boundary
            if current_arg.strip():
                dafny_args.append(current_arg.strip())
            current_arg = ""
            i += 1
            continue
        
        current_arg += char
        i += 1
    
    # Add the last argument
    if current_arg.strip():
        dafny_args.append(current_arg.strip())
    
    # Process each argument
    processed_args = []
    for arg in dafny_args:
        if "=" in arg:
            # Keyword argument: key=value -> use value
            arg = arg.split("=", 1)[1].strip()
            processed_args.append(arg)
        else:
            processed_args.append(arg)
    
    dafny_args = ",".join(processed_args)
    
    # Convert Python list syntax to Dafny array syntax
    # [1, 2, 3] -> new int[3](1, 2, 3) for arrays
    # or keep as [1, 2, 3] for sequences if the method expects seq<int>
    
    # For now, let's try to detect if we need arrays or sequences
    # and convert accordingly
    
    # # Convert [1, 2, 3] to new int[3](1, 2, 3) for arrays
    # dafny_args = re.sub(r'\[([^\]]+)\]', convert_list_to_dafny_array, dafny_args)
    
    # # Convert string literals
    # dafny_args = re.sub(r'"([^"]*)"', r'"\1"', dafny_args)  # Keep string quotes
    
    # Convert boolean values
    dafny_args = dafny_args.replace('True', 'true').replace('False', 'false')
    
    return dafny_args

def execute_dafny_code_parallel(code_item: Dict[str, Any]) -> Dict[str, Any]:
    """Execute a single Dafny code item and return results."""
    question_id = code_item['question_id']
    code = code_item['code']
    expected_count = code_item['count']
    
    if code is None:
        return {
            'question_id': question_id,
            'success': False,
            'error': 'No valid Dafny code generated',
            'true_count': 0,
            'expected_count': expected_count,
            'passed': False
        }
    
    try:
        # Execute Dafny code
        success, stdout, stderr = execute_dafny_file(code, question_id)
        
        
        if not success or expected_count == 0:
            # if " 0 errors" in stdout:
            #     print(f"Dafny execution failed: {stdout}")
            #     with open(f"/mnt/shared-storage-user/formalverification-shared/fengdi/Dafny_process/logs/unit_test/{question_id}.dfy", "w") as f:
            #         f.write(code)
            return {
                'question_id': question_id,
                'success': False,
                'error': f'Dafny execution failed: {stderr}',
                'true_count': 0,
                'expected_count': expected_count,
                'passed': False,
                'stdout': stdout,
                'stderr': stderr
            }
        
        # Count 'true' values in output
        true_count = stdout.count('true')
        # Check if all tests passed
        passed = (true_count == expected_count)
        
        return {
            'question_id': question_id,
            'success': True,
            'error': None,
            'true_count': true_count,
            'expected_count': expected_count,
            'passed': passed,
            'stdout': stdout,
            'stderr': stderr
        }
            
    except Exception as e:
        return {
            'question_id': question_id,
            'success': False,
            'error': f'Exception during execution: {str(e)}',
            'true_count': 0,
            'expected_count': expected_count,
            'passed': False
        }
        

def execute_dafny_codes_parallel(code_list: List[Dict[str, Any]], max_workers: int = 4) -> List[Dict[str, Any]]:
    """Execute Dafny codes in parallel and return results."""
    results = []
    
    print(f"Executing {len(code_list)} Dafny codes in parallel with {max_workers} workers...")
    # max_workers = min(max_workers, os.cpu_count())

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_code = {executor.submit(execute_dafny_code_parallel, code_item): code_item 
                         for code_item in code_list}
        
        # Process completed tasks
        completed = 0
        for future in as_completed(future_to_code):
            result = future.result()
            results.append(result)
            completed += 1
            
            # Print individual result
            question_id = result['question_id']
            if result['success']:
                true_count = result['true_count']
                expected_count = result['expected_count']
                print(f"Q{question_id}: {true_count}/{expected_count} tests passed")
                with open(f"/mnt/shared-storage-user/formalverification-shared/fengdi/Dafny_process/logs/execution_summary.txt", "a") as f:
                    f.write(f"Q{question_id}: {true_count}/{expected_count} tests passed\n")
            
            # Print progress
            if completed % 10 == 0 or completed == len(code_list):
                print(f"--- Completed {completed}/{len(code_list)} executions ---")
                with open(f"/mnt/shared-storage-user/formalverification-shared/fengdi/Dafny_process/logs/execution_summary.txt", "a") as f:
                    f.write(f"--- Completed {completed}/{len(code_list)} executions ---\n")
    
    return results

def main():
    leetcode_data = load_leetcode_data(dafny_data)
    
    original_tests = load_original_tests(ORIGINAL_TEST)
    original_train = load_original_tests(ORIGINAL_TRAIN)

    import time
    start_time = time.time()
    
    code_list = []
    for problem in leetcode_data:
   
        question_id = problem.get('question_id')
        dafny_no_comment = problem.get('dafny_no_comment', '')
        

        # Find matching test cases
        if question_id not in original_tests and question_id not in original_train:
            continue
            
        original_test_data = original_tests[question_id] if question_id in original_tests else original_train[question_id]
        test_code = original_test_data.get('test', '')

        
        # Extract Dafny code
        dafny_code = extract_dafny_code(dafny_no_comment)
        
        # Extract test cases
        test_cases = extract_input_output_pairs(test_code)
        
        # Generate Dafny code with main method
        code = generate_dafny_main_method(dafny_code, test_cases, question_id)
        if code is None:
            continue
        # print(code)
        code_list.append({"code": code, "question_id": question_id, "count": len(test_cases)})
    
    print(f"\nGenerated {len(code_list)} Dafny codes with main methods")
    
    # Execute Dafny codes in parallel
    execution_results = execute_dafny_codes_parallel(code_list, max_workers=64)

    end_time = time.time()
    print(f"Time taken: {end_time - start_time} seconds")
    
    # Analyze results
    total_codes = len(execution_results)
    successful_executions = sum(1 for r in execution_results if r['success'])
    passed_tests = sum(1 for r in execution_results if r['passed'])
    
    # Count timeouts and verification errors separately
    timeout_count = sum(1 for r in execution_results if not r['success'] and r.get('stderr') and 'timed out' in r['stderr'])
    verification_error_count = sum(1 for r in execution_results if not r['success'] and r.get('stdout') and 'verified' in r['stdout'])
    
    # total_expected_tests = sum(r['expected_count'] for r in execution_results)
    # total_true_outputs = sum(r['true_count'] for r in execution_results)
    # Group results by test pass rate
    perfect_passes = [r for r in execution_results if r['passed'] and r['success']]
    partial_passes = [r for r in execution_results if not r['passed'] and r['success'] and r['true_count'] > 0]
    complete_failures = [r for r in execution_results if r['success'] and r['true_count'] == 0]
    execution_failures = [r for r in execution_results if not r['success']]

    print("\n=== EXECUTION SUMMARY ===")
    print(f"Total codes processed: {total_codes}")
    print(f"Successful executions: {successful_executions}/{total_codes} ({successful_executions/total_codes*100:.1f}%)")
    print(f"Codes with all tests passed: {passed_tests}/{total_codes} ({passed_tests/total_codes*100:.1f}%)")
    print(f"Timeouts: {timeout_count}")
    print(f"Verification errors: {verification_error_count}")

    print(f"Perfect passes question_ids: {','.join(str(r.get('question_id', r)) for r in perfect_passes)}")
    print(f"Partial passes question_ids: {','.join(str(r.get('question_id', r)) for r in partial_passes)}")
    print(f"Complete failures question_ids: {','.join(str(r.get('question_id', r)) for r in complete_failures)}")
    print(f"Execution failures question_ids: {','.join(str(r.get('question_id', r)) for r in execution_failures)}")

    
    log_dir = "/mnt/shared-storage-user/formalverification-shared/fengdi/Dafny_process/logs"
    log_file = os.path.join(log_dir, "execution_summary.txt")
    with open(log_file, "a") as log_file:
        log_file.write(f"\n=== EXECUTION SUMMARY ===\n")
        log_file.write(f"Total codes processed: {total_codes}\n")
        log_file.write(f"Successful executions: {successful_executions}/{total_codes} ({successful_executions/total_codes*100:.1f}%)\n")
        log_file.write(f"Codes with all tests passed: {passed_tests}/{total_codes} ({passed_tests/total_codes*100:.1f}%)\n")
        log_file.write(f"Timeouts: {timeout_count}\n")
        log_file.write(f"Verification errors: {verification_error_count}\n")

        # Save lists as comma-separated strings in the log file
        log_file.write(f"Perfect passes question_ids: {','.join(str(r.get('question_id', r)) for r in perfect_passes)}\n")
        log_file.write(f"Partial passes question_ids: {','.join(str(r.get('question_id', r)) for r in partial_passes)}\n")
        log_file.write(f"Complete failures question_ids: {','.join(str(r.get('question_id', r)) for r in complete_failures)}\n")
        log_file.write(f"Execution failures question_ids: {','.join(str(r.get('question_id', r)) for r in execution_failures)}\n")
    # print(f"Total expected test cases: {total_expected_tests}")
    # print(f"Total 'true' outputs: {total_true_outputs}")
    # print(f"Test success rate: {total_true_outputs}/{total_expected_tests} ({total_true_outputs/total_expected_tests*100:.1f}%)")
    
    
    # Show examples of each category
    if partial_passes:
        print(f"\n=== PARTIAL PASSES (first 3) ===")
        for i, case in enumerate(partial_passes[:3]):
            print(f"Q{case['question_id']}: {case['true_count']}/{case['expected_count']} tests passed")
    
    if complete_failures:
        print(f"\n=== COMPLETE FAILURES (first 3) ===")
        for i, case in enumerate(complete_failures[:3]):
            print(f"Q{case['question_id']}: {case['true_count']}/{case['expected_count']} tests passed")
    
    if execution_failures:
        print(f"\n=== EXECUTION FAILURES (first 3) ===")
        for i, case in enumerate(execution_failures[:3]):
            print(f"Q{case['question_id']}: {case['error']}")

    pass_list = []
    for r in execution_results:
        if r['passed']:
            pass_list.append(f"Q{r['question_id']}: {r['true_count']}/{r['expected_count']} tests passed")
        
    print(f"Pass rate: {pass_list}")
    
    # # Save detailed results
    # results_file = "/mnt/shared-storage-user/formalverification-shared/fengdi/Dafny_process/training_data/execution_results.json"
    # with open(results_file, 'w', encoding='utf-8') as f:
    #     json.dump({
    #         'summary': {
    #             'total_codes': total_codes,
    #             'successful_executions': successful_executions,
    #             'passed_tests': passed_tests,
    #             'total_expected_tests': total_expected_tests,
    #             'total_true_outputs': total_true_outputs
    #         },
    #         'detailed_results': execution_results
    #     }, f, indent=2, ensure_ascii=False)
    
    # print(f"\nDetailed results saved to: {results_file}")

if __name__ == "__main__":
    main()

