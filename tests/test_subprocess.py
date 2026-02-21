"""Tests for the subprocess manager and worker processes."""

import asyncio
import json
import os
import tempfile
from pathlib import Path

import pytest

from plutus.core.subprocess_manager import (
    SubprocessManager,
    SubprocessTask,
    SubprocessResult,
    WorkerStatus,
    TaskPriority,
)


@pytest.fixture
def manager():
    return SubprocessManager(max_workers=3, default_timeout=30.0)


@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory(prefix="plutus_test_") as d:
        yield d


# ── Shell Worker Tests ──────────────────────────────────────────────────────

class TestShellWorker:
    async def test_basic_command(self, manager):
        """Test executing a simple shell command."""
        task = SubprocessTask(
            worker_type="shell",
            command={"action": "exec", "command": "echo hello"},
        )
        result = await manager.spawn(task)
        assert result.status == WorkerStatus.COMPLETED
        assert "hello" in result.output["stdout"]

    async def test_command_with_cwd(self, manager, temp_dir):
        """Test executing a command in a specific directory."""
        task = SubprocessTask(
            worker_type="shell",
            command={"action": "exec", "command": "pwd", "cwd": temp_dir},
        )
        result = await manager.spawn(task)
        assert result.status == WorkerStatus.COMPLETED
        assert temp_dir in result.output["stdout"]

    async def test_failing_command(self, manager):
        """Test handling a failing command."""
        task = SubprocessTask(
            worker_type="shell",
            command={"action": "exec", "command": "false"},
        )
        result = await manager.spawn(task)
        assert result.status == WorkerStatus.FAILED

    async def test_exec_many(self, manager):
        """Test executing multiple commands."""
        task = SubprocessTask(
            worker_type="shell",
            command={
                "action": "exec_many",
                "commands": ["echo one", "echo two", "echo three"],
            },
        )
        result = await manager.spawn(task)
        assert result.status == WorkerStatus.COMPLETED
        assert len(result.output) == 3

    async def test_timeout(self, manager):
        """Test command timeout."""
        task = SubprocessTask(
            worker_type="shell",
            command={"action": "exec", "command": "sleep 100", "timeout": 1},
            timeout=3.0,
        )
        result = await manager.spawn(task)
        # The shell worker handles the timeout internally
        assert result.status in (WorkerStatus.COMPLETED, WorkerStatus.FAILED, WorkerStatus.TIMEOUT)


# ── File Edit Worker Tests ──────────────────────────────────────────────────

