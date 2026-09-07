from pathlib import Path
import hashlib
import re
import subprocess
import sys

PATH = Path("index.html")
EXPECTED_SOURCE = "fc9ad73ab4cd01f9bccb0d616e463f119d381273"
EXPECTED_TARGET = "25a11adf2e81e06dc7807d48ed525ffe6d8779dd"


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def sub_once(text: str, pattern: str, replacement: str, label: str, flags=0) -> str:
    out, n = re.subn(pattern, lambda _m: replacement, text, count=1, flags=flags)
    if n != 1:
        raise RuntimeError(f"{label}: expected one match, got {n}")
    print(f"patched: {label}")
    return out


data = PATH.read_bytes()
source_sha = git_blob_sha(data)
if source_sha != EXPECTED_SOURCE:
    raise SystemExit(f"Refusing to patch unexpected index.html: {source_sha} != {EXPECTED_SOURCE}")

text = data.decode("utf-8")

# 1) The new Main-remark view uses one exact PMS remark selector, not category buttons.
text = sub_once(
    text,
    r'''          <div class="vcc-filter vcc-remark-filter no-print" id="vccRemarkFilter" hidden>\n(?:.|\n)*?          </div>\n\n          <div class="vcc-list no-print">''',
    '''          <div class="vcc-filter vcc-remark-filter no-print" id="vccRemarkFilter" hidden>\n            <label class="vcc-remark-label" for="vccRemarkGroup">Main remark</label>\n            <select id="vccRemarkGroup" aria-label="Filter by main remark">\n              <option value="">All main remarks</option>\n            </select>\n            <button class="vfl" id="vccRemarkReset" type="button">Show all</button>\n          </div>\n\n          <div class="vcc-list no-print">''',
    "replace Main-remark filter controls",
    re.S,
)

# 2) Remove the obsolete category-filter state.
text = sub_once(text, r'  var vccRemarkFilter = "all";\n', '', "remove obsolete remark category state")

# 3) Agencies observed in the daily departures report must be parsed as agencies,
#    otherwise their names leak into Main rem. and create false groups.
text = sub_once(
    text,
    r'    "GBT III BV","TRADEDOUBLER","STUBA"\];',
    '''    "GBT III BV","TRADEDOUBLER","STUBA",\n    // agencies seen in the daily departures list whose name was ending up inside the remark\n    "VENDITO - HOTEL SALES SERVICE","TRIPACTIONS - GERMANY","SINFINITY CTC DOO (DE)",\n    "SINFINITY CTC DOO","GEBR. KNAUF KG","GUEST, LOYALTY","HELMSBRISCOE","TRIPACTIONS"];''',
    "extend travel-agent recognition",
)

# 4) Preserve the PMS split: the first ## segment is the grouping instruction;
#    later ## segments remain row notes.
insert_split = '''  // The PMS "Main rem." column holds one instruction, optionally followed by\n  // extra notes, all separated by ## in the export. The PMS sorts the list on\n  // that leading instruction, so the tool groups on exactly the same thing.\n  function vccSplitRemark(raw){\n    var parts = vccRedact(String(raw || "")).split(/#{2,}/).map(function(p){\n      return p.replace(/#+/g, " ").replace(/\\s+/g, " ").trim();\n    }).filter(function(p){ return p.length > 0; });\n    return {\n      head: (parts[0] || "").slice(0,120),\n      rest: parts.slice(1).join(" \\u00B7 ").slice(0,200),\n      full: parts.join(" ").slice(0,240)\n    };\n  }\n\n'''
text = sub_once(
    text,
    r'(  function vccRedact\(t\)\{(?:.|\n)*?\n  \}\n\n)(  function vccNormRoom\(raw\)\{)',
    lambda_placeholder := '',
    "placeholder",
    re.S,
) if False else text
# Do the insertion without depending on a replacement backreference in sub_once.
m = re.search(r'(  function vccRedact\(t\)\{(?:.|\n)*?\n  \}\n\n)(?=  function vccNormRoom\(raw\)\{)', text, re.S)
if not m:
    raise RuntimeError("insert vccSplitRemark: anchor not found")
text = text[:m.end()] + insert_split + text[m.end():]
print("patched: split Main remark on ##")

# 5) Store the exact group head and extra note on every newly parsed row.
text = sub_once(
    text,
    r'(      var typo = !hasVcc && /VVC/i\.test\(hay\);   // "acVVC" appears in real exports\n)(      rows\.push\(\{)',
    r'''\1      var split = vccSplitRemark(remark);\n\2''',
    "create split remark during parsing",
)
text = sub_once(
    text,
    r'        remark: vccRedact\(remark\)\.replace\(/#\{2,\}/g," "\)\.replace\(/\\s\+/g," "\)\.trim\(\)\.slice\(0,240\),',
    '''        remark: split.full,\n        remarkHead: split.head,\n        remarkRest: split.rest,''',
    "store remark head/rest",
)

