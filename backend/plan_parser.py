"""Static layout from plan.xml: blocks, sensors, signals, switches, track geometry.
Only geometry and ids come from here; live state still comes from Rocrail events."""
import xml.etree.ElementTree as ET


def _pick(el, keys):
    return {k: el.attrib[k] for k in keys if k in el.attrib}


def parse_plan(path):
    root = ET.parse(path).getroot()
    out = {"blocks": [], "sensors": [], "signals": [], "switches": [], "tracks": [], "locos": []}
    spec = {
        "bk": ("blocks",  ["id", "x", "y", "cx", "cy", "locid", "len"]),
        "fb": ("sensors", ["id", "x", "y", "cx", "cy", "state"]),
        "sg": ("signals", ["id", "x", "y", "cx", "cy", "type"]),
        "sw": ("switches", ["id", "x", "y", "cx", "cy", "type", "state"]),
        "tk": ("tracks",  ["x", "y", "cx", "cy", "type", "ori"]),
        "lc": ("locos",   ["id", "addr", "blockid", "V", "dir"]),
    }
    for tag, (key, attrs) in spec.items():
        for el in root.iter(tag):
            item = _pick(el, attrs)
            if item:
                out[key].append(item)
    return out