"""
Print a console notification from final-agent-report.json.

Current phase:
- Reads the consolidated final report.
- Prints build, migration, remediation, and validation results.
- Does not send email, Teams, GitHub, or pull-request notifications.
"""

import json
from pathlib import Path


AGENT_ROOT = Path(__file__).resolve().parent
REPORT_FILE = AGENT_ROOT / "reports" / "final-agent-report.json"


def load_final_report():
    """Load and validate final-agent-report.json."""

    if not REPORT_FILE.exists():
        raise FileNotFoundError(
            "Final agent report was not found: {}".format(REPORT_FILE)
        )

    if not REPORT_FILE.is_file():
        raise ValueError(
            "Final agent report path is not a file: {}".format(
                REPORT_FILE
            )
        )

    try:
        return json.loads(REPORT_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(
            "Final agent report contains invalid JSON: {}".format(error)
        )


def determine_notification_message(report):
    """Create a concise notification message from the final report."""

    build = report.get("build", {})
    migration = report.get("migration", {})
    validation = report.get("validation", {})

    build_status = build.get("status", "UNKNOWN")
    plan_status = migration.get("planStatus", "UNKNOWN")
    validation_status = validation.get("status", "NOT_EXECUTED")
    automatic_changes = migration.get(
        "automaticChangesAllowed",
        False,
    )

    if build_status == "SUCCESS":
        return (
            "The Maven build is healthy. Analysis and baseline validation "
            "completed successfully, so no remediation is required."
        )

    if validation_status not in ["SUCCESS", "NOT_EXECUTED"]:
        return (
            "Validation failed. Inspect the validation logs and do not "
            "commit or push changes."
        )

    if automatic_changes:
        return (
            "A dependency-related failure was confirmed and policy permits "
            "automatic remediation."
        )

    if plan_status == "READY_FOR_REMEDIATION":
        return (
            "A compatible migration plan is ready, but policy currently "
            "blocks automatic changes."
        )

    if plan_status == "COMPATIBILITY_VALIDATION_REQUIRED":
        return (
            "A dependency migration candidate was found, but compatibility "
            "validation is incomplete."
        )

    if plan_status == "NO_ACTION_NON_DEPENDENCY_FAILURE":
        return (
            "The build failure is not dependency-related. No dependency "
            "changes will be made."
        )

    return (
        "The agent completed analysis, but no automatic remediation action "
        "is currently permitted."
    )


def print_notification(report):
    """Print the final migration-agent notification."""

    project = report.get("project", {})
    build = report.get("build", {})
    platform = report.get("platform", {})
    dependencies = report.get("dependencies", {})
    research = report.get("research", {})
    compatibility = report.get("compatibility", {})
    migration = report.get("migration", {})
    remediation = report.get("remediation", {})
    validation = report.get("validation", {})
    branch = report.get("branch", {})
    summary = report.get("summary", {})

    notification_message = determine_notification_message(report)

    print("=" * 60)
    print("DEPENDENCY MIGRATION AGENT NOTIFICATION")
    print("=" * 60)
    print(
        "Agent status        : {}".format(
            report.get("agentStatus", "UNKNOWN")
        )
    )
    print(
        "Generated at        : {}".format(
            report.get("generatedAt", "UNKNOWN")
        )
    )
    print(
        "Project             : {}".format(
            project.get("coordinates", "UNKNOWN")
        )
    )
    print(
        "Project version     : {}".format(
            project.get("version", "UNKNOWN")
        )
    )
    print(
        "Build status        : {}".format(
            build.get("status", "UNKNOWN")
        )
    )
    print(
        "Build classification: {}".format(
            build.get("classification", "unknown")
        )
    )
    print(
        "Plan status         : {}".format(
            migration.get("planStatus", "UNKNOWN")
        )
    )
    print(
        "Java version        : {}".format(
            platform.get("javaVersion", "UNKNOWN")
        )
    )
    print(
        "Spring Boot version : {}".format(
            platform.get("springBootVersion", "UNKNOWN")
        )
    )
    print(
        "Namespace           : {}".format(
            platform.get("namespace", "UNKNOWN")
        )
    )
    print(
        "Dependencies        : {}".format(
            dependencies.get("total", 0)
        )
    )
    print(
        "Migration candidates: {}".format(
            research.get(
                "migrationCandidates",
                summary.get("migrationCandidateCount", 0),
            )
        )
    )
    print(
        "Compatible          : {}".format(
            compatibility.get(
                "compatibleCandidates",
                summary.get("compatibleCandidateCount", 0),
            )
        )
    )
    print(
        "Remediation status  : {}".format(
            remediation.get("status", "UNKNOWN")
        )
    )
    print(
        "Planned changes     : {}".format(
            remediation.get("plannedChangeCount", 0)
        )
    )
    print(
        "Validation status   : {}".format(
            validation.get("status", "NOT_EXECUTED")
        )
    )
    print(
        "Tests run           : {}".format(
            validation.get("testsRun", 0)
        )
    )
    print(
        "Test failures       : {}".format(
            validation.get("testFailures", 0)
        )
    )
    print(
        "Coverage generated  : {}".format(
            validation.get("coverageGenerated", False)
        )
    )
    print(
        "SonarCloud          : {}".format(
            validation.get("sonarCloudStatus", "NOT_EXECUTED")
        )
    )
    print(
        "Automatic changes   : {}".format(
            migration.get("automaticChangesAllowed", False)
        )
    )
    print(
        "Branch creation     : {}".format(
            migration.get("branchCreationAllowed", False)
        )
    )
    print(
        "Branch required     : {}".format(
            branch.get("required", False)
        )
    )
    print(
        "Branch name         : {}".format(
            branch.get("name")
        )
    )
    print(
        "Commit allowed      : {}".format(
            validation.get("commitAllowed", False)
        )
    )
    print(
        "Next step           : {}".format(
            migration.get(
                "nextStep",
                summary.get("nextStep", "No next step was provided."),
            )
        )
    )
    print("-" * 60)
    print("Notification        : {}".format(notification_message))
    print("=" * 60)


def main():
    """Command-line entry point."""

    try:
        report = load_final_report()
        print_notification(report)
        return 0

    except (FileNotFoundError, ValueError) as error:
        print("NOTIFIER ERROR: {}".format(error))
        return 2

    except Exception as error:
        print("Unexpected notifier error: {}".format(error))
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
