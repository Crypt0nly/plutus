#!/usr/bin/env python3
"""Code Analysis Worker — performs AST-based code analysis in a subprocess.

Protocol: JSON over stdin/stdout (one line per message).

Supported actions:
  - analyze: Full analysis of a Python file (AST, complexity, imports, etc.)
  - parse_ast: Parse and return AST structure
  - find_functions: Find all function/method definitions
  - find_classes: Find all class definitions
  - find_imports: Extract all imports
  - find_todos: Find TODO/FIXME/HACK comments
  - complexity: Calculate cyclomatic complexity
  - dependencies: Analyze file dependencies
  - lint: Basic lint checks (unused imports, undefined names, etc.)
  - symbols: Extract all symbols (functions, classes, variables)
  - call_graph: Build a call graph for the file
  - summarize: Generate a human-readable summary of the code
  - quit: Shut down the worker
"""

import ast
import json
import os
import re
import signal
import sys
import tokenize
from io import StringIO
from pathlib import Path


def parse_file(path: str) -> tuple[ast.Module | None, str, str | None]:
    """Parse a Python file and return (tree, source, error)."""
    try:
        p = Path(path).expanduser().resolve()
        if not p.exists():
            return None, "", f"File not found: {path}"
        source = p.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source, filename=str(p))
        return tree, source, None
    except SyntaxError as e:
        return None, "", f"Syntax error at line {e.lineno}: {e.msg}"
    except Exception as e:
        return None, "", str(e)


def find_functions(tree: ast.Module, source: str) -> list[dict]:
    """Extract all function and method definitions."""
    functions = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = []
            for arg in node.args.args:
                annotation = ""
                if arg.annotation:
                    annotation = ast.get_source_segment(source, arg.annotation) or ""
                args.append({
                    "name": arg.arg,
                    "annotation": annotation,
                })

            return_annotation = ""
            if node.returns:
                return_annotation = ast.get_source_segment(source, node.returns) or ""

            decorators = []
            for dec in node.decorator_list:
                dec_text = ast.get_source_segment(source, dec) or ""
                decorators.append(dec_text)

            docstring = ast.get_docstring(node) or ""

            functions.append({
                "name": node.name,
                "type": "async_function" if isinstance(node, ast.AsyncFunctionDef) else "function",
                "line": node.lineno,
                "end_line": node.end_lineno,
                "args": args,
                "return_type": return_annotation,
                "decorators": decorators,
                "docstring": docstring[:200],
                "is_method": isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and any(
                    isinstance(parent, ast.ClassDef)
                    for parent in ast.walk(tree)
                    if hasattr(parent, "body") and node in getattr(parent, "body", [])
                ),
            })
    return functions


def find_classes(tree: ast.Module, source: str) -> list[dict]:
    """Extract all class definitions."""
    classes = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            bases = []
            for base in node.bases:
                base_text = ast.get_source_segment(source, base) or ""
                bases.append(base_text)

            methods = []
            attributes = []
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    methods.append(item.name)
                elif isinstance(item, ast.Assign):
                    for target in item.targets:
                        if isinstance(target, ast.Name):
                            attributes.append(target.id)

            docstring = ast.get_docstring(node) or ""

            classes.append({
                "name": node.name,
                "line": node.lineno,
                "end_line": node.end_lineno,
                "bases": bases,
                "methods": methods,
                "attributes": attributes,
                "docstring": docstring[:200],
                "method_count": len(methods),
            })
    return classes


def find_imports(tree: ast.Module) -> list[dict]:
    """Extract all import statements."""
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append({
                    "module": alias.name,
                    "alias": alias.asname,
                    "line": node.lineno,
                    "type": "import",
                })
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                imports.append({
                    "module": module,
                    "name": alias.name,
                    "alias": alias.asname,
                    "line": node.lineno,
                    "type": "from_import",
                })
    return imports


def find_todos(source: str) -> list[dict]:
    """Find TODO, FIXME, HACK, XXX comments."""
    todos = []
    pattern = re.compile(r"#\s*(TODO|FIXME|HACK|XXX|NOTE|BUG)\b[:\s]*(.*)", re.IGNORECASE)
    for i, line in enumerate(source.splitlines(), 1):
        match = pattern.search(line)
        if match:
            todos.append({
                "line": i,
                "type": match.group(1).upper(),
                "text": match.group(2).strip(),
            })
    return todos