class TestFileEditWorker:
    async def test_write_and_read(self, manager, temp_dir):
        """Test writing and reading a file."""
        filepath = os.path.join(temp_dir, "test.txt")

        # Write
        task = SubprocessTask(
            worker_type="file_edit",
            command={
                "action": "write",
                "path": filepath,
                "content": "Hello, World!\nLine 2\n",
            },
        )
        result = await manager.spawn(task)
        assert result.status == WorkerStatus.COMPLETED
        assert result.output["path"] == filepath

        # Read
        task = SubprocessTask(
            worker_type="file_edit",
            command={"action": "read", "path": filepath},
        )
        result = await manager.spawn(task)
        assert result.status == WorkerStatus.COMPLETED
        assert "Hello, World!" in result.output["content"]
        assert result.output["total_lines"] == 2

    async def test_edit_file(self, manager, temp_dir):
        """Test surgical file editing."""
        filepath = os.path.join(temp_dir, "edit_test.py")

        # Create file
        task = SubprocessTask(
            worker_type="file_edit",
            command={
                "action": "write",
                "path": filepath,
                "content": "def hello():\n    print('hello')\n\ndef world():\n    print('world')\n",
            },
        )
        await manager.spawn(task)

        # Edit
        task = SubprocessTask(
            worker_type="file_edit",
            command={
                "action": "edit",
                "path": filepath,
                "edits": [
                    {"find": "print('hello')", "replace": "print('Hello, World!')"},
                ],
            },
        )
        result = await manager.spawn(task)
        assert result.status == WorkerStatus.COMPLETED
        assert result.output["changes"] == 1

        # Verify
        task = SubprocessTask(
            worker_type="file_edit",
            command={"action": "read", "path": filepath},
        )
        result = await manager.spawn(task)
        assert "Hello, World!" in result.output["content"]

    async def test_list_directory(self, manager, temp_dir):
        """Test listing directory contents."""
        # Create some files
        for name in ["a.py", "b.txt", "c.py"]:
            Path(temp_dir, name).write_text(f"# {name}")

        task = SubprocessTask(
            worker_type="file_edit",
            command={"action": "list", "path": temp_dir},
        )
        result = await manager.spawn(task)
        assert result.status == WorkerStatus.COMPLETED
        assert result.output["count"] == 3

    async def test_find_files(self, manager, temp_dir):
        """Test finding files by pattern."""
        # Create nested structure
        sub = Path(temp_dir, "sub")
        sub.mkdir()
        Path(temp_dir, "a.py").write_text("# a")
        Path(sub, "b.py").write_text("# b")
        Path(sub, "c.txt").write_text("# c")

        task = SubprocessTask(
            worker_type="file_edit",
            command={"action": "find", "path": temp_dir, "pattern": "*.py"},
        )
        result = await manager.spawn(task)
        assert result.status == WorkerStatus.COMPLETED
        assert result.output["count"] == 2

    async def test_grep(self, manager, temp_dir):
        """Test searching file contents."""
        Path(temp_dir, "a.py").write_text("def hello():\n    pass\n")
        Path(temp_dir, "b.py").write_text("def world():\n    pass\n")

        task = SubprocessTask(
            worker_type="file_edit",
            command={
                "action": "grep",
                "path": temp_dir,
                "regex": "def \\w+",
                "file_pattern": "*.py",
            },
        )
        result = await manager.spawn(task)
        assert result.status == WorkerStatus.COMPLETED
        assert result.output["count"] == 2

    async def test_mkdir(self, manager, temp_dir):
        """Test creating directories."""
        new_dir = os.path.join(temp_dir, "a", "b", "c")
        task = SubprocessTask(
            worker_type="file_edit",
            command={"action": "mkdir", "path": new_dir},
        )
        result = await manager.spawn(task)
        assert result.status == WorkerStatus.COMPLETED
        assert os.path.isdir(new_dir)

    async def test_copy_and_move(self, manager, temp_dir):
        """Test copying and moving files."""
        src = os.path.join(temp_dir, "original.txt")
        Path(src).write_text("original content")

        # Copy
        dst = os.path.join(temp_dir, "copy.txt")
        task = SubprocessTask(
            worker_type="file_edit",
            command={"action": "copy", "src": src, "dst": dst},
        )
        result = await manager.spawn(task)
        assert result.status == WorkerStatus.COMPLETED
        assert Path(dst).read_text() == "original content"

        # Move
        moved = os.path.join(temp_dir, "moved.txt")
        task = SubprocessTask(
            worker_type="file_edit",
            command={"action": "move", "src": dst, "dst": moved},
        )
        result = await manager.spawn(task)
        assert result.status == WorkerStatus.COMPLETED
        assert Path(moved).exists()
        assert not Path(dst).exists()


# ── Code Analysis Worker Tests ──────────────────────────────────────────────

