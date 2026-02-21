#!/usr/bin/env python3
"""Shell Worker — executes shell commands in a sandboxed subprocess.

Protocol: reads JSON commands from stdin, writes JSON results to stdout.
Each command is a single line of JSON, each response is a single line of JSON.

Command format:
  {"action": "exec", "command": "ls -la", "timeout": 30, "cwd": "/tmp"}
  {"action": "exec_many", "commands": ["cmd1", "cmd2"], "timeout": 30}
  {"action": "quit"}

Response format:
  {"success": true, "result": {"stdout": "...", "stderr": "...", "returncode": 0}}
  {"success": false, "error": "..."}
"""

import json
import os
import subprocess
import sys
import signal


def execute_command(command: str, timeout: float = 30.0, cwd: str | None = None) -> dict:
    """Execute a single shell command and return structured output."""
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd or os.getcwd(),
            env={**os.environ},
        )
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {
            "stdout": "",
            "stderr": f"Command timed out after {timeout}s",
            "returncode": -1,
        }
    except Exception as e:
        return {
            "stdout": "",
            "stderr": str(e),
            "returncode": -1,
        }


def handle_command(cmd: dict) -> dict:
    """Process a single command and return the response."""
    action = cmd.get("action", "exec")

    if action == "quit":
        return {"success": True, "result": "goodbye"}

    if action == "exec":
        command = cmd.get("command", "")
        timeout = cmd.get("timeout", 30.0)
        cwd = cmd.get("cwd")
        if not command:
            return {"success": False, "error": "No command provided"}
        result = execute_command(command, timeout, cwd)
        success = result["returncode"] == 0
        return {"success": success, "result": result, "error": result["stderr"] if not success else None}

    if action == "exec_many":
        commands = cmd.get("commands", [])
        timeout = cmd.get("timeout", 30.0)
        cwd = cmd.get("cwd")
        results = []
        for command in commands:
            result = execute_command(command, timeout, cwd)
            results.append(result)
        all_success = all(r["returncode"] == 0 for r in results)
        return {"success": all_success, "result": results}

    return {"success": False, "error": f"Unknown action: {action}"}


def main():
    """Main loop: read JSON commands from stdin, write JSON responses to stdout."""
    # Ignore SIGINT in the worker — let the parent handle it
    signal.signal(signal.SIGINT, signal.SIG_IGN)

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            cmd = json.loads(line)
        except json.JSONDecodeError as e:
            response = {"success": False, "error": f"Invalid JSON: {e}"}
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()
            continue

        response = handle_command(cmd)
        sys.stdout.write(json.dumps(response) + "\n")
        sys.stdout.flush()

        if cmd.get("action") == "quit":
            break


if __name__ == "__main__":
    main()
