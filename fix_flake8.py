import subprocess
import re
import os

result = subprocess.run(['flake8', 'dct/'], capture_output=True, text=True)

for line in result.stdout.split('\n'):
    if not line:
        continue
    if "F841" in line:
        # F841 local variable 't_start' is assigned to but never used
        m = re.search(r"([^:]+):(\d+):\d+: F841 local variable '([^']+)'", line)
        if m:
            file_path = m.group(1)
            line_num = int(m.group(2))
            var_name = m.group(3)
            with open(file_path, "r") as f:
                lines = f.readlines()
            
            # Simple fix: comment out the assignment or add a dummy use
            if var_name in lines[line_num - 1]:
                lines[line_num - 1] = lines[line_num - 1].replace(var_name, "_" + var_name)
            
            with open(file_path, "w") as f:
                f.writelines(lines)
