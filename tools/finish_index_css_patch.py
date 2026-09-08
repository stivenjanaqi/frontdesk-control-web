from pathlib import Path
import hashlib

PATH = Path("index.html")
EXPECTED_BEFORE = "de90a434f09d37900d992c88f71b7ae30212f6cc"
EXPECTED_TARGET = "25a11adf2e81e06dc7807d48ed525ffe6d8779dd"


def blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


data = PATH.read_bytes()
sha = blob_sha(data)
if sha != EXPECTED_BEFORE:
    raise SystemExit(f"Unexpected pre-CSS blob: {sha} != {EXPECTED_BEFORE}")
text = data.decode("utf-8")

anchor = '  .vfl:focus-visible{outline:2px solid var(--navy); outline-offset:2px;}\n\n'
css = '''  .vcc-remark-filter{align-items:center; gap:8px;}\n  .vcc-remark-label{\n    font:800 11px/1 var(--sans); letter-spacing:.06em; text-transform:uppercase; color:var(--ink-muted);\n  }\n  #vccRemarkGroup{\n    flex:1; min-width:200px; max-width:100%; border:1.5px solid var(--line); border-radius:999px;\n    background:#fff; color:var(--navy); padding:7px 12px; font:650 13px var(--sans); cursor:pointer;\n  }\n  #vccRemarkGroup:focus-visible{outline:2px solid var(--navy); outline-offset:2px;}\n  .vcc-grouphead{\n    display:flex; align-items:center; justify-content:space-between; gap:12px;\n    padding:9px 12px; background:#e8eef7; border-top:1px solid #ccd8e8; border-bottom:1px solid #ccd8e8;\n    color:var(--navy); font:800 12.5px/1.35 var(--sans);\n  }\n  .vcc-grouphead:first-child{border-top:0;}\n  .vcc-grouphead span:last-child{\n    flex:none; border-radius:999px; background:#fff; padding:2px 8px; font:800 12px/1.4 var(--mono);\n  }\n\n'''
if text.count(anchor) != 1:
    raise SystemExit(f"CSS anchor count is {text.count(anchor)}, expected 1")
text = text.replace(anchor, anchor + css, 1)

report_anchor = '''    ]));\n\n    if(charged.length){'''
report_insert = '''    ]));\n\n    var remarkGroups = vccRemarkGroups();\n    if(remarkGroups.length){\n      out += bfSection("Main remarks on the list", naTable(["Main remark","Rooms"],\n        remarkGroups.map(function(group){\n          return [escapeHtml(group.label), { v:group.count, mono:true }];\n        })));\n    }\n\n    if(charged.length){'''
if text.count(report_anchor) != 1:
    raise SystemExit(f"VCC report anchor count is {text.count(report_anchor)}, expected 1")
text = text.replace(report_anchor, report_insert, 1)

out = text.encode("utf-8")
PATH.write_bytes(out)
final = blob_sha(out)
print(f"pre-CSS blob: {sha}")
print(f"final blob:   {final}")
print(f"target blob:  {EXPECTED_TARGET}")
print(f"final bytes:  {len(out)}")
if final != EXPECTED_TARGET:
    raise SystemExit(f"Final blob still differs from uploaded index: {final} != {EXPECTED_TARGET}")
print("EXACT_UPLOAD_MATCH")
