from termstory.parser import parse_bash_history
import tempfile
import os

content = """\
#1698544800
echo "cmd_before_dst_1"
#1698544900
echo "cmd_before_dst_2"
#1698541300
echo "cmd_dst_jump_back_1"
#-9999999999
echo "cmd_negative_timestamp"
#9999999999999
echo "cmd_future_timestamp"
"""

with tempfile.NamedTemporaryFile("w", delete=False) as f:
    f.write(content)
    f.flush()
    commands = parse_bash_history(f.name)
    for c in commands:
        print(f"Time: {c.timestamp}, Command: {c.command}")
    os.remove(f.name)
