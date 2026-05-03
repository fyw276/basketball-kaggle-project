# -*- coding: utf-8 -*-
import subprocess
import sys

# Add all changes
result = subprocess.run(['git', 'add', '-A'], capture_output=True, text=True)
print("git add:", result.returncode)

# Commit with message
commit_msg = """docs: fix documentation accuracy, add CHANGELOG, and sync docs

Fixed issues:
- README.md: Corrected replace mode engine priority to [warp, bailian, remote, catvton, diffusion]
- warp_engine.py: Fixed docstring reference from tryon_top_warp_preserve to tryon_top_warp
- TRYON_TECH_BLUEPRINT_AB.md: Removed non-existent tryon_engine_selector.py reference
- test_tryon_replace_mode_preservation.py: Updated test docstring to reflect actual priority

Added:
- CHANGELOG.md documenting recent changes and commit history
- CatVTON diagnostic scripts (diagnose_catvton_direct.py, diagnose_catvton_subprocess.py, test_catvton_optimized.py)

All tests pass.
"""

result = subprocess.run(['git', 'commit', '-m', commit_msg], capture_output=True, text=True)
print("git commit:", result.returncode)
print(result.stdout)
print(result.stderr)

if result.returncode == 0:
    # Push
    result = subprocess.run(['git', 'push'], capture_output=True, text=True)
    print("git push:", result.returncode)
    print(result.stdout)
    print(result.stderr)
