"""
Generate a consolidated executive report for the migration agent.

Inputs:
- build-analysis.json
- pom-scan.json
- dependency-scan.json
- dependency-research.json
- compatibility-report.json
- migration-plan.json
- remediation-report.json
- validation-report.json (optional)
- branch-report.json (optional)

Output:
- final-agent-report.json
"""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


AGENT_ROOT = Path(__file__).resolve().parent
REPORTS_ROOT = AGENT_ROOT / "reports"
DEFAULT_OUTPUT = REPORTS_ROOT / "final-agent-report.json"


def load_json(report_name, required=True):
    """Load one report from the reports directory."""

    report_path = REPORTS_ROOT / report_name

    if not report_path.exists():
        if required:
            raise FileNotFoundError(
                "Required report was not found: {}".format(report_path)
            )
        return {}

    if not report_path.is_file():
        raise ValueError(
            "Report path is not a file: {}".format(report_path)
        )

    try:
        return json.loads(report_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(
            "Report contains invalid JSON: {}: {}".format(
                report_path,
                error,
            )
        )


def create_final_report():
    """Create a stable executive summary from all generated reports."""

    build = load_json("build-analysis.json")
    pom = load_json("pom-scan.json")
    dependency = load_json("dependency-scan.json")
    research = load_json("dependency-research.json")
    compatibility = load_json("compatibility-report.json")
    migration = load_json("migration-plan.json")
    remediation = load_json("remediation-report.json")
    validation = load_json("validation-report.json", required=False)
    branch = load_json("branch-report.json", required=False)

    project = pom.get("project", {})
    platform = pom.get("platform", {})
    java_info = platform.get("javaVersion", {})
    spring_boot_info = platform.get("springBoot", {})
    dependency_analysis = dependency.get("analysis", {})
    migration_research = migration.get("research", {})
    migration_compatibility = migration.get("compatibility", {})
    tests = validation.get("tests", {})
    coverage = validation.get("coverage", {})
    sonar = validation.get("sonarCloud", {})

    failed_components = []

    if build.get("buildStatus") not in ["SUCCESS", "FAILED"]:
        failed_components.append("build-analysis")

    if dependency.get("scanStatus") != "SUCCESS":
        failed_components.append("dependency-scan")

    if validation and validation.get("validationStatus") != "SUCCESS":
        failed_components.append("validation")

    agent_status = "SUCCESS" if not failed_components else "FAILED"

    migration_candidate_count = migration_research.get(
        "migrationCandidateCount",
        research.get("migrationCandidatesFound", 0),
    )

    compatible_candidate_count = migration_compatibility.get(
        "compatibleCandidateCount",
        compatibility.get("compatibleCandidateCount", 0),
    )

    return {
        "agentStatus": agent_status,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "project": {
            "groupId": project.get("groupId"),
            "artifactId": project.get("artifactId"),
            "version": project.get("version"),
            "coordinates": "{}:{}".format(
                project.get("groupId"),
                project.get("artifactId"),
            ),
        },
        "build": {
            "status": build.get("buildStatus", "UNKNOWN"),
            "classification": build.get("classification", "unknown"),
            "confidence": build.get("confidence"),
            "actionable": build.get("actionable", False),
        },
        "platform": {
            "javaVersion": java_info.get("value"),
            "springBootVersion": spring_boot_info.get("version"),
            "namespace": compatibility.get("platform", {}).get("namespace"),
        },
        "dependencies": {
            "total": dependency_analysis.get("totalDependencies", 0),
            "direct": dependency_analysis.get("directDependencyCount", 0),
            "transitive": dependency_analysis.get(
                "transitiveDependencyCount",
                0,
            ),
            "conflicts": dependency_analysis.get("conflictCount", 0),
        },
        "research": {
            "status": research.get("researchStatus", "UNKNOWN"),
            "completed": research.get("researchCompletedCount", 0),
            "pending": research.get("researchPendingCount", 0),
            "migrationCandidates": migration_candidate_count,
            "internetResearchPerformed": research.get(
                "internetResearchPerformed",
                False,
            ),
        },
        "compatibility": {
            "status": compatibility.get("analysisStatus", "UNKNOWN"),
            "platformStatus": compatibility.get("platformStatus", "UNKNOWN"),
            "compatibleCandidates": compatible_candidate_count,
            "allMigrationCandidatesCompatible": compatibility.get(
                "allMigrationCandidatesCompatible",
                False,
            ),
            "automaticMigrationAllowed": compatibility.get(
                "automaticMigrationAllowed",
                False,
            ),
        },
        "migration": {
            "planStatus": migration.get("planStatus", "UNKNOWN"),
            "replacementGroupCount": len(
                migration.get("replacementGroups", [])
            ),
            "remediationEligible": migration.get(
                "remediationEligible",
                False,
            ),
            "automaticChangesAllowed": migration.get(
                "automaticChangesAllowed",
                False,
            ),
            "branchCreationAllowed": migration.get(
                "branchCreationAllowed",
                False,
            ),
            "nextStep": migration.get("nextStep"),
        },
        "remediation": {
            "status": remediation.get("status", "UNKNOWN"),
            "allowed": remediation.get("remediationAllowed", False),
            "plannedChangeCount": len(
                remediation.get("plannedChanges", [])
            ),
            "affectedSourceFileCount": remediation.get(
                "affectedSourceFileCount",
                0,
            ),
            "changesApplied": remediation.get("changesApplied", False),
        },
        "validation": {
            "available": bool(validation),
            "status": validation.get("validationStatus", "NOT_EXECUTED"),
            "testsRun": tests.get("tests", 0),
            "testFailures": tests.get("failures", 0),
            "testErrors": tests.get("errors", 0),
            "testsSkipped": tests.get("skipped", 0),
            "testsSuccessful": validation.get("testsSuccessful", False),
            "coverageGenerated": coverage.get("reportFound", False),
            "sonarCloudStatus": sonar.get("status", "NOT_EXECUTED"),
            "commitAllowed": validation.get("commitAllowed", False),
        },
        "branch": {
            "required": branch.get("branchRequired", False),
            "name": branch.get("branchName"),
        },
        "failedComponents": failed_components,
        "summary": {
            "planStatus": migration.get("planStatus", "UNKNOWN"),
            "migrationCandidateCount": migration_candidate_count,
            "compatibleCandidateCount": compatible_candidate_count,
            "automaticChangesAllowed": migration.get(
                "automaticChangesAllowed",
                False,
            ),
            "branchCreationAllowed": migration.get(
                "branchCreationAllowed",
                False,
            ),
            "nextStep": migration.get("nextStep"),
        },
    }


def write_report(report, output_file):
    """Write final-agent-report.json."""

    output_path = Path(output_file).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )
    return output_path


