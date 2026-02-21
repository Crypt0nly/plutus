#!/usr/bin/env python3
"""Custom Worker — executes dynamically-created tool scripts in a subprocess.

Protocol: JSON over stdin/stdout (one line per message).

This worker is used when Claude creates new tools at runtime. It:
  1. Receives a script path or inline code
  2. Executes it in an isolated namespace
  3. Returns the result

Supported actions:
  - run_script: Execute a Python script file
  - run_inline: Execute inline Python code
  - run_function: Execute a specific function from a script
  - validate: Check if a script is valid Python
  - quit: Shut down the worker
"""

import importlib.util
import json
import os
import signal
import sys
import traceback
from io import StringIO
from pathlib import Path


def run_script(path: str, args: dict | None = None) -> dict:
    """Execute a Python script file and capture its output."""
    try:
        p = Path(path).expanduser().resolve()
        if not p.exists():
            return {"success": False, "error": f"Script not found: {path}"}

        # Capture stdout/stderr
        old_stdout, old_stderr = sys.stdout, sys.stderr
        captured_out = StringIO()
        captured_err = StringIO()
        sys.stdout = captured_out
        sys.stderr = captured_err

        # Create isolated namespace
        namespace = {
            "__name__": "__main__",
            "__file__": str(p),
            "__builtins__": __builtins__,
            "args": args or {},
        }

        try:
            code = p.read_text(encoding="utf-8")
            exec(compile(code, str(p), "exec"), namespace)

            # Check if there's a main() function and call it
            if "main" in namespace and callable(namespace["main"]):
                result = namespace["main"](args or {}) if args else namespace["main"]()
            elif "result" in namespace:
                result = namespace["result"]
            else:
                result = None

            return {
                "success": True,
                "result": {
                    "output": captured_out.getvalue(),
                    "errors": captured_err.getvalue(),
                    "return_value": _serialize(result),
                },
            }
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr

    except Exception as e:
        return {
            "success": False,
            "error": f"{type(e).__name__}: {e}\n{traceback.format_exc()}",
        }


def run_inline(code: str, args: dict | None = None) -> dict:
    """Execute inline Python code."""
    try:
        old_stdout, old_stderr = sys.stdout, sys.stderr
        captured_out = StringIO()
        captured_err = StringIO()
        sys.stdout = captured_out
        sys.stderr = captured_err

        namespace = {
            "__name__": "__main__",
            "__builtins__": __builtins__,
            "args": args or {},
        }

        try:
            exec(compile(code, "<inline>", "exec"), namespace)

            result = namespace.get("result", None)

            return {
                "success": True,
                "result": {
                    "output": captured_out.getvalue(),
                    "errors": captured_err.getvalue(),
                    "return_value": _serialize(result),
                },
            }
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr

    except Exception as e:
        return {
            "success": False,
            "error": f"{type(e).__name__}: {e}\n{traceback.format_exc()}",
        }


def run_function(path: str, function_name: str, args: dict | None = None) -> dict:
    """Execute a specific function from a Python script."""
    try:
        p = Path(path).expanduser().resolve()
        if not p.exists():
            return {"success": False, "error": f"Script not found: {path}"}

        # Load the module
        spec = importlib.util.spec_from_file_location("custom_module", str(p))
        if not spec or not spec.loader:
            return {"success": False, "error": f"Cannot load module from: {path}"}

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # Find and call the function
        func = getattr(module, function_name, None)
        if not func:
            available = [n for n in dir(module) if callable(getattr(module, n)) and not n.startswith("_")]
            return {
                "success": False,
                "error": f"Function '{function_name}' not found. Available: {available}",
            }

        if not callable(func):
            return {"success": False, "error": f"'{function_name}' is not callable"}

        # Call with args
        if args:
            result = func(**args)
        else:
            result = func()

        return {
            "success": True,
            "result": {"return_value": _serialize(result)},
        }

    except Exception as e:
        return {
            "success": False,
            "error": f"{type(e).__name__}: {e}\n{traceback.format_exc()}",
        }


def validate_script(code: str) -> dict:
    """Validate that code is syntactically correct Python."""
    try:
        compile(code, "<validation>", "exec")
        return {
            "success": True,
            "result": {"valid": True, "message": "Script is valid Python"},
        }
    except SyntaxError as e:
        return {
            "success": True,
            "result": {
                "valid": False,
                "message": f"Syntax error at line {e.lineno}: {e.msg}",
                "line": e.lineno,
                "offset": e.offset,
            },
        }


def _serialize(obj):
    """Attempt to serialize an object to JSON-compatible format."""
    if obj is None:
        return None
    if isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, (list, tuple)):
        return [_serialize(item) for item in obj]
    if isinstance(obj, dict):
        return {str(k): _serialize(v) for k, v in obj.items()}
    return str(obj)


def handle_command(cmd: dict) -> dict:
    """Route a command to the appropriate handler."""
    action = cmd.get("action", "")

    if action == "quit":
        return {"success": True, "result": "goodbye"}

    handlers = {
        "run_script": lambda: run_script(cmd.get("path", ""), cmd.get("args")),
        "run_inline": lambda: run_inline(cmd.get("code", ""), cmd.get("args")),
        "run_function": lambda: run_function(
            cmd.get("path", ""),
            cmd.get("function", "main"),
            cmd.get("args"),
        ),
        "validate": lambda: validate_script(cmd.get("code", "")),
    }

    handler = handlers.get(action)
    if not handler:
        return {"success": False, "error": f"Unknown action: {action}"}

    return handler()


def main():
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
