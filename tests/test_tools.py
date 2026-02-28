"""Tests for the tool system."""

import os
import tempfile
from pathlib import Path

import pytest

from plutus.tools.base import Tool  # noqa: F401
from plutus.tools.filesystem import FilesystemTool
from plutus.tools.registry import ToolRegistry
from plutus.tools.shell import BLOCKED_COMMANDS, ShellTool  # noqa: F401
from plutus.tools.system_info import SystemInfoTool
from plutus.tools.wsl import BLOCKED_PATTERNS as WSL_BLOCKED_PATTERNS
from plutus.tools.wsl import WSLTool

# ── Tool Registry tests ─────────────────────────────────────


class TestToolRegistry:
    def test_register_and_get(self):
        registry = ToolRegistry()
        tool = ShellTool()
        registry.register(tool)

        assert registry.get("shell") is tool
        assert registry.get("nonexistent") is None

    def test_list_tools(self):
        registry = ToolRegistry()
        registry.register(ShellTool())
        registry.register(FilesystemTool())

        tools = registry.list_tools()
        assert "shell" in tools
        assert "filesystem" in tools

    def test_get_definitions(self):
        registry = ToolRegistry()
        registry.register(ShellTool())
        registry.register(SystemInfoTool())

        defs = registry.get_definitions()
        assert len(defs) == 2
        names = {d.name for d in defs}
        assert names == {"shell", "system_info"}

    def test_get_tool_info(self):
        registry = ToolRegistry()
        registry.register(ShellTool())

        info = registry.get_tool_info()
        assert len(info) == 1
        assert info[0]["name"] == "shell"
        assert "description" in info[0]
        assert "parameters" in info[0]


# ── Shell Tool tests ────────────────────────────────────────


class TestShellTool:
    @pytest.fixture
    def tool(self):
        return ShellTool()

    def test_properties(self, tool):
        assert tool.name == "shell"
        assert len(tool.description) > 0
        assert tool.parameters["type"] == "object"
        assert "command" in tool.parameters["properties"]

    @pytest.mark.asyncio
    async def test_execute_simple_command(self, tool):
        result = await tool.execute(command="echo hello")
        assert "hello" in result
        assert "exit_code: 0" in result

    @pytest.mark.asyncio
    async def test_execute_with_working_directory(self, tool):
        result = await tool.execute(command="pwd", working_directory="/tmp")
        assert "/tmp" in result

    @pytest.mark.asyncio
    async def test_blocks_dangerous_commands(self, tool):
        result = await tool.execute(command="rm -rf /")
        assert "[BLOCKED]" in result

    @pytest.mark.asyncio
    async def test_captures_stderr(self, tool):
        result = await tool.execute(command="ls /nonexistent_path_12345")
        assert "stderr:" in result or "exit_code:" in result

    @pytest.mark.asyncio
    async def test_timeout(self, tool):
        result = await tool.execute(command="sleep 5", timeout=1)
        assert "[TIMEOUT]" in result

    def test_get_definition(self, tool):
        defn = tool.get_definition()
        assert defn.name == "shell"
        assert "command" in defn.parameters["properties"]


# ── Filesystem Tool tests ───────────────────────────────────


class TestFilesystemTool:
    @pytest.fixture
    def tool(self):
        return FilesystemTool()

    @pytest.mark.asyncio
    async def test_read_file(self, tool):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("test content")
            path = f.name

        result = await tool.execute(operation="read", path=path)
        assert "test content" in result
        os.unlink(path)

    @pytest.mark.asyncio
    async def test_write_file(self, tool):
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            path = f.name

        result = await tool.execute(
            operation="write", path=path, content="new content"
        )
        assert "written" in result.lower()
        assert Path(path).read_text() == "new content"
        os.unlink(path)

    @pytest.mark.asyncio
    async def test_list_directory(self, tool):
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "a.txt").write_text("a")
            Path(tmpdir, "b.txt").write_text("b")

            result = await tool.execute(operation="list", path=tmpdir)
            assert "a.txt" in result
            assert "b.txt" in result

    @pytest.mark.asyncio
    async def test_mkdir(self, tool):
        with tempfile.TemporaryDirectory() as tmpdir:
            new_dir = os.path.join(tmpdir, "subdir", "nested")
            result = await tool.execute(operation="mkdir", path=new_dir)
            assert "Created" in result
            assert Path(new_dir).is_dir()

    @pytest.mark.asyncio
    async def test_info(self, tool):
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"test")
            path = f.name

        result = await tool.execute(operation="info", path=path)
        assert "file" in result
        assert "size:" in result
        os.unlink(path)

    @pytest.mark.asyncio
    async def test_read_nonexistent(self, tool):
        result = await tool.execute(operation="read", path="/nonexistent_12345.txt")
        assert "[ERROR]" in result

    @pytest.mark.asyncio
    async def test_search(self, tool):
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "test.py").write_text("def hello_world():\n    pass\n")
            Path(tmpdir, "other.txt").write_text("nothing here\n")

            result = await tool.execute(
                operation="search", path=tmpdir, pattern="hello_world"
            )
            assert "hello_world" in result
            assert "test.py" in result


