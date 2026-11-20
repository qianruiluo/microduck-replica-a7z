"""Shared serial selection for newly built A7Z images (never touches a board)."""
import re
import tomllib

DEFAULT_SERVO_PORT = "/dev/ttyACM0"
SERVO_PORTS = (DEFAULT_SERVO_PORT, "/dev/ttyS2")


def validate_port(port):
    if port not in SERVO_PORTS:
        raise ValueError("unsupported servo port: " + str(port))
    return port


def bus_port_config(text, port):
    """Change only an existing [bus] port, preserving all other configuration."""
    validate_port(port)
    original = tomllib.loads(text)
    if not isinstance(original.get("bus", {}).get("port"), str):
        raise ValueError("profile must contain [bus] port")
    lines = text.splitlines(keepends=True)
    in_bus = False
    changed = 0
    for i, line in enumerate(lines):
        if line.lstrip().startswith("["):
            in_bus = bool(re.fullmatch(r"\s*\[\s*(?:bus|\"bus\"|'bus')\s*\]\s*(?:#.*)?", line.strip()))
        if in_bus:
            match = re.fullmatch(r"([ \t]*(?:port|\"port\"|'port')[ \t]*=[ \t]*)(?:\"[^\"]*\"|'[^']*')([^\r\n]*)(\r?\n)?", line)
            if match:
                lines[i] = match[1] + '"' + port + '"' + match[2] + (match[3] or "")
                changed += 1
    if changed != 1:
        raise ValueError("expected one explicit [bus] port assignment")
    result = "".join(lines)
    expected = original.copy()
    expected["bus"] = dict(original["bus"], port=port)
    if tomllib.loads(result) != expected:
        raise ValueError("serial edit changed unrelated configuration")
    return result


def deploy_serial_source(text, port, kind):
    """Adapt only reviewed literals in the staged helper/updater, not source baselines."""
    validate_port(port)
    patterns = {
        "helper": (r'^PORT = "/dev/ttyS2"$', 'PORT = "' + port + '"'),
        "updater": (r"^(ARGS = \[TARGET, '--socket', '/run/robotd.sock', '--params', CONFIG), '--port', '/dev/ttyS2'\]$", r"\1]"),
    }
    pattern, replacement = patterns[kind]
    result, count = re.subn(pattern, replacement, text, flags=re.MULTILINE)
    if count != 1:
        raise ValueError("unrecognized " + kind + " serial baseline; review before building")
    # The updater reads the device's CONFIG instead of reintroducing a fixed CLI port.
    return result