# 6) Saved rows from the previous build have only a flattened remark. Repair them
#    conservatively so an open shift remains usable until the next PDF import.
repair_helper = '''  // Rows saved before the list was grouped by Main remark have no head stored.\n  // Rebuild a best-effort one so an old session still groups sensibly; the next\n  // upload replaces it with the exact head from the export.\n  function vccHeadFromStored(text){\n    var t = String(text || "").replace(/\\s+/g," ").trim();\n    if(!t) return "";\n    var m = t.match(/^.{0,40}?\\b(?:VCC|POA|MC|VA)\\b/i);\n    if(m) return m[0].trim();\n    m = t.match(/^Check Connectivity comments/i);\n    if(m) return m[0];\n    return t.length > 55 ? t.slice(0,55).trim() : t;\n  }\n\n'''
anchor = '  function vccRepairSavedRows(list){\n'
pos = text.find(anchor)
if pos < 0:
    raise RuntimeError("insert saved-row repair helper: anchor not found")
text = text[:pos] + repair_helper + text[pos:]
print("patched: add saved-row remark repair helper")
text = sub_once(
    text,
    r'  function vccRepairSavedRows\(list\)\{\n    var changed = false;\n',
    '''  function vccRepairSavedRows(list){\n    var changed = false;\n    list.forEach(function(r){\n      if(typeof r.remarkHead !== "string"){\n        r.remarkHead = vccHeadFromStored(r.remark);\n        r.remarkRest = String(r.remark || "").replace(/\\s+/g," ").trim().slice(r.remarkHead.length).trim();\n        changed = true;\n      }\n    });\n''',
    "repair legacy saved remark fields",
)

# 7) Replace interpreted remark categories with literal PMS groups, alphabetically.
new_groups = '''  // One group per Main remark, exactly the split the PMS list shows: the\n  // instruction before the first ## is the group, anything after it stays on\n  // the row as an extra note. No re-interpreting, no merged categories.\n  function vccMainRemarkGroup(r){\n    var head = String(r.remarkHead || "").replace(/\\s+/g," ").trim();\n    if(!head) return { id:"~none", key:"", label:"No main remark", empty:true };\n    var key = head.toLowerCase();\n    return {\n      id: "rm:" + key,\n      key: key,\n      label: head.length > 90 ? head.slice(0,87).trim() + "\\u2026" : head,\n      empty: false\n    };\n  }\n\n  // PMS sorts blanks first, then the remark text A→Z. Same order here.\n  function vccGroupSort(a, b){\n    if(a.key === b.key) return 0;\n    if(!a.key) return -1;\n    if(!b.key) return 1;\n    return a.key.localeCompare(b.key, undefined, {numeric:true});\n  }\n\n  function vccRemarkGroups(){\n    var groups = {}, order = [];\n    vccRooms.forEach(function(r){\n      var group = vccMainRemarkGroup(r);\n      if(!groups[group.id]){\n        groups[group.id] = { id:group.id, key:group.key, label:group.label, empty:group.empty, count:0 };\n        order.push(group.id);\n      }\n      groups[group.id].count++;\n    });\n    return order.map(function(id){ return groups[id]; }).sort(vccGroupSort);\n  }\n\n  function vccWithRemarkCount(){\n    var n = 0;\n    vccRooms.forEach(function(r){ if(String(r.remarkHead || "").trim()) n++; });\n    return n;\n  }\n\n'''
text = sub_once(
    text,
    r'  var VCC_REMARK_META = \{(?:.|\n)*?(?=  function vccSetMode\(mode\)\{)',
    new_groups,
    "replace remark categorization with exact PMS groups",
    re.S,
)

# 8) Copy/headings for the literal remark view.
text = text.replace(
    '      ? "The same Main remark stays together. Choose a quick filter or one exact comment group."\n',
    '      ? "The list is split by Main remark, in the same order as the PMS. Pick one remark to see only those rooms."\n',
    1,
)
text = text.replace(
    '    if(hAction) hAction.textContent = vccMode === "remarks" ? "Main remark / action" : "Outcome";\n',
    '    if(hAction) hAction.textContent = vccMode === "remarks" ? "Extra note / action" : "Outcome";\n',
    1,
)