def calculate_complexity(tree: ast.Module) -> list[dict]:
    """Calculate cyclomatic complexity for each function."""
    results = []

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            complexity = 1  # Base complexity

            for child in ast.walk(node):
                if isinstance(child, (ast.If, ast.While, ast.For, ast.AsyncFor)):
                    complexity += 1
                elif isinstance(child, ast.ExceptHandler):
                    complexity += 1
                elif isinstance(child, ast.BoolOp):
                    complexity += len(child.values) - 1
                elif isinstance(child, ast.Assert):
                    complexity += 1
                elif isinstance(child, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
                    complexity += 1

            rating = "A" if complexity <= 5 else "B" if complexity <= 10 else "C" if complexity <= 20 else "F"

            results.append({
                "name": node.name,
                "line": node.lineno,
                "complexity": complexity,
                "rating": rating,
            })

    return results


def extract_symbols(tree: ast.Module) -> dict:
    """Extract all top-level symbols."""
    symbols = {
        "functions": [],
        "classes": [],
        "variables": [],
        "constants": [],
    }

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            symbols["functions"].append({"name": node.name, "line": node.lineno})
        elif isinstance(node, ast.ClassDef):
            symbols["classes"].append({"name": node.name, "line": node.lineno})
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    name = target.id
                    if name.isupper():
                        symbols["constants"].append({"name": name, "line": node.lineno})
                    else:
                        symbols["variables"].append({"name": name, "line": node.lineno})

    return symbols


def build_call_graph(tree: ast.Module) -> dict:
    """Build a simple call graph showing which functions call which."""
    graph = {}

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            calls = set()
            for child in ast.walk(node):
                if isinstance(child, ast.Call):
                    if isinstance(child.func, ast.Name):
                        calls.add(child.func.id)
                    elif isinstance(child.func, ast.Attribute):
                        calls.add(child.func.attr)
            graph[node.name] = sorted(calls)

    return graph


def summarize_file(path: str, tree: ast.Module, source: str) -> dict:
    """Generate a comprehensive summary of a Python file."""
    lines = source.splitlines()
    functions = find_functions(tree, source)
    classes = find_classes(tree, source)
    imports = find_imports(tree)
    todos = find_todos(source)
    complexity = calculate_complexity(tree)

    # Count comment lines
    comment_lines = sum(1 for line in lines if line.strip().startswith("#"))
    blank_lines = sum(1 for line in lines if not line.strip())
    code_lines = len(lines) - comment_lines - blank_lines

    # Module docstring
    module_doc = ast.get_docstring(tree) or ""

    avg_complexity = (
        sum(c["complexity"] for c in complexity) / len(complexity)
        if complexity
        else 0
    )

    return {
        "path": path,
        "total_lines": len(lines),
        "code_lines": code_lines,
        "comment_lines": comment_lines,
        "blank_lines": blank_lines,
        "module_docstring": module_doc[:300],
        "function_count": len(functions),
        "class_count": len(classes),
        "import_count": len(imports),
        "todo_count": len(todos),
        "avg_complexity": round(avg_complexity, 1),
        "functions": [{"name": f["name"], "line": f["line"]} for f in functions],
        "classes": [{"name": c["name"], "line": c["line"], "methods": c["method_count"]} for c in classes],
        "top_imports": [i["module"] for i in imports[:10]],
    }


def full_analysis(path: str) -> dict:
    """Perform a complete analysis of a Python file."""
    tree, source, error = parse_file(path)
    if error:
        return {"success": False, "error": error}

    return {
        "success": True,
        "result": {
            "summary": summarize_file(path, tree, source),
            "functions": find_functions(tree, source),
            "classes": find_classes(tree, source),
            "imports": find_imports(tree),
            "todos": find_todos(source),
            "complexity": calculate_complexity(tree),
            "symbols": extract_symbols(tree),
            "call_graph": build_call_graph(tree),
        },
    }


def handle_command(cmd: dict) -> dict:
    """Route a command to the appropriate handler."""
    action = cmd.get("action", "")
    path = cmd.get("path", "")

    if action == "quit":
        return {"success": True, "result": "goodbye"}

    if action == "analyze":
        return full_analysis(path)

    # All other actions need a parsed tree
    tree, source, error = parse_file(path)
    if error:
        return {"success": False, "error": error}

    handlers = {
        "parse_ast": lambda: {"success": True, "result": {"ast": ast.dump(tree, indent=2)[:5000]}},
        "find_functions": lambda: {"success": True, "result": find_functions(tree, source)},
        "find_classes": lambda: {"success": True, "result": find_classes(tree, source)},
        "find_imports": lambda: {"success": True, "result": find_imports(tree)},
        "find_todos": lambda: {"success": True, "result": find_todos(source)},
        "complexity": lambda: {"success": True, "result": calculate_complexity(tree)},
        "symbols": lambda: {"success": True, "result": extract_symbols(tree)},
        "call_graph": lambda: {"success": True, "result": build_call_graph(tree)},
        "summarize": lambda: {"success": True, "result": summarize_file(path, tree, source)},
    }

    handler = handlers.get(action)
    if not handler:
        return {"success": False, "error": f"Unknown action: {action}"}

    try:
        return handler()
    except Exception as e:
        return {"success": False, "error": str(e)}


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
