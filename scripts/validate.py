#!/usr/bin/env python3
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_RAW = "https://raw.githubusercontent.com/imzenreally/unraid-community-apps/main"
errors: list[str] = []


def check(condition: bool, message: str) -> None:
    if not condition:
        errors.append(message)


def config_by_target(root: ET.Element) -> dict[str, ET.Element]:
    return {item.attrib.get("Target", ""): item for item in root.findall("Config")}


profile_path = ROOT / "ca_profile.xml"
check(profile_path.exists(), "ca_profile.xml is missing")
if profile_path.exists():
    profile = ET.parse(profile_path).getroot()
    check(profile.tag == "CommunityApplications", "ca_profile.xml has the wrong root element")
    check(bool((profile.findtext("Profile") or "").strip()), "repository Profile is empty")
    check((profile.findtext("WebPage") or "").strip() == "https://github.com/imzenreally/unraid-community-apps", "repository WebPage is wrong")

for asset in ("worldmonitor-dashboard.png", "openwebrxplus.png"):
    check((ROOT / "assets" / asset).exists(), f"required asset is missing: {asset}")

templates = sorted((ROOT / "templates").glob("*.xml"))
check(bool(templates), "no Docker templates found")
seen_names: set[str] = set()

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
    for tag in (
        "Name", "Repository", "Registry", "Network", "WebUI", "Overview",
        "Description", "Support", "Project", "TemplateURL", "ReadMe",
        "Category", "License", "Requires", "Changes", "Date",
    ):
        check(bool((root.findtext(tag) or "").strip()), f"{path.name} is missing {tag}")

    name = (root.findtext("Name") or "").strip()
    check(bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", name)), f"{path.name} Name must be a valid Docker container name")
    check(name not in seen_names, f"duplicate application Name: {name}")
    seen_names.add(name)

    check(root.findtext("Privileged") == "false", f"{path.name} must not be privileged")
    check(root.findtext("TemplateURL") == f"{REPOSITORY_RAW}/templates/{path.name}", f"{path.name} has the wrong TemplateURL")
    check(root.findtext("ReadMe") == f"{REPOSITORY_RAW}/README.md", f"{path.name} has the wrong ReadMe URL")
    check(not (root.findtext("PostArgs") or "").strip(), f"{path.name} must not run post-install commands")

    configs = root.findall("Config")
    targets = [item.attrib.get("Target", "") for item in configs]
    check(len(targets) == len(set(targets)), f"{path.name} has duplicate Config targets")
    for item in configs:
        target = item.attrib.get("Target", "")
        if any(marker in target for marker in ("KEY", "TOKEN", "PASSWORD", "SECRET")):
            check(item.attrib.get("Mask") == "true", f"{path.name}: {target} must be masked")

    config = config_by_target(root)

    if path.name == "worldmonitor-aio.xml":
        check(name == "WorldMonitorAIO-Unofficial", f"{path.name} must identify the package as unofficial")
        check(root.findtext("Repository") == "ghcr.io/imzenreally/worldmonitor-unraid-aio:beta", f"{path.name} has the wrong beta image")
        check(root.findtext("Registry") == "https://github.com/users/imzenreally/packages/container/package/worldmonitor-unraid-aio", f"{path.name} has the wrong package page")
        check(root.findtext("Beta") == "true", f"{path.name} must be marked beta")
        check(root.findtext("License") == "AGPL-3.0-only", f"{path.name} has the wrong image license")
        check(root.findtext("Network") == "bridge", f"{path.name} must use bridge networking")
        extra = root.findtext("ExtraParams") or ""
        for option in ("--read-only", "no-new-privileges", "--cap-drop=ALL", "--cap-add=CHOWN", "--cap-add=FOWNER", "--cap-add=SETUID", "--cap-add=SETGID"):
            check(option in extra, f"{path.name} is missing hardening option {option}")
        required_targets = {"OPENSKY_CLIENT_ID", "OPENSKY_CLIENT_SECRET", "OLLAMA_API_URL", "OLLAMA_API_KEY", "OLLAMA_MODEL"}
        check(required_targets.issubset(config), f"{path.name} is missing required OpenSky/Ollama fields")

    elif path.name == "openwebrxplus.xml":
        check(name == "OpenWebRX-Plus", f"{path.name} has the wrong application name")
        check(root.findtext("Repository") == "slechev/openwebrxplus-softmbe:latest", f"{path.name} has the wrong image")
        check(root.findtext("Registry") == "https://hub.docker.com/r/slechev/openwebrxplus-softmbe", f"{path.name} has the wrong registry URL")
        check(root.findtext("License") == "AGPL-3.0-only", f"{path.name} has the wrong application license")
        check(root.findtext("Network") == "bridge", f"{path.name} must use bridge networking")
        check("[PORT:8073]" in (root.findtext("WebUI") or ""), f"{path.name} WebUI must use container port 8073")
        check("--tmpfs /tmp:" in (root.findtext("ExtraParams") or ""), f"{path.name} must keep temporary data in tmpfs")
        required_targets = {
            "8073", "/etc/openwebrx", "/var/lib/openwebrx", "/dev/bus/usb",
            "TZ", "OPENWEBRX_ADMIN_USER", "OPENWEBRX_ADMIN_PASSWORD",
        }
        check(required_targets.issubset(config), f"{path.name} is missing required port, path, device, or account fields")
        if "8073" in config:
            check(config["8073"].attrib.get("Type") == "Port", f"{path.name} Web UI must be a Port config")
            check(config["8073"].attrib.get("Mode") == "tcp", f"{path.name} Web UI must use TCP")
        for target in ("/etc/openwebrx", "/var/lib/openwebrx"):
            if target in config:
                check(config[target].attrib.get("Type") == "Path", f"{path.name} {target} must be a Path config")
                check(config[target].attrib.get("Mode") == "rw", f"{path.name} {target} must be read-write")
        if "/dev/bus/usb" in config:
            check(config["/dev/bus/usb"].attrib.get("Type") == "Device", f"{path.name} USB mapping must be a Device config")
        for target in ("TZ", "OPENWEBRX_ADMIN_USER", "OPENWEBRX_ADMIN_PASSWORD"):
            if target in config:
                check(config[target].attrib.get("Type") == "Variable", f"{path.name} {target} must be a Variable config")
        password = config.get("OPENWEBRX_ADMIN_PASSWORD")
        if password is not None:
            check(password.attrib.get("Mask") == "true", f"{path.name} admin password must be masked")
            check(password.attrib.get("Required") == "true", f"{path.name} admin password must be required")
            check(not (password.attrib.get("Default") or ""), f"{path.name} admin password must not have a default")

    else:
        errors.append(f"no app-specific validation is defined for {path.name}")

if errors:
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)
    raise SystemExit(1)
print(f"PASS: validated {len(templates)} Community Applications template(s): {', '.join(sorted(seen_names))}")