# ── SystemInfo Tool tests ───────────────────────────────────


class TestSystemInfoTool:
    @pytest.fixture
    def tool(self):
        return SystemInfoTool()

    @pytest.mark.asyncio
    async def test_overview(self, tool):
        result = await tool.execute(operation="overview")
        assert "CPU:" in result
        assert "Memory:" in result

    @pytest.mark.asyncio
    async def test_os_info(self, tool):
        result = await tool.execute(operation="os")
        assert "System:" in result
        assert "Python:" in result


# ── WSL Tool tests ─────────────────────────────────────────


class TestWSLTool:
    @pytest.fixture
    def tool(self):
        return WSLTool()

    def test_properties(self, tool):
        assert tool.name == "wsl"
        assert len(tool.description) > 0
        assert tool.parameters["type"] == "object"
        assert "operation" in tool.parameters["properties"]
        assert "command" in tool.parameters["properties"]

    def test_get_definition(self, tool):
        defn = tool.get_definition()
        assert defn.name == "wsl"
        assert "operation" in defn.parameters["properties"]

    @pytest.mark.asyncio
    async def test_run_simple_command(self, tool):
        """On Linux (CI), the WSL tool falls back to native shell."""
        result = await tool.execute(operation="run", command="echo wsl_test")
        assert "wsl_test" in result
        assert "exit_code: 0" in result

    @pytest.mark.asyncio
    async def test_run_requires_command(self, tool):
        result = await tool.execute(operation="run")
        assert "[ERROR]" in result

    @pytest.mark.asyncio
    async def test_blocks_dangerous_commands(self, tool):
        result = await tool.execute(operation="run", command="rm -rf /")
        assert "[BLOCKED]" in result

    @pytest.mark.asyncio
    async def test_blocks_fork_bomb(self, tool):
        result = await tool.execute(operation="run", command=":(){ :|:& };:")
        assert "[BLOCKED]" in result

    @pytest.mark.asyncio
    async def test_timeout(self, tool):
        result = await tool.execute(operation="run", command="sleep 5", timeout=1)
        assert "[TIMEOUT]" in result

    @pytest.mark.asyncio
    async def test_unknown_operation(self, tool):
        result = await tool.execute(operation="bogus")
        assert "[ERROR]" in result

    @pytest.mark.asyncio
    async def test_info(self, tool):
        result = await tool.execute(operation="info")
        assert "host_os:" in result

    @pytest.mark.asyncio
    async def test_list_distros_non_windows(self, tool):
        """On Linux/macOS, list_distros returns a helpful non-applicable message."""
        import platform
        if platform.system() == "Windows":
            pytest.skip("Test only for non-Windows")
        result = await tool.execute(operation="list_distros")
        assert "native" in result.lower() or "not applicable" in result.lower()

    @pytest.mark.asyncio
    async def test_path_to_linux_non_windows(self, tool):
        import platform
        if platform.system() == "Windows":
            pytest.skip("Test only for non-Windows")
        result = await tool.execute(operation="path_to_linux", path="/tmp/test.txt")
        assert "/tmp/test.txt" in result

    @pytest.mark.asyncio
    async def test_path_requires_path(self, tool):
        result = await tool.execute(operation="path_to_linux")
        assert "[ERROR]" in result

    @pytest.mark.asyncio
    async def test_set_default_non_windows(self, tool):
        import platform
        if platform.system() == "Windows":
            pytest.skip("Test only for non-Windows")
        result = await tool.execute(operation="set_default", distro="Ubuntu")
        assert "[ERROR]" in result

    @pytest.mark.asyncio
    async def test_working_directory(self, tool):
        result = await tool.execute(
            operation="run", command="pwd", working_directory="/tmp"
        )
        assert "/tmp" in result

    def test_blocked_patterns_exist(self):
        assert len(WSL_BLOCKED_PATTERNS) > 0
        assert "rm -rf /" in WSL_BLOCKED_PATTERNS
