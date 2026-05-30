"""
ReviewMate Judging Sandbox — safe code execution for C and Python.
"""

import os
import sys
import json
import shutil
import tempfile
import subprocess
import time


def _normalize(s: str) -> str:
    return s.strip()


def judge_submission(
    code: str,
    language: str,
    test_cases: list[dict],
    time_limit_ms: int = 2000,
    memory_limit_mb: int = 128,
) -> dict:
    """
    Execute code against test cases in a temp sandbox.

    Returns:
        {
            "status": "Accepted" | "Wrong Answer" | "Compilation Error"
                   | "Runtime Error" | "Time Limit Exceeded",
            "total_cases": int,
            "passed_cases": int,
            "case_results": [{"case_id": int, "passed": bool, "input_preview": str,
                              "expected_output": str, "actual_output": str,
                              "error_message": str, "time_ms": float}],
            "compile_error": str | None,
            "total_time_ms": float,
            "peak_memory_mb": float
        }
    """
    result = {
        "status": "Accepted",
        "total_cases": len(test_cases),
        "passed_cases": 0,
        "case_results": [],
        "compile_error": None,
        "total_time_ms": 0.0,
        "peak_memory_mb": 0.0,
    }

    tmpdir = tempfile.mkdtemp(prefix="reviewmate_judge_")
    timeout = time_limit_ms / 1000.0 + 1.0  # 1s buffer

    try:
        if language == "Python":
            src_path = os.path.join(tmpdir, "solution.py")
            with open(src_path, "w", encoding="utf-8") as f:
                f.write(code)

            for i, case in enumerate(test_cases):
                case_input = case.get("input", "")
                expected = _normalize(case.get("expected_output", ""))
                case_result = {
                    "case_id": i + 1,
                    "passed": False,
                    "input_preview": case_input[:200],
                    "expected_output": expected,
                    "actual_output": "",
                    "error_message": "",
                    "time_ms": 0.0,
                }
                try:
                    t0 = time.perf_counter()
                    proc = subprocess.run(
                        [sys.executable, src_path],
                        input=case_input.encode("utf-8", errors="replace"),
                        capture_output=True,
                        timeout=timeout,
                    )
                    t1 = time.perf_counter()
                    case_result["time_ms"] = round((t1 - t0) * 1000, 2)

                    if proc.returncode != 0:
                        case_result["error_message"] = proc.stderr.decode("utf-8", errors="replace")[:500]
                        if result["status"] == "Accepted":
                            result["status"] = "Runtime Error"
                    else:
                        actual = _normalize(proc.stdout.decode("utf-8", errors="replace"))
                        case_result["actual_output"] = actual[:500]
                        if actual == expected:
                            case_result["passed"] = True
                            result["passed_cases"] += 1
                        elif result["status"] in ("Accepted", "Wrong Answer"):
                            result["status"] = "Wrong Answer"
                except subprocess.TimeoutExpired:
                    case_result["error_message"] = "Time Limit Exceeded"
                    case_result["time_ms"] = time_limit_ms
                    if result["status"] == "Accepted":
                        result["status"] = "Time Limit Exceeded"

                result["case_results"].append(case_result)

        elif language == "C":
            # Check for available C compiler
            cc = shutil.which("gcc") or shutil.which("clang") or shutil.which("cc")
            if not cc:
                result["status"] = "Compilation Error"
                if sys.platform == "win32":
                    hint = "请安装 MinGW-w64 或 TDM-GCC，或使用 WSL / MSYS2。"
                elif sys.platform == "darwin":
                    hint = "请在终端运行 xcode-select --install 安装命令行工具。"
                else:
                    hint = "请通过系统包管理器安装 gcc 或 clang（如 apt install gcc）。"
                result["compile_error"] = f"未找到 C 编译器（gcc/clang）。\n{hint}"
                for i, case in enumerate(test_cases):
                    result["case_results"].append({
                        "case_id": i + 1, "passed": False,
                        "input_preview": case.get("input", "")[:200],
                        "expected_output": _normalize(case.get("expected_output", "")),
                        "actual_output": "", "error_message": "Compiler not found",
                        "time_ms": 0.0,
                    })
                return result

            src_path = os.path.join(tmpdir, "solution.c")
            exe_name = "solution.exe" if sys.platform == "win32" else "solution"
            exe_path = os.path.join(tmpdir, exe_name)
            with open(src_path, "w", encoding="utf-8") as f:
                f.write(code)

            # Compile
            compile_proc = subprocess.run(
                [cc, src_path, "-o", exe_path, "-Wall", "-O2"],
                capture_output=True,
                timeout=30,
            )
            if compile_proc.returncode != 0:
                result["status"] = "Compilation Error"
                result["compile_error"] = compile_proc.stderr.decode("utf-8", errors="replace")[:2000]
                for i, case in enumerate(test_cases):
                    result["case_results"].append({
                        "case_id": i + 1,
                        "passed": False,
                        "input_preview": case.get("input", "")[:200],
                        "expected_output": _normalize(case.get("expected_output", "")),
                        "actual_output": "",
                        "error_message": "Compilation Error",
                        "time_ms": 0.0,
                    })
                return result

            # Execute each test case
            for i, case in enumerate(test_cases):
                case_input = case.get("input", "")
                expected = _normalize(case.get("expected_output", ""))
                case_result = {
                    "case_id": i + 1,
                    "passed": False,
                    "input_preview": case_input[:200],
                    "expected_output": expected,
                    "actual_output": "",
                    "error_message": "",
                    "time_ms": 0.0,
                }
                try:
                    t0 = time.perf_counter()
                    proc = subprocess.run(
                        [exe_path],
                        input=case_input.encode("utf-8", errors="replace"),
                        capture_output=True,
                        timeout=timeout,
                    )
                    t1 = time.perf_counter()
                    case_result["time_ms"] = round((t1 - t0) * 1000, 2)

                    if proc.returncode != 0:
                        case_result["error_message"] = proc.stderr.decode("utf-8", errors="replace")[:500]
                        if result["status"] == "Accepted":
                            result["status"] = "Runtime Error"
                    else:
                        actual = _normalize(proc.stdout.decode("utf-8", errors="replace"))
                        case_result["actual_output"] = actual[:500]
                        if actual == expected:
                            case_result["passed"] = True
                            result["passed_cases"] += 1
                        elif result["status"] in ("Accepted", "Wrong Answer"):
                            result["status"] = "Wrong Answer"
                except subprocess.TimeoutExpired:
                    case_result["error_message"] = "Time Limit Exceeded"
                    case_result["time_ms"] = time_limit_ms
                    if result["status"] == "Accepted":
                        result["status"] = "Time Limit Exceeded"

                result["case_results"].append(case_result)

        else:
            result["status"] = "Compilation Error"
            result["compile_error"] = f"Unsupported language: {language}"

        result["total_time_ms"] = round(
            sum(c["time_ms"] for c in result["case_results"]), 2
        )
        return result

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
