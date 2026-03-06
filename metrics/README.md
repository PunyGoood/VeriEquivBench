# Dafny Metrics

Self-contained scoring toolkit for Dafny verification. All modules depend only on one another and the Python standard library.

## Prerequisites

### Dafny

`dafny` must be on your `PATH`.

```bash
# macOS
brew install dafny

# or cross-platform via .NET
dotnet tool install --global dafny
```

Verify: `dafny --version`

---

## How to Use

Point `DATA_DIR` in `test.py` to your folder of generated Dafny code (structured as `code_*/rollout_*/dafny_code_final.dfy`), then run:

```bash
cd metrics/
python3 test.py
```

Passing results are saved to `logs/<index>/rollout_3.dfy`.

## Modules

### `dafny_parser.py`
Low-level helpers: extract solutions from LLM output, fuzzy-match code, tidy Dafny source.

### `spec_utils.py`
Spec extraction & comparison: remove comments/specs, parse `requires`/`ensures` clauses, inject assertions to compare GT vs LLM specs.

Key export: `strip_specs_and_inject_asserts(gt_code, ex_code, key)` → returns modified Dafny code for comparison.

### `equiv_reward.py`
GT spec-to-code equivalence check.

Key export: `create_spec_to_code_check(code)` → returns Dafny code with injected check methods that verify implementation matches its specification.

### `subset_reward.py`
Subset specification reward.

Key export: `create_subset_check(gt_code, gen_code)` → returns Dafny code that checks whether LLM-generated specs are a valid subset of the ground truth.

### `dafny_verifier.py`
Parallel Dafny verification via subprocess.

Key export: `parallel_version_gt_score(command_def, dafny_codes, ...)` → verifies a batch of Dafny programs in parallel, returns pass/fail lists.

### `run_verifier.py`
Orchestrator. Loads data from `code_*/rollout_*/dafny_code_final.dfy`, then runs:
- **GT score** (`gt_score`) — checks spec-to-code equivalence via `create_spec_to_code_check` + parallel verification
- **Subset reward** (`subset_reward`) — checks spec subset via `create_subset_check` + parallel verification

### `unit_test.py`
Translates Python unit tests into Dafny. Takes Python assertions like `assert candidate(args) == expected`, extracts input-output pairs, generates a Dafny `Main()` method that runs those tests, and verifies the results via `dafny run`.

Key functions:
- `extract_input_output_pairs(test_code)` — parses Python test assertions into structured test cases
- `generate_dafny_main_method(dafny_code, test_cases, question_id)` — produces a complete Dafny program with a `Main()` that prints pass/fail for each test
- `execute_dafny_codes_parallel(code_list, max_workers)` — runs all generated test programs in parallel

> **Note:** Requires an internet connection for LLM-based argument conversion.

---

## File Layout

```
metrics/
├── README.md
├── dafny_parser.py      # Solution extraction, code tidying
├── spec_utils.py        # Spec extraction & assertion injection
├── equiv_reward.py      # GT equivalence check (returns code)
├── subset_reward.py     # Subset spec check (returns code)
├── dafny_verifier.py    # Parallel Dafny verification
├── run_verifier.py      # Orchestrator (process_data, gt_score, subset_reward)
└── unit_test.py         # Translate Python tests → Dafny
```

## Dependency Graph

```
run_verifier.py
├── subset_reward.py
│   ├── dafny_parser.py
│   ├── spec_utils.py
│   └── equiv_reward.py
│       ├── dafny_parser.py
│       └── spec_utils.py
└── dafny_verifier.py
```
