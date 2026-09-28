"""
Dependency Migration Agent Orchestrator.

Runs all framework stages sequentially.

Current execution mode:
- analysis only
- planning only
- no dependency modifications
- no Git branch creation
- no source-code changes
- no pull-request creation
"""

import json
import subprocess
import sys
from pathlib import Path


AGENT_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = AGENT_ROOT.parent
REPORTS_ROOT = AGENT_ROOT / "reports"
POLICY_FILE = AGENT_ROOT / "policy.json"


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


def load_policy():
    """Load and validate policy.json."""

    if not POLICY_FILE.exists():
        raise FileNotFoundError(
            "Agent policy file was not found: {}".format(
                POLICY_FILE
            )
        )

    if not POLICY_FILE.is_file():
        raise ValueError(
            "Agent policy path is not a file: {}".format(
                POLICY_FILE
            )
        )

    try:
        policy = json.loads(
            POLICY_FILE.read_text(encoding="utf-8")
        )
    except json.JSONDecodeError as error:
        raise ValueError(
            "Agent policy contains invalid JSON: {}".format(
                error
            )
        )

    required_fields = [
        "agentName",
        "version",
        "executionMode",
        "allowAutomaticChanges",
        "allowBranchCreation",
        "allowPullRequestCreation",
    ]

    missing_fields = [
        field_name
        for field_name in required_fields
        if field_name not in policy
    ]

    if missing_fields:
        raise ValueError(
            "Agent policy is missing fields: {}".format(
                ", ".join(missing_fields)
            )
        )

    return policy


def build_command(step):
    """Build the Python command for one agent stage."""

    script_path = AGENT_ROOT / step["script"]

    if not script_path.exists():
        raise FileNotFoundError(
            "Agent module was not found: {}".format(
                script_path
            )
        )

    command = [
        sys.executable,
        str(script_path),
    ]

    command.extend(step.get("arguments", []))

    return command


def execute_step(step_number, total_steps, step):
    """Execute one agent stage and return its result."""

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
        print("Reason: {}".format(error))

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
        print("Reason: {}".format(error))

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
    """Load a generated JSON report if available."""

    report_path = REPORTS_ROOT / report_name

    if not report_path.exists():
        return None

    try:
        return json.loads(
            report_path.read_text(encoding="utf-8")
        )
    except json.JSONDecodeError:
        return None


def print_startup(policy):
    """Print policy-driven agent startup information."""

    agent_name = policy.get(
        "agentName",
        "Dependency Migration Agent",
    )

    print("=" * 60)
    print(agent_name.upper())
    print("=" * 60)
    print(
        "Agent name          : {}".format(
            agent_name
        )
    )
    print(
        "Agent version       : {}".format(
            policy.get("version")
        )
    )
    print(
        "Execution mode      : {}".format(
            policy.get("executionMode")
        )
    )
    print(
        "Automatic changes   : {}".format(
            policy.get("allowAutomaticChanges")
        )
    )
    print(
        "Branch creation     : {}".format(
            policy.get("allowBranchCreation")
        )
    )
    print(
        "Pull request        : {}".format(
            policy.get("allowPullRequestCreation")
        )
    )
    print(
        "Research sources    : {}".format(
            policy.get("minimumResearchSources")
        )
    )
    print(
        "Confidence threshold: {}".format(
            policy.get("minimumConfidenceScore")
        )
    )
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


def print_final_summary(step_results, policy):
    """Print the final agent execution summary."""

    migration_plan = load_json_report(
        "migration-plan.json"
    )
    remediation_report = load_json_report(
        "remediation-report.json"
    )
    branch_report = load_json_report(
        "branch-report.json"
    )
    final_report = load_json_report(
        "final-agent-report.json"
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
        "Agent version       : {}".format(
            policy.get("version")
        )
    )
    print(
        "Execution mode      : {}".format(
            policy.get("executionMode")
        )
    )
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
                migration_plan.get("planStatus")
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
                remediation_report.get("status")
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
                branch_report.get("branchName")
            )
        )

    if final_report:
        print(
            "Final agent status  : {}".format(
                final_report.get("agentStatus")
            )
        )
        print(
            "Final next step     : {}".format(
                final_report.get("nextStep")
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
    """Validate files required before execution."""

    required_files = [
        PROJECT_ROOT / "pom.xml",
        POLICY_FILE,
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

    try:
        policy = load_policy()
    except (FileNotFoundError, ValueError) as error:
        print("=" * 60)
        print("DEPENDENCY MIGRATION AGENT")
        print("=" * 60)
        print(
            "Unable to load policy: {}".format(
                error
            )
        )
        return 2

    print_startup(policy)

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

            print_final_summary(
                step_results,
                policy,
            )

            return result["exitCode"] or 1

    print()
    print("=" * 60)
    print("AGENT EXECUTION COMPLETE")
    print("=" * 60)

    print_final_summary(
        step_results,
        policy,
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