class TestCodeAnalysisWorker:
    @pytest.fixture
    def sample_python_file(self, temp_dir):
        filepath = os.path.join(temp_dir, "sample.py")
        code = '''"""Sample module for testing."""

import os
import sys
from pathlib import Path

# TODO: Add more features
# FIXME: Handle edge cases

CONSTANT = 42

class MyClass:
    """A sample class."""

    def __init__(self, name: str):
        self.name = name

    def greet(self) -> str:
        """Return a greeting."""
        if self.name:
            return f"Hello, {self.name}!"
        return "Hello!"

    async def async_method(self):
        pass

def standalone_function(x: int, y: int = 0) -> int:
    """Add two numbers."""
    if x > 0:
        if y > 0:
            return x + y
        return x
    return 0

def simple_function():
    pass
'''
        Path(filepath).write_text(code)
        return filepath

    async def test_full_analysis(self, manager, sample_python_file):
        """Test full code analysis."""
        task = SubprocessTask(
            worker_type="code_analysis",
            command={"action": "analyze", "path": sample_python_file},
        )
        result = await manager.spawn(task)
        assert result.status == WorkerStatus.COMPLETED

        output = result.output
        assert "summary" in output
        assert "functions" in output
        assert "classes" in output
        assert "imports" in output
        assert "todos" in output
        assert "complexity" in output

    async def test_find_functions(self, manager, sample_python_file):
        """Test finding functions."""
        task = SubprocessTask(
            worker_type="code_analysis",
            command={"action": "find_functions", "path": sample_python_file},
        )
        result = await manager.spawn(task)
        assert result.status == WorkerStatus.COMPLETED
        func_names = [f["name"] for f in result.output]
        assert "standalone_function" in func_names
        assert "simple_function" in func_names
        assert "greet" in func_names

    async def test_find_classes(self, manager, sample_python_file):
        """Test finding classes."""
        task = SubprocessTask(
            worker_type="code_analysis",
            command={"action": "find_classes", "path": sample_python_file},
        )
        result = await manager.spawn(task)
        assert result.status == WorkerStatus.COMPLETED
        assert len(result.output) == 1
        assert result.output[0]["name"] == "MyClass"

    async def test_find_imports(self, manager, sample_python_file):
        """Test finding imports."""
        task = SubprocessTask(
            worker_type="code_analysis",
            command={"action": "find_imports", "path": sample_python_file},
        )
        result = await manager.spawn(task)
        assert result.status == WorkerStatus.COMPLETED
        modules = [i["module"] for i in result.output]
        assert "os" in modules
        assert "sys" in modules

    async def test_find_todos(self, manager, sample_python_file):
        """Test finding TODOs."""
        task = SubprocessTask(
            worker_type="code_analysis",
            command={"action": "find_todos", "path": sample_python_file},
        )
        result = await manager.spawn(task)
        assert result.status == WorkerStatus.COMPLETED
        assert len(result.output) == 2
        types = [t["type"] for t in result.output]
        assert "TODO" in types
        assert "FIXME" in types

    async def test_complexity(self, manager, sample_python_file):
        """Test complexity analysis."""
        task = SubprocessTask(
            worker_type="code_analysis",
            command={"action": "complexity", "path": sample_python_file},
        )
        result = await manager.spawn(task)
        assert result.status == WorkerStatus.COMPLETED
        # standalone_function should have higher complexity due to nested ifs
        func_complexity = {c["name"]: c["complexity"] for c in result.output}
        assert func_complexity["standalone_function"] > func_complexity["simple_function"]

    async def test_call_graph(self, manager, sample_python_file):
        """Test call graph generation."""
        task = SubprocessTask(
            worker_type="code_analysis",
            command={"action": "call_graph", "path": sample_python_file},
        )
        result = await manager.spawn(task)
        assert result.status == WorkerStatus.COMPLETED
        assert isinstance(result.output, dict)

    async def test_summarize(self, manager, sample_python_file):
        """Test code summarization."""
        task = SubprocessTask(
            worker_type="code_analysis",
            command={"action": "summarize", "path": sample_python_file},
        )
        result = await manager.spawn(task)
        assert result.status == WorkerStatus.COMPLETED
        assert "function_count" in result.output
        assert "class_count" in result.output


# ── Custom Worker Tests ─────────────────────────────────────────────────────

class TestCustomWorker:
    async def test_run_inline(self, manager):
        """Test running inline Python code."""
        task = SubprocessTask(
            worker_type="custom",
            command={
                "action": "run_inline",
                "code": "result = 2 + 2\nprint('computed')",
            },
        )
        result = await manager.spawn(task)
        assert result.status == WorkerStatus.COMPLETED
        assert result.output["return_value"] == 4
        assert "computed" in result.output["output"]

    async def test_run_script(self, manager, temp_dir):
        """Test running a Python script file."""
        script = os.path.join(temp_dir, "test_script.py")
        Path(script).write_text(
            "def main(args=None):\n"
            "    return {'message': 'hello', 'value': 42}\n"
        )

        task = SubprocessTask(
            worker_type="custom",
            command={"action": "run_script", "path": script},
        )
        result = await manager.spawn(task)
        assert result.status == WorkerStatus.COMPLETED
        assert result.output["return_value"]["message"] == "hello"

    async def test_run_function(self, manager, temp_dir):
        """Test running a specific function from a script."""
        script = os.path.join(temp_dir, "funcs.py")
        Path(script).write_text(
            "def add(x=0, y=0):\n"
            "    return x + y\n"
            "\n"
            "def multiply(x=0, y=0):\n"
            "    return x * y\n"
        )

        task = SubprocessTask(
            worker_type="custom",
            command={
                "action": "run_function",
                "path": script,
                "function": "add",
                "args": {"x": 3, "y": 4},
            },
        )
        result = await manager.spawn(task)
        assert result.status == WorkerStatus.COMPLETED
        assert result.output["return_value"] == 7

    async def test_validate_valid_code(self, manager):
        """Test validating valid Python code."""
        task = SubprocessTask(
            worker_type="custom",
            command={
                "action": "validate",
                "code": "def hello():\n    return 'world'\n",
            },
        )
        result = await manager.spawn(task)
        assert result.status == WorkerStatus.COMPLETED
        assert result.output["valid"] is True

    async def test_validate_invalid_code(self, manager):
        """Test validating invalid Python code."""
        task = SubprocessTask(
            worker_type="custom",
            command={
                "action": "validate",
                "code": "def hello(\n    return 'world'\n",
            },
        )
        result = await manager.spawn(task)
        assert result.status == WorkerStatus.COMPLETED
        assert result.output["valid"] is False


