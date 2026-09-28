"""
Create a safe draft migration plan from agent analysis reports.

Inputs:
- build-analysis.json
- pom-scan.json
- dependency-research.json
- compatibility-report.json

Output:
- migration-plan.json

This phase is planning-only. It does not modify dependencies, source files,
tests, Git branches, or remote repositories.
"""

import argparse
import json
from pathlib import Path


def load_json(file_path, description, required=True):
    """Load a JSON report, optionally allowing a missing report."""

    path = Path(file_path).resolve()

    if not path.exists():
        if required:
            raise FileNotFoundError(
                "{} was not found: {}".format(description, path)
            )
        return None

    if not path.is_file():
        raise ValueError(
            "{} path is not a file: {}".format(description, path)
        )

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(
            "{} is not valid JSON: {}".format(description, error)
        )


def index_compatibility_checks(compatibility_report):
    """Index compatibility entries by dependency identifier."""

    indexed_checks = {}

    if compatibility_report is None:
        return indexed_checks

    for candidate in compatibility_report.get("candidateChecks", []):
        identifier = candidate.get("identifier")

        if identifier:
            indexed_checks[identifier] = candidate

    return indexed_checks


def determine_candidate_action(candidate, compatibility_check):
    """Determine the safe planning action for a candidate."""

    research_status = candidate.get("researchStatus", "PENDING")
    maintenance_status = candidate.get("maintenanceStatus", "UNKNOWN")
    replacements = candidate.get("replacementCandidates", [])

    compatibility_status = "NOT_EVALUATED"

    if compatibility_check:
        compatibility_status = compatibility_check.get(
            "compatibilityStatus",
            "PENDING_RESEARCH",
        )

    if research_status != "COMPLETE":
        return "RESEARCH_REQUIRED"

    if not replacements:
        return "NO_REPLACEMENT_CONFIRMED"

    if compatibility_status != "COMPATIBLE":
        return "COMPATIBILITY_VALIDATION_REQUIRED"

    if maintenance_status in ["DEPRECATED", "ARCHIVED", "UNMAINTAINED"]:
        return "READY_FOR_REVIEW"

    return "HUMAN_REVIEW_REQUIRED"


def create_candidate_plan(candidate, compatibility_check):
    """Create one safe, non-actionable migration candidate entry."""

    identifier = candidate.get("identifier")

    plan = {
        "dependency": identifier,
        "currentVersion": candidate.get("version"),
        "scope": candidate.get("scope"),
        "researchStatus": candidate.get("researchStatus", "PENDING"),
        "maintenanceStatus": candidate.get("maintenanceStatus", "UNKNOWN"),
        "latestKnownVersion": candidate.get("latestKnownVersion"),
        "replacementCandidates": candidate.get("replacementCandidates", []),
        "researchSources": candidate.get("sources", []),
        "researchConfidence": candidate.get("confidence", 0.0),
        "compatibilityStatus": (
            compatibility_check.get("compatibilityStatus")
            if compatibility_check
            else "NOT_EVALUATED"
        ),
        "requiredChecks": (
            compatibility_check.get("requiredChecks", [])
            if compatibility_check
            else []
        ),
        "action": determine_candidate_action(
            candidate,
            compatibility_check,
        ),
        "automaticChangeAllowed": False,
    }

    return plan


def select_candidates(research_report, compatibility_report):
    """Build candidate plans without hard-coded dependency rules."""

    candidates = research_report.get("candidates", [])
    compatibility_index = index_compatibility_checks(
        compatibility_report
    )
    plans = []

    for candidate in candidates:
        identifier = candidate.get("identifier")
        compatibility_check = compatibility_index.get(identifier)

        plans.append(
            create_candidate_plan(
                candidate,
                compatibility_check,
            )
        )

    return plans


def summarize_actions(candidate_plans):
    """Count candidates by planning action."""

    action_counts = {}

    for candidate in candidate_plans:
        action = candidate.get("action", "UNKNOWN")
        action_counts[action] = action_counts.get(action, 0) + 1

    return action_counts


