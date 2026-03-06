# VeriEquivBench: An Equivalence Score for Ground-Truth-Free Evaluation of Formally Verifiable Code

## Dataset Overview

VeriEquivBench provides a comprehensive collection of verifiable Dafny programs for benchmarking verification tools, enabling ground-truth-free evaluation through equivalence scoring.


## Hugging Face Dataset

📊 **[View on Hugging Face](https://huggingface.co/datasets/FengdiFlo/VeriEquivBench/viewer/bench)**

Explore the dataset online with the Hugging Face Dataset Viewer.


## Dataset Components

###  `bench.json`
- **2,174** self-contained Dafny programs
- Each program is **verifiable** with complete implementations


###  `SpecGen.json` 
- **2,018** specification-only baselines


###  `SpecRefine.json`
- Refined versions of the SpecGen dataset
- Features enhanced specifications including:
  - Stronger invariants
  - Loop variants
  - Additional verification constructs



## Citation
If you find the code useful, please cite our paper:

```bibtex
@inproceedings{veriequiv2025,
  title     = {VeriEquivBench: An Equivalence Score for Ground-Truth-Free Evaluation of Formally Verifiable Code},
  author    = {Zeng, Lingfei and Che, Fengdi and Huang, Xuhan and Ye, Fei and Xu, Xu and Yuan, Binhang and Fu, Jie and Chen, Lin and Chen, Zehui and Chen, Huaian and Ouyang, Wanli and Zhao, Feng},
  booktitle = {Proceedings of the 2025 Conference on <Conference-Name>},
  year      = {2025}
}