# 9) Render/select all literal remark groups, without category filtering.
text = sub_once(
    text,
    r'''    var remarkCounts = vccRemarkCounts\(\);\n(?:.|\n)*?    var filtered = vccRooms\.filter\(function\(r\)\{\n      if\(vccMode === "remarks"\)\{\n(?:.|\n)*?      \}\n      if\(vccFilter === "all"\) return true;''',
    '''    var remarkCount = document.getElementById("vccRemarkCount");\n    if(remarkCount) remarkCount.textContent = vccWithRemarkCount();\n    var groupSelect = document.getElementById("vccRemarkGroup");\n    var allGroups = vccRemarkGroups();\n    if(!allGroups.some(function(group){ return group.id === vccRemarkGroupFilter; })) vccRemarkGroupFilter = "";\n    if(groupSelect){\n      groupSelect.innerHTML = "<option value=''>All main remarks (" + vccRooms.length + ")</option>" +\n        allGroups.map(function(group){\n          return "<option value='" + escapeHtml(group.id) + "'>" + escapeHtml(group.label) + " (" + group.count + ")</option>";\n        }).join("");\n      groupSelect.value = vccRemarkGroupFilter;\n    }\n    var filtered = vccRooms.filter(function(r){\n      if(vccMode === "remarks"){\n        return !vccRemarkGroupFilter || vccMainRemarkGroup(r).id === vccRemarkGroupFilter;\n      }\n      if(vccFilter === "all") return true;''',
    "simplify remark group selector/render filtering",
    re.S,
)
text = sub_once(
    text,
    r'''    \}\)\.sort\(function\(a,b\)\{\n      var priority = \{vcc:1,poa:2,connectivity:3,other:4,none:5\};\n      var groupA = vccMainRemarkGroup\(a\);\n      var groupB = vccMainRemarkGroup\(b\);\n      var groupOrder = vccMode === "remarks"\n        \? priority\[groupA\.family\] - priority\[groupB\.family\] \|\| groupA\.label\.localeCompare\(groupB\.label\)\n        : 0;''',
    '''    }).sort(function(a,b){\n      var groupOrder = vccMode === "remarks"\n        ? vccGroupSort(vccMainRemarkGroup(a), vccMainRemarkGroup(b))\n        : 0;''',
    "sort remark groups like PMS",
)
text = sub_once(
    text,
    r'''      var meta = "<span class='vrow-meta'>" \+\n        \(vccMode === "remarks" && r\.pay !== "VCC"\n          \? escapeHtml\(remarkGroup\.label\)\n          : \(r\.status \? escapeHtml\(\(\{charged:"Charged",failed:"Failed",other:"No VCC"\}\)\[r\.status\] \|\| r\.status\) \+''',
    '''      var extraNote = String(r.remarkRest || "").replace(/\\s+/g," ").trim();\n      var meta = "<span class='vrow-meta'>" +\n        (vccMode === "remarks" && r.pay !== "VCC"\n          ? (extraNote ? escapeHtml(extraNote.length > 90 ? extraNote.slice(0,87) + "\\u2026" : extraNote) : "\\u2014")\n          : (r.status ? escapeHtml(({charged:"Charged",failed:"Failed",other:"No VCC"})[r.status] || r.status) +''',
    "show extra remark note as row action",
    re.S,
)

# 10) Replace category-button listener with a simple Show all reset.
text = sub_once(
    text,
    r'''  document\.getElementById\("vccRemarkFilter"\)\.addEventListener\("click", function\(e\)\{(?:.|\n)*?  \}\);\n\n(?=  document\.getElementById\("vccRemarkGroup"\)\.addEventListener)''',
    '''  document.getElementById("vccRemarkReset").addEventListener("click", function(){\n    vccRemarkGroupFilter = "";\n    var listBox = document.querySelector("#panel-vcc .vcc-list");\n    if(listBox) listBox.scrollTop = 0;\n    renderVcc();\n  });\n\n''',
    "replace remark category listener with reset",
    re.S,
)

# Required markers from the uploaded version.
required = [
    'id="vccRemarkReset"',
    '"VENDITO - HOTEL SALES SERVICE"',
    'function vccSplitRemark(raw)',
    'remarkHead: split.head',
    'function vccHeadFromStored(text)',
    'function vccGroupSort(a, b)',
    'All main remarks (',
]
for marker in required:
    if marker not in text:
        raise RuntimeError(f"missing expected marker after patch: {marker}")
if 'var vccRemarkFilter = "all";' in text or 'data-rf=' in text:
    raise RuntimeError("old remark category UI/state still present")

out = text.encode("utf-8")
PATH.write_bytes(out)
final_sha = git_blob_sha(out)
print(f"source blob: {source_sha}")
print(f"final blob:  {final_sha}")
print(f"target blob: {EXPECTED_TARGET}")

# Syntax validation of every inline script block.
blocks = re.findall(r'<script([^>]*)>(.*?)</script\\s*>', text, flags=re.I | re.S)
checked = 0
for i, (attrs, body) in enumerate(blocks):
    if re.search(r'\\bsrc\\s*=', attrs, re.I):
        continue
    tmp = Path(f"/tmp/frontdesk_script_{i}.js")
    tmp.write_text(body, encoding="utf-8")
    subprocess.run(["node", "--check", str(tmp)], check=True)
    checked += 1
print(f"inline JS syntax blocks checked: {checked}")

# Exact equality is the final guard. If any edit was missed, do not publish.
if final_sha != EXPECTED_TARGET:
    raise SystemExit(f"Patch result does not match uploaded index.html exactly: {final_sha} != {EXPECTED_TARGET}")

print("PATCH_OK_EXACT")
