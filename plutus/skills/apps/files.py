"""File management skills — reliable workflows for file operations.

Strategy: All file operations use shell commands (Layer 1) which are
the most reliable. Cross-platform commands are used where possible.
"""

from __future__ import annotations
from typing import Any
from plutus.skills.engine import SkillDefinition, SkillStep


class CreateFile(SkillDefinition):
    name = "create_file"
    description = "Create a new file with optional content"
    app = "File System"
    triggers = ["create file", "new file", "make file", "write file", "create document"]
    category = "files"
    required_params = ["file_path"]
    optional_params = ["content"]

    def build_steps(self, params: dict[str, Any]) -> list[SkillStep]:
        file_path = params["file_path"]
        content = params.get("content", "")

        steps = []

        if content:
            # Use run_command to create file with content
            # Use echo for simple content, or a heredoc for multiline
            if "\n" in content:
                # Write via Python one-liner for reliability with multiline
                escaped = content.replace("\\", "\\\\").replace('"', '\\"')
                cmd = f'python3 -c "open(\'{file_path}\', \'w\').write(\'{escaped}\')"'
            else:
                cmd = f'echo "{content}" > "{file_path}"'
            steps.append(SkillStep(
                description=f"Create file: {file_path}",
                operation="run_command",
                params={"command": cmd},
                wait_after=0.5,
            ))
        else:
            steps.append(SkillStep(
                description=f"Create empty file: {file_path}",
                operation="run_command",
                params={"command": f'type nul > "{file_path}" 2>nul || touch "{file_path}"'},
                wait_after=0.5,
            ))

        steps.append(SkillStep(
            description=f"Open the file in the default editor",
            operation="open_file",
            params={"file_path": file_path},
            wait_after=1.0,
            optional=True,
        ))

        return steps


class OrganizeFolder(SkillDefinition):
    name = "organize_folder"
    description = "Organize files in a folder by type (images, documents, videos, etc.)"
    app = "File System"
    triggers = ["organize folder", "sort files", "clean up folder", "organize files",
                "tidy up", "sort folder"]
    category = "files"
    required_params = ["folder_path"]
    optional_params = []

    def build_steps(self, params: dict[str, Any]) -> list[SkillStep]:
        folder = params["folder_path"]

        # Use a Python script for reliable cross-platform file organization
        organize_script = f"""
import os, shutil
folder = r'{folder}'
categories = {{
    'Images': ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg', '.webp', '.ico'],
    'Documents': ['.pdf', '.doc', '.docx', '.txt', '.rtf', '.odt', '.xls', '.xlsx', '.ppt', '.pptx', '.csv'],
    'Videos': ['.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm'],
    'Audio': ['.mp3', '.wav', '.flac', '.aac', '.ogg', '.wma', '.m4a'],
    'Archives': ['.zip', '.rar', '.7z', '.tar', '.gz', '.bz2'],
    'Code': ['.py', '.js', '.ts', '.html', '.css', '.java', '.cpp', '.c', '.h', '.go', '.rs'],
    'Executables': ['.exe', '.msi', '.dmg', '.app', '.deb', '.rpm'],
}}
moved = 0
for f in os.listdir(folder):
    fp = os.path.join(folder, f)
    if os.path.isfile(fp):
        ext = os.path.splitext(f)[1].lower()
        for cat, exts in categories.items():
            if ext in exts:
                dest = os.path.join(folder, cat)
                os.makedirs(dest, exist_ok=True)
                shutil.move(fp, os.path.join(dest, f))
                moved += 1
                break
print(f'Organized {{moved}} files into categories')
"""

        return [
            SkillStep(
                description=f"Organize files in: {folder}",
                operation="run_command",
                params={"command": f'python3 -c "{organize_script.strip()}"'},
                wait_after=1.0,
            ),
            SkillStep(
                description=f"Open the organized folder",
                operation="open_folder",
                params={"file_path": folder},
                wait_after=1.0,
                optional=True,
            ),
        ]


class FindFiles(SkillDefinition):
    name = "find_files"
    description = "Search for files by name, extension, or content"
    app = "File System"
    triggers = ["find file", "search file", "locate file", "where is file",
                "find files"]
    category = "files"
    required_params = ["query"]
    optional_params = ["folder", "extension"]

    def build_steps(self, params: dict[str, Any]) -> list[SkillStep]:
        query = params["query"]
        folder = params.get("folder", ".")
        extension = params.get("extension", "")

        if extension:
            # Search by extension
            cmd = f'dir /s /b "{folder}\\*.{extension}" 2>nul || find "{folder}" -name "*.{extension}" -type f 2>/dev/null'
        else:
            # Search by name
            cmd = f'dir /s /b "{folder}\\*{query}*" 2>nul || find "{folder}" -iname "*{query}*" -type f 2>/dev/null'

        return [
            SkillStep(
                description=f"Search for files matching: {query}",
                operation="run_command",
                params={"command": cmd},
                wait_after=0.5,
            ),
        ]


class ZipFiles(SkillDefinition):
    name = "zip_files"
    description = "Compress files or a folder into a zip archive"
    app = "File System"
    triggers = ["zip files", "compress files", "create zip", "archive files",
                "zip folder", "compress folder"]
    category = "files"
    required_params = ["source", "output"]
    optional_params = []

    def build_steps(self, params: dict[str, Any]) -> list[SkillStep]:
        source = params["source"]
        output = params["output"]

        # Cross-platform zip command
        cmd = f'powershell Compress-Archive -Path "{source}" -DestinationPath "{output}" -Force 2>nul || zip -r "{output}" "{source}" 2>/dev/null'

        return [
            SkillStep(
                description=f"Compress {source} into {output}",
                operation="run_command",
                params={"command": cmd},
                wait_after=1.0,
            ),
        ]