def create_plan(
    build_analysis,
    pom_scan,
    research_report,
    compatibility_report,
):
    """Combine reports into a safe draft migration plan."""

    build_status = build_analysis.get("buildStatus", "UNKNOWN")
    build_classification = build_analysis.get(
        "classification",
        "unknown",
    )

    platform = pom_scan.get("platform", {})
    java_info = platform.get("javaVersion", {})
    spring_boot_info = platform.get("springBoot", {})

    candidate_plans = select_candidates(
        research_report,
        compatibility_report,
    )

    action_counts = summarize_actions(candidate_plans)

    dependency_failure_confirmed = (
        build_status == "FAILED"
        and build_classification == "dependency_related"
        and build_analysis.get("actionable") is True
    )

    compatibility_ready = (
        compatibility_report is not None
        and compatibility_report.get("platformStatus") == "READY"
    )

    internet_research_complete = (
        research_report.get("internetResearchPerformed") is True
        and research_report.get("researchStatus") == "COMPLETE"
    )

    ready_candidates = [
        candidate
        for candidate in candidate_plans
        if candidate.get("action") == "READY_FOR_REVIEW"
    ]

    automatic_changes_allowed = (
        dependency_failure_confirmed
        and compatibility_ready
        and internet_research_complete
        and len(ready_candidates) > 0
    )

    if build_status == "SUCCESS":
        plan_status = "NO_ACTION_BUILD_HEALTHY"
        next_step = "Stop. The daily build is healthy."
    elif build_classification != "dependency_related":
        plan_status = "NO_ACTION_NON_DEPENDENCY_FAILURE"
        next_step = (
            "Generate a diagnostic report. Do not create a dependency "
            "migration branch."
        )
    elif not internet_research_complete:
        plan_status = "DRAFT_RESEARCH_REQUIRED"
        next_step = (
            "Complete trusted internet research and compatibility evidence "
            "before proposing any dependency change."
        )
    elif not ready_candidates:
        plan_status = "DRAFT_NO_VERIFIED_REPLACEMENT"
        next_step = (
            "No verified compatible replacement is ready. Escalate for "
            "human review."
        )
    else:
        plan_status = "READY_FOR_HUMAN_REVIEW"
        next_step = (
            "Review evidence. A later remediation phase may create an "
            "isolated feature branch after policy approval."
        )

    return {
        "planStatus": plan_status,
        "planningMode": "ANALYSIS_ONLY",
        "build": {
            "status": build_status,
            "classification": build_classification,
            "confidence": build_analysis.get("confidence"),
            "failedGoal": build_analysis.get("failedGoal"),
            "affectedFiles": build_analysis.get("affectedFiles", []),
            "dependencyFailureConfirmed": dependency_failure_confirmed,
        },
        "project": pom_scan.get("project", {}),
        "platform": {
            "javaVersion": java_info.get("value"),
            "springBootVersion": spring_boot_info.get("version"),
            "namespace": (
                compatibility_report.get("platform", {}).get("namespace")
                if compatibility_report
                else None
            ),
        },
        "research": {
            "status": research_report.get("researchStatus"),
            "internetResearchPerformed": research_report.get(
                "internetResearchPerformed",
                False,
            ),
            "candidateCount": len(candidate_plans),
        },
        "compatibility": {
            "platformStatus": (
                compatibility_report.get("platformStatus")
                if compatibility_report
                else "NOT_AVAILABLE"
            ),
            "automaticMigrationAllowedByCompatibility": (
                compatibility_report.get("automaticMigrationAllowed", False)
                if compatibility_report
                else False
            ),
        },
        "migrationCandidates": candidate_plans,
        "actionSummary": action_counts,
        "readyCandidateCount": len(ready_candidates),
        "automaticChangesAllowed": automatic_changes_allowed,
        "branchCreationAllowed": False,
        "sourceModificationAllowed": False,
        "nextStep": next_step,
    }


def write_report(plan, output_file):
    """Write the migration plan as formatted JSON."""

    output_path = Path(output_file).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(plan, indent=2),
        encoding="utf-8",
    )
    return output_path


def print_summary(plan, report_path):
    """Print a concise migration-plan summary."""

    print("=" * 60)
    print("MIGRATION PLAN")
    print("=" * 60)
    print(
        "Plan status         : {}".format(
            plan.get("planStatus")
        )
    )
    print(
        "Build status        : {}".format(
            plan.get("build", {}).get("status")
        )
    )
    print(
        "Build classification: {}".format(
            plan.get("build", {}).get("classification")
        )
    )
    print(
        "Candidates          : {}".format(
            plan.get("research", {}).get("candidateCount", 0)
        )
    )
    print(
        "Ready candidates    : {}".format(
            plan.get("readyCandidateCount", 0)
        )
    )
    print(
        "Automatic changes   : {}".format(
            plan.get("automaticChangesAllowed")
        )
    )
    print(
        "Branch creation     : {}".format(
            plan.get("branchCreationAllowed")
        )
    )
    print(
        "Next step           : {}".format(
            plan.get("nextStep")
        )
    )
    print(
        "Report              : {}".format(
            report_path
        )
    )


def main():
    """Command-line entry point."""

    parser = argparse.ArgumentParser(
        description="Create a safe draft dependency migration plan."
    )
    parser.add_argument(
        "--build-analysis",
        default="migration-agent/reports/build-analysis.json",
        help="Path to build-analysis.json.",
    )
    parser.add_argument(
        "--pom-scan",
        default="migration-agent/reports/pom-scan.json",
        help="Path to pom-scan.json.",
    )
    parser.add_argument(
        "--research",
        default="migration-agent/reports/dependency-research.json",
        help="Path to dependency-research.json.",
    )
    parser.add_argument(
        "--compatibility",
        default="migration-agent/reports/compatibility-report.json",
        help="Path to compatibility-report.json.",
    )
    parser.add_argument(
        "--output",
        default="migration-agent/reports/migration-plan.json",
        help="Path for migration-plan.json.",
    )

    args = parser.parse_args()

    try:
        build_analysis = load_json(
            args.build_analysis,
            "Build analysis report",
            required=True,
        )
        pom_scan = load_json(
            args.pom_scan,
            "POM scan report",
            required=True,
        )
        research_report = load_json(
            args.research,
            "Dependency research report",
            required=True,
        )
        compatibility_report = load_json(
            args.compatibility,
            "Compatibility report",
            required=False,
        )

        plan = create_plan(
            build_analysis,
            pom_scan,
            research_report,
            compatibility_report,
        )
        report_path = write_report(plan, args.output)
        print_summary(plan, report_path)
        return 0

    except (FileNotFoundError, ValueError) as error:
        print("ERROR: {}".format(error))
        return 2

    except Exception as error:
        print(
            "Unexpected migration planner error: {}".format(error)
        )
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