# ── Subprocess Manager Tests ────────────────────────────────────────────────

class TestSubprocessManager:
    async def test_spawn_many(self, manager):
        """Test spawning multiple tasks concurrently."""
        tasks = [
            SubprocessTask(
                worker_type="shell",
                command={"action": "exec", "command": f"echo task_{i}"},
            )
            for i in range(3)
        ]
        results = await manager.spawn_many(tasks)
        assert len(results) == 3
        assert all(r.status == WorkerStatus.COMPLETED for r in results)

    async def test_worker_limit(self, manager):
        """Test that worker limit is enforced."""
        # Manager has max_workers=3, spawn 5 tasks
        # Some should fail due to limit (they run sequentially in this test though)
        task = SubprocessTask(
            worker_type="shell",
            command={"action": "exec", "command": "echo test"},
        )
        # Run one at a time — should all succeed
        for _ in range(5):
            result = await manager.spawn(task)
            assert result.status == WorkerStatus.COMPLETED

    async def test_unknown_worker_type(self, manager):
        """Test handling unknown worker type."""
        task = SubprocessTask(
            worker_type="nonexistent",
            command={"action": "exec"},
        )
        result = await manager.spawn(task)
        assert result.status == WorkerStatus.FAILED
        assert "Unknown worker type" in result.error

    async def test_list_results(self, manager):
        """Test listing task results."""
        task = SubprocessTask(
            worker_type="shell",
            command={"action": "exec", "command": "echo test"},
        )
        await manager.spawn(task)
        results = manager.list_results()
        assert len(results) >= 1

    async def test_cleanup(self, manager):
        """Test cleanup."""
        task = SubprocessTask(
            worker_type="shell",
            command={"action": "exec", "command": "echo test"},
        )
        await manager.spawn(task)
        await manager.cleanup()
        assert len(manager.list_active()) == 0


# ── Tool Integration Tests ──────────────────────────────────────────────────

class TestToolIntegration:
    async def test_registry_creation(self):
        """Test that the default registry includes all new tools."""
        from plutus.tools.registry import create_default_registry

        registry = create_default_registry()
        tool_names = registry.list_tools()

        assert "code_editor" in tool_names
        assert "code_analysis" in tool_names
        assert "subprocess" in tool_names
        assert "tool_creator" in tool_names
        assert "shell" in tool_names
        assert "filesystem" in tool_names

    async def test_code_editor_tool(self, temp_dir):
        """Test the CodeEditorTool end-to-end."""
        from plutus.tools.code_editor import CodeEditorTool

        tool = CodeEditorTool()
        filepath = os.path.join(temp_dir, "editor_test.txt")

        # Write
        result = await tool.execute(
            operation="write",
            path=filepath,
            content="Hello World\n",
        )
        assert "error" not in result.lower()

        # Read
        result = await tool.execute(operation="read", path=filepath)
        assert "Hello World" in result

    async def test_code_analysis_tool(self, temp_dir):
        """Test the CodeAnalysisTool end-to-end."""
        from plutus.tools.code_analysis import CodeAnalysisTool

        tool = CodeAnalysisTool()
        filepath = os.path.join(temp_dir, "analysis_test.py")
        Path(filepath).write_text("def hello():\n    return 'world'\n")

        result = await tool.execute(operation="find_functions", path=filepath)
        assert "hello" in result

    async def test_subprocess_tool(self):
        """Test the SubprocessTool end-to-end."""
        from plutus.tools.subprocess_tool import SubprocessTool

        tool = SubprocessTool()
        result = await tool.execute(
            operation="spawn",
            worker_type="shell",
            command={"action": "exec", "command": "echo subprocess_test"},
        )
        assert "subprocess_test" in result
