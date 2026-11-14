"""Portable host C compiler support for independent audit scripts."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess


def _msvc_environment_script() -> Path | None:
    roots = (
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")),
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")),
    )
    candidates = []
    for root in roots:
        candidates.extend(root.glob("Microsoft Visual Studio/*/*/Common7/Tools/VsDevCmd.bat"))
    return sorted(candidates, reverse=True)[0] if candidates else None


def compile_c_binary(
    *,
    root: Path,
    directory: str | Path,
    test_name: str,
    sources: tuple[str, ...],
    include_dirs: tuple[Path, ...],
) -> tuple[Path, subprocess.CompletedProcess[str]]:
    directory = Path(directory)
    binary = directory / (test_name + (".exe" if os.name == "nt" else ""))
    source_paths = [str(root / source) for source in sources]
    compiler = os.environ.get("CC") or shutil.which("cc") or shutil.which("gcc")
    if os.name == "nt" and not compiler:
        vsdevcmd = _msvc_environment_script()
        if vsdevcmd is None:
            raise AssertionError("host C compiler is unavailable")
        command = [
            "cl", "/nologo", "/std:c11", "/W4", "/WX", "/O2",
            "/UNDEBUG", "/D_CRT_SECURE_NO_WARNINGS", "/wd4310",
            *(f"/I{path}" for path in include_dirs),
            *source_paths,
            f"/Fe:{binary}",
        ]
        compile_script = directory / f"compile_{test_name}.cmd"
        compile_script.write_text(
            "@echo off\r\n"
            f'call "{vsdevcmd}" -arch=x64 >nul\r\n'
            "if errorlevel 1 exit /b %errorlevel%\r\n"
            f"{subprocess.list2cmdline(command)}\r\n",
            encoding="utf-8",
        )
        compile_command = ["cmd.exe", "/d", "/c", str(compile_script)]
    else:
        if compiler is None:
            raise AssertionError("host C compiler is unavailable")
        compile_command = [
            compiler,
            "-std=gnu11", "-Wall", "-Wextra", "-Wpedantic", "-Werror",
            "-O2", "-UNDEBUG",
            *(f"-I{path}" for path in include_dirs),
            *source_paths,
        ]
        if os.name != "nt":
            compile_command.append("-lm")
        compile_command.extend(("-o", str(binary)))
    result = subprocess.run(
        compile_command,
        check=False,
        capture_output=True,
        text=True,
        cwd=directory,
    )
    return binary, result
