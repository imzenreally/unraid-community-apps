#!/usr/bin/env python3
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
errors: list[str] = []


def check(condition: bool, message: str) -> None:
    if not condition:
        errors.append(message)


profile_path = ROOT / "ca_profile.xml"
check(profile_path.exists(), "ca_profile.xml is missing")
if profile_path.exists():
    profile = ET.parse(profile_path).getroot()
    check(profile.tag == "CommunityApplications", "ca_profile.xml has the wrong root element")
    check(bool((profile.findtext("Profile") or "").strip()), "repository Profile is empty")

screenshots = ROOT / "assets" / "worldmonitor-dashboard.png"
check(screenshots.exists(), "dashboard screenshot is missing")

templates = sorted((ROOT / "templates").glob("*.xml"))
check(bool(templates), "no Docker templates found")
for path in templates:
    text = path.read_text()
    check("YOUR_" not in text and "REPLACE_ME" not in text, f"{path.name} contains a placeholder")
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        errors.append(f"{path.name} is not valid XML: {exc}")
        continue
    check(root.tag == "Container", f"{path.name} root must be Container")
    check(root.attrib.get("version") == "2", f"{path.name} must use Container version 2")
    for tag in ("Name", "Repository", "Registry", "Network", "WebUI", "Overview", "Support", "Project", "TemplateURL", "ReadMe", "Category", "License"):
        check(bool((root.findtext(tag) or "").strip()), f"{path.name} is missing {tag}")
    name = root.findtext("Name") or ""
    check(name == "WorldMonitorAIO-Unofficial", f"{path.name} must identify the package as unofficial")
    check(bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", name)), f"{path.name} Name must be a valid Docker container name")
    check(root.findtext("Repository") == "ghcr.io/imzenreally/worldmonitor-unraid-aio:beta", f"{path.name} has the wrong beta image")
    check(root.findtext("Registry") == "https://github.com/users/imzenreally/packages/container/package/worldmonitor-unraid-aio", f"{path.name} has the wrong package page")
    check(root.findtext("Beta") == "true", f"{path.name} must be marked beta")
    check(root.findtext("License") == "AGPL-3.0-only", f"{path.name} has the wrong image license")
    check(root.findtext("Privileged") == "false", f"{path.name} must not be privileged")
    check(root.findtext("Network") == "bridge", f"{path.name} must use bridge networking")
    extra = root.findtext("ExtraParams") or ""
    for option in ("--read-only", "no-new-privileges", "--cap-drop=ALL", "--cap-add=CHOWN", "--cap-add=FOWNER", "--cap-add=SETUID", "--cap-add=SETGID"):
        check(option in extra, f"{path.name} is missing hardening option {option}")
    configs = root.findall("Config")
    targets = [item.attrib.get("Target") for item in configs]
    check(len(targets) == len(set(targets)), f"{path.name} has duplicate Config targets")
    required_provider_targets = {
        "OPENSKY_CLIENT_ID",
        "OPENSKY_CLIENT_SECRET",
        "OLLAMA_API_URL",
        "OLLAMA_API_KEY",
        "OLLAMA_MODEL",
    }
    check(required_provider_targets.issubset(set(targets)), f"{path.name} is missing required OpenSky/Ollama fields")
    for item in configs:
        target = item.attrib.get("Target", "")
        if any(marker in target for marker in ("KEY", "TOKEN", "PASSWORD", "SECRET")):
            check(item.attrib.get("Mask") == "true", f"{path.name}: {target} must be masked")

if errors:
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)
    raise SystemExit(1)
print(f"PASS: validated {len(templates)} Community Applications template(s)")
