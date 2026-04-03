with open("tests/test_providers.py", "r") as f:
    lines = f.readlines()
with open("tests/test_providers.py", "w") as f:
    for line in lines:
        if line.startswith("import pytest"):
            continue
        f.write(line)

with open("tests/test_registry.py", "r") as f:
    lines = f.readlines()
with open("tests/test_registry.py", "w") as f:
    for line in lines:
        if line.startswith("import pytest") or line.startswith("import os"):
            continue
        f.write(line)
