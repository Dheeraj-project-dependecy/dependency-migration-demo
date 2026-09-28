"""
Dependency Migration Agent Orchestrator.

Runs the analysis and framework modules sequentially.

Current phase:
- Analysis only
- Planning only
- No dependency modifications
- No Git branch creation
- No source-code modifications
- No pull-request creation
"""

import json
import subprocess
import sys
from pathlib import Path


AGENT_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = AGENT_ROOT.parent
REPORTS_ROOT = AGENT_ROOT / "reports"


STEPS = [
    {
        "name": "Build Analysis",
        "script": "build_analyzer.py",
        "arguments": [
            "--build-log",
            str(REPORTS_ROOT / "maven-build.log"),
        ],
    },
    {
        "name": "POM Scanner",
        "script": "pom_scanner.py",
        "arguments": [
            "--pom",
            str(PROJECT_ROOT / "pom.xml"),
        ],
    },
    {
        "name": "Dependency Scanner",
        "script": "dependency_scanner.py",
        "arguments": [
            "--project-root",
            str(PROJECT_ROOT),
        ],
    },
    {
        "name": "Dependency Research",
        "script": "dependency_researcher.py",
        "arguments": [],
    },
    {
        "name": "Compatibility Analyzer",
        "script": "compatibility_analyzer.py",
        "arguments": [],
    },
    {
        "name": "Migration Planner",
        "script": "migration_planner.py",
        "arguments": [],
    },
    {
        "name": "Remediation Engine",
        "script": "remediation_engine.py",
        "arguments": [],
    },
    {
        "name": "Branch Manager",
        "script": "branch_manager.py",
        "arguments": [],
    },
    {
        "name": "Report Generator",
        "script": "report_generator.py",
        "arguments": [],
    },
    {
        "name": "Notifier",
        "script": "notifier.py",
        "arguments": [],
    },
]


def build_command(step):
    """Build the Python command for one agent step."""

    script_path = AGENT_ROOT / step["script"]

    if not script_path.exists():
        raise FileNotFoundError(
            "Agent module was not found: {}".format(script_path)
        )

    command = [
        sys.executable,
        str(script_path),
    ]

    command.extend(step.get("arguments", []))

    return command


def execute_step(step_number, total_steps, step):
    """Execute one agent module and return its result."""

    print()
    print("-" * 60)
    print(
        "[{}/{}] {}".format(
            step_number,
            total_steps,
            step["name"],
        )
    )
    print("-" * 60)

    try:
        command = build_command(step)

        result = subprocess.run(
            command,
            cwd=str(PROJECT_ROOT),
            stdout=None,
            stderr=None,
            shell=False,
        )

    except FileNotFoundError as error:
        print(
            "FAILED: {}".format(
                step["name"]
            )
        )
        print(
            "Reason: {}".format(error)
        )

        return {
            "name": step["name"],
            "status": "FAILED",
            "exitCode": 2,
            "error": str(error),
        }

    except Exception as error:
        print(
            "FAILED: {}".format(
                step["name"]
            )
        )
        print(
            "Reason: {}".format(error)
        )

        return {
            "name": step["name"],
            "status": "FAILED",
            "exitCode": 3,
            "error": str(error),
        }

    if result.returncode != 0:
        print()
        print(
            "FAILED: {}".format(
                step["name"]
            )
        )
        print(
            "Exit code: {}".format(
                result.returncode
            )
        )

        return {
            "name": step["name"],
            "status": "FAILED",
            "exitCode": result.returncode,
            "error": None,
        }

    print()
    print(
        "SUCCESS: {}".format(
            step["name"]
        )
    )

    return {
        "name": step["name"],
        "status": "SUCCESS",
        "exitCode": 0,
        "error": None,
    }


def load_json_report(report_name):
    """Load a report if it exists and contains valid JSON."""

    report_path = REPORTS_ROOT / report_name

    if not report_path.exists():
        return None

    try:
        return json.loads(
            report_path.read_text(
                encoding="utf-8"
            )
        )

    except json.JSONDecodeError:
        return None


