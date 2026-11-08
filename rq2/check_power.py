"""Lists every power sensor LibreHardwareMonitor reports, so we know which name to use.

    python check_power.py
"""
import json
import urllib.request

with urllib.request.urlopen("http://127.0.0.1:8085/data.json", timeout=3) as r:
    tree = json.load(r)


def walk(node, path):
    here = path + [node.get("Text", "")]
    value = str(node.get("Value", ""))
    if value.endswith(" W"):
        print(f"{value:>10}   {' > '.join(here[1:])}")
    for child in node.get("Children", []):
        walk(child, here)


walk(tree, [])
