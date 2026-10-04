"""
Orchestrate the Self-Healing Legacy Dependency Migration Agent pipeline.

The orchestrator:
- loads and validates policy.json
- runs every agent stage in sequence
- stops immediately when a required stage fails
- prints a consolidated final summary

Current safety mode is controlled by policy.json.
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
    "name": "Source Remediator",
    "script": "source_remediator.py",
    "arguments": ["--dry-run"],
    },
    {
    "name": "Validation Engine",
    "script": "validation_engine.py",
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
            "Agent policy file was not found: {}".format(POLICY_FILE)
        )

    if not POLICY_FILE.is_file():
        raise ValueError(
            "Agent policy path is not a file: {}".format(POLICY_FILE)
        )

    try:
        policy = json.loads(POLICY_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(
            "Agent policy contains invalid JSON: {}".format(error)
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


def load_json_report(report_name):
    """Load a generated JSON report when it exists and is valid."""

    report_path = REPORTS_ROOT / report_name

    if not report_path.exists() or not report_path.is_file():
        return None

    try:
        return json.loads(report_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def build_command(step):
    """Build the Python command for one agent stage."""

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
    """Execute one agent stage and return structured status metadata."""

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
        print("FAILED: {}".format(step["name"]))
        print("Reason: {}".format(error))
        return {
            "name": step["name"],
            "status": "FAILED",
            "exitCode": 2,
            "error": str(error),
        }
    except Exception as error:
        print("FAILED: {}".format(step["name"]))
        print("Reason: {}".format(error))
        return {
            "name": step["name"],
            "status": "FAILED",
            "exitCode": 3,
            "error": str(error),
        }

    if result.returncode != 0:
        print()
        print("FAILED: {}".format(step["name"]))
        print("Exit code: {}".format(result.returncode))
        return {
            "name": step["name"],
            "status": "FAILED",
            "exitCode": result.returncode,
            "error": None,
        }

    print()
    print("SUCCESS: {}".format(step["name"]))

    return {
        "name": step["name"],
        "status": "SUCCESS",
        "exitCode": 0,
        "error": None,
    }


def print_startup(policy):
    """Print policy-driven startup information."""

    agent_name = policy.get(
        "agentName",
        "Dependency Migration Agent",
    )

    print("=" * 60)
    print(agent_name.upper())
    print("=" * 60)
    print("Agent name          : {}".format(agent_name))
    print("Agent version       : {}".format(policy.get("version")))
    print("Execution mode      : {}".format(policy.get("executionMode")))
    print(
        "Automatic changes   : {}".format(
            policy.get("allowAutomaticChanges", False)
        )
    )
    print(
        "Branch creation     : {}".format(
            policy.get("allowBranchCreation", False)
        )
    )
    print(
        "Pull request        : {}".format(
            policy.get("allowPullRequestCreation", False)
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
    print("Project root        : {}".format(PROJECT_ROOT))
    print("Agent root          : {}".format(AGENT_ROOT))


def print_final_summary(step_results, policy):
    """Print the final agent execution summary."""

    migration_plan = load_json_report("migration-plan.json") or {}
    remediation_report = load_json_report("remediation-report.json") or {}
    validation_report = load_json_report("validation-report.json") or {}
    branch_report = load_json_report("branch-report.json") or {}
    final_report = load_json_report("final-agent-report.json") or {}

    successful_steps = [
        step
        for step in step_results
        if step.get("status") == "SUCCESS"
    ]
    failed_steps = [
        step
        for step in step_results
        if step.get("status") == "FAILED"
    ]

    migration_research = migration_plan.get("research", {})
    final_summary = final_report.get("summary", {})
    final_validation = final_report.get("validation", {})

    migration_candidate_count = migration_research.get(
        "migrationCandidateCount",
        final_summary.get("migrationCandidateCount", 0),
    )
    final_next_step = final_summary.get(
        "nextStep",
        migration_plan.get("nextStep", "No next step was provided."),
    )

    print()
    print("=" * 60)
    print("AGENT EXECUTION SUMMARY")
    print("=" * 60)
    print("Agent version       : {}".format(policy.get("version")))
    print("Execution mode      : {}".format(policy.get("executionMode")))
    print("Successful steps    : {}".format(len(successful_steps)))
    print("Failed steps        : {}".format(len(failed_steps)))
    print(
        "Plan status         : {}".format(
            migration_plan.get("planStatus", "UNKNOWN")
        )
    )
    print(
        "Automatic changes   : {}".format(
            migration_plan.get("automaticChangesAllowed", False)
        )
    )
    print(
        "Branch creation     : {}".format(
            migration_plan.get("branchCreationAllowed", False)
        )
    )
    print(
        "Migration candidates: {}".format(
            migration_candidate_count
        )
    )
    print(
        "Remediation status  : {}".format(
            remediation_report.get("status", "UNKNOWN")
        )
    )
    print(
        "Validation status   : {}".format(
            validation_report.get(
                "validationStatus",
                final_validation.get("status", "NOT_EXECUTED"),
            )
        )
    )
    print(
        "Tests run           : {}".format(
            validation_report.get("tests", {}).get(
                "tests",
                final_validation.get("testsRun", 0),
            )
        )
    )
    print(
        "Coverage generated  : {}".format(
            validation_report.get("coverage", {}).get(
                "reportFound",
                final_validation.get("coverageGenerated", False),
            )
        )
    )
    print(
        "Branch required     : {}".format(
            branch_report.get("branchRequired", False)
        )
    )
    print(
        "Branch name         : {}".format(
            branch_report.get("branchName")
        )
    )
    print(
        "Final agent status  : {}".format(
            final_report.get("agentStatus", "UNKNOWN")
        )
    )
    print("Final next step     : {}".format(final_next_step))
    print("Reports directory    : {}".format(REPORTS_ROOT))

    if failed_steps:
        print()
        print("Failed modules:")

        for failed_step in failed_steps:
            print(
                "  - {} (exit code {})".format(
                    failed_step.get("name"),
                    failed_step.get("exitCode"),
                )
            )


def validate_environment():
    """Validate files required before agent execution."""

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
            print("  - {}".format(missing_file))

        return False

    missing_modules = [
        str(AGENT_ROOT / step["script"])
        for step in STEPS
        if not (AGENT_ROOT / step["script"]).exists()
    ]

    if missing_modules:
        print("Missing agent modules:")

        for missing_module in missing_modules:
            print("  - {}".format(missing_module))

        return False

    return True


def main():
    """Run the complete agent pipeline sequentially."""

    try:
        policy = load_policy()
    except (FileNotFoundError, ValueError) as error:
        print("=" * 60)
        print("DEPENDENCY MIGRATION AGENT")
        print("=" * 60)
        print("Unable to load policy: {}".format(error))
        return 2

    REPORTS_ROOT.mkdir(parents=True, exist_ok=True)
    print_startup(policy)

    if not validate_environment():
        print()
        print(
            "Agent execution stopped because required inputs are missing."
        )
        return 2

    step_results = []
    total_steps = len(STEPS)

    for index, step in enumerate(STEPS, start=1):
        result = execute_step(index, total_steps, step)
        step_results.append(result)

        if result.get("status") == "FAILED":
            print()
            print("=" * 60)
            print("AGENT PIPELINE STOPPED")
            print("=" * 60)
            print("Failed stage       : {}".format(result.get("name")))
            print_final_summary(step_results, policy)
            return result.get("exitCode") or 1

    print()
    print("=" * 60)
    print("AGENT EXECUTION COMPLETE")
    print("=" * 60)
    print_final_summary(step_results, policy)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