def print_summary(report, report_path):
    """Print a concise final-report summary."""

    summary = report.get("summary", {})
    validation = report.get("validation", {})

    print("=" * 60)
    print("FINAL AGENT REPORT")
    print("=" * 60)
    print("Agent status        : {}".format(report.get("agentStatus")))
    print("Plan status         : {}".format(summary.get("planStatus")))
    print(
        "Migration candidates: {}".format(
            summary.get("migrationCandidateCount", 0)
        )
    )
    print(
        "Compatible          : {}".format(
            summary.get("compatibleCandidateCount", 0)
        )
    )
    print(
        "Validation status   : {}".format(
            validation.get("status")
        )
    )
    print(
        "Tests run           : {}".format(
            validation.get("testsRun", 0)
        )
    )
    print(
        "Coverage generated  : {}".format(
            validation.get("coverageGenerated", False)
        )
    )
    print(
        "Automatic changes   : {}".format(
            summary.get("automaticChangesAllowed", False)
        )
    )
    print("Report              : {}".format(report_path))


def main():
    """Command-line entry point."""

    parser = argparse.ArgumentParser(
        description="Generate the consolidated migration-agent report."
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help="Path for final-agent-report.json.",
    )

    args = parser.parse_args()

    try:
        report = create_final_report()
        report_path = write_report(report, args.output)
        print_summary(report, report_path)
        return 0

    except (FileNotFoundError, ValueError) as error:
        print("ERROR: {}".format(error))
        return 2

    except Exception as error:
        print("Unexpected report generator error: {}".format(error))
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
