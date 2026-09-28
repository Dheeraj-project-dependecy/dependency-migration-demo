"""
Dependency Migration Agent console notifier.

Reads:
- migration-agent/reports/final-agent-report.json

Current phase:
- Prints an execution summary to the console.
- Does not send email, Teams, or GitHub notifications.
"""

import json
from pathlib import Path


AGENT_ROOT = Path(__file__).resolve().parent
REPORT_FILE = AGENT_ROOT / "reports" / "final-agent-report.json"


def load_final_report():
    """Load and validate the final agent report."""

    if not REPORT_FILE.exists():
        raise FileNotFoundError(
            "Final agent report was not found: {}".format(
                REPORT_FILE
            )
        )

    if not REPORT_FILE.is_file():
        raise ValueError(
            "Final agent report path is not a file: {}".format(
                REPORT_FILE
            )
        )

    try:
        return json.loads(
            REPORT_FILE.read_text(
                encoding="utf-8"
            )
        )

    except json.JSONDecodeError as error:
        raise ValueError(
            "Final agent report contains invalid JSON: {}".format(
                error
            )
        )


def determine_notification_message(report):
    """Determine a readable notification message."""

    build_status = report.get(
        "buildStatus",
        "UNKNOWN",
    )

    plan_status = report.get(
        "planStatus",
        "UNKNOWN",
    )

    automatic_changes = report.get(
        "automaticChangesAllowed",
        False,
    )

    if build_status == "SUCCESS":
        return (
            "The daily Maven build is healthy. "
            "No dependency remediation is required."
        )

    if automatic_changes:
        return (
            "A dependency-related build failure was confirmed. "
            "Automatic remediation is permitted by policy."
        )

    if plan_status == "DRAFT_RESEARCH_REQUIRED":
        return (
            "A possible dependency-related failure was detected. "
            "Additional research is required before remediation."
        )

    if plan_status == "NO_ACTION_NON_DEPENDENCY_FAILURE":
        return (
            "The build failure is not dependency-related. "
            "The agent will not modify dependencies."
        )

    return (
        "The agent completed analysis, but no automatic "
        "remediation action is currently permitted."
    )


def print_notification(report):
    """Print the final agent notification."""

    notification_message = determine_notification_message(
        report
    )

    print("=" * 60)
    print("DEPENDENCY MIGRATION AGENT NOTIFICATION")
    print("=" * 60)

    print(
        "Agent status        : {}".format(
            report.get(
                "agentStatus",
                "UNKNOWN",
            )
        )
    )

    print(
        "Generated at        : {}".format(
            report.get(
                "generatedAt",
                "UNKNOWN",
            )
        )
    )

    print(
        "Project             : {}".format(
            report.get(
                "project",
                "UNKNOWN",
            )
        )
    )

    print(
        "Build status        : {}".format(
            report.get(
                "buildStatus",
                "UNKNOWN",
            )
        )
    )

    print(
        "Plan status         : {}".format(
            report.get(
                "planStatus",
                "UNKNOWN",
            )
        )
    )

    print(
        "Java version        : {}".format(
            report.get(
                "javaVersion",
                "UNKNOWN",
            )
        )
    )

    print(
        "Spring Boot version : {}".format(
            report.get(
                "springBootVersion",
                "UNKNOWN",
            )
        )
    )

    print(
        "Dependencies        : {}".format(
            report.get(
                "dependencyCount",
                0,
            )
        )
    )

    print(
        "Migration candidates: {}".format(
            report.get(
                "migrationCandidateCount",
                0,
            )
        )
    )

    print(
        "Automatic changes   : {}".format(
            report.get(
                "automaticChangesAllowed",
                False,
            )
        )
    )

    print(
        "Branch creation     : {}".format(
            report.get(
                "branchCreationAllowed",
                False,
            )
        )
    )

    print(
        "Next step           : {}".format(
            report.get(
                "nextStep",
                "No next step was provided.",
            )
        )
    )

    print("-" * 60)

    print(
        "Notification        : {}".format(
            notification_message
        )
    )

    print("=" * 60)


def main():
    """Command-line entry point."""

    try:
        report = load_final_report()
        print_notification(report)
        return 0

    except (FileNotFoundError, ValueError) as error:
        print(
            "NOTIFIER ERROR: {}".format(
                error
            )
        )
        return 2

    except Exception as error:
        print(
            "Unexpected notifier error: {}".format(
                error
            )
        )
        return 3


if __name__ == "__main__":
    raise SystemExit(main())