def print_final_summary(step_results):
    """Print the final agent-execution summary."""

    migration_plan = load_json_report(
        "migration-plan.json"
    )

    remediation_report = load_json_report(
        "remediation-report.json"
    )

    branch_report = load_json_report(
        "branch-report.json"
    )

    successful_steps = [
        step
        for step in step_results
        if step["status"] == "SUCCESS"
    ]

    failed_steps = [
        step
        for step in step_results
        if step["status"] == "FAILED"
    ]

    print()
    print("=" * 60)
    print("AGENT EXECUTION SUMMARY")
    print("=" * 60)

    print(
        "Successful steps    : {}".format(
            len(successful_steps)
        )
    )

    print(
        "Failed steps        : {}".format(
            len(failed_steps)
        )
    )

    if migration_plan:
        print(
            "Plan status         : {}".format(
                migration_plan.get(
                    "planStatus"
                )
            )
        )

        print(
            "Automatic changes   : {}".format(
                migration_plan.get(
                    "automaticChangesAllowed",
                    False,
                )
            )
        )

        print(
            "Branch creation     : {}".format(
                migration_plan.get(
                    "branchCreationAllowed",
                    False,
                )
            )
        )

        print(
            "Migration candidates: {}".format(
                migration_plan.get(
                    "research",
                    {},
                ).get(
                    "candidateCount",
                    0,
                )
            )
        )

    if remediation_report:
        print(
            "Remediation status  : {}".format(
                remediation_report.get(
                    "status"
                )
            )
        )

    if branch_report:
        print(
            "Branch required     : {}".format(
                branch_report.get(
                    "branchRequired",
                    False,
                )
            )
        )

        print(
            "Branch name         : {}".format(
                branch_report.get(
                    "branchName"
                )
            )
        )

    print(
        "Reports directory    : {}".format(
            REPORTS_ROOT
        )
    )

    if failed_steps:
        print()
        print("Failed modules:")

        for failed_step in failed_steps:
            print(
                "  - {} (exit code {})".format(
                    failed_step["name"],
                    failed_step["exitCode"],
                )
            )


def validate_environment():
    """Validate the files required before agent execution."""

    required_files = [
        PROJECT_ROOT / "pom.xml",
        REPORTS_ROOT / "maven-build.log",
    ]

    missing_files = [
        str(file_path)
        for file_path in required_files
        if not file_path.exists()
    ]

    if missing_files:
        print("Missing required files:")

        for missing_file in missing_files:
            print(
                "  - {}".format(
                    missing_file
                )
            )

        return False

    return True


def main():
    """Run the complete agent framework sequentially."""

    print("=" * 60)
    print("DEPENDENCY MIGRATION AGENT")
    print("=" * 60)

    print(
        "Project root        : {}".format(
            PROJECT_ROOT
        )
    )

    print(
        "Agent root          : {}".format(
            AGENT_ROOT
        )
    )

    print(
        "Execution mode      : ANALYSIS_ONLY"
    )

    REPORTS_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    if not validate_environment():
        print()
        print(
            "Agent execution stopped because required "
            "input files are missing."
        )

        return 2

    total_steps = len(STEPS)
    step_results = []

    for index, step in enumerate(
        STEPS,
        start=1,
    ):
        result = execute_step(
            index,
            total_steps,
            step,
        )

        step_results.append(result)

        if result["status"] == "FAILED":
            print()
            print("=" * 60)
            print("AGENT PIPELINE STOPPED")
            print("=" * 60)
            print(
                "Failed stage       : {}".format(
                    result["name"]
                )
            )

            print_final_summary(step_results)

            return result["exitCode"] or 1

    print()
    print("=" * 60)
    print("AGENT EXECUTION COMPLETE")
    print("=" * 60)

    print_final_summary(step_results)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())