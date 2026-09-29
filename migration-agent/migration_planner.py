"""
Create a concrete dependency migration plan from agent analysis reports.

Inputs:
- build-analysis.json
- pom-scan.json
- dependency-research.json
- compatibility-report.json
- policy.json

Output:
- migration-plan.json

Version 1.1 behavior:
- Keeps a healthy build in NO_ACTION_BUILD_HEALTHY state.
- Uses compatible replacements selected by compatibility_analyzer.py.
- Consolidates multiple old dependencies that share one replacement.
- Permits remediation only for a confirmed dependency-related build failure.
- Applies policy controls before allowing changes or branch creation.
- Does not directly modify files or execute Git commands.
"""

import argparse
import json
from pathlib import Path


AGENT_ROOT = Path(__file__).resolve().parent
DEFAULT_BUILD_ANALYSIS = AGENT_ROOT / "reports" / "build-analysis.json"
DEFAULT_POM_SCAN = AGENT_ROOT / "reports" / "pom-scan.json"
DEFAULT_RESEARCH = AGENT_ROOT / "reports" / "dependency-research.json"
DEFAULT_COMPATIBILITY = AGENT_ROOT / "reports" / "compatibility-report.json"
DEFAULT_POLICY = AGENT_ROOT / "policy.json"
DEFAULT_OUTPUT = AGENT_ROOT / "reports" / "migration-plan.json"


def load_json(file_path, description, required=True):
    """Load and validate a JSON file."""

    path = Path(file_path).resolve()

    if not path.exists():
        if required:
            raise FileNotFoundError(
                "{} was not found: {}".format(description, path)
            )
        return {}

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


def index_research_candidates(research_report):
    """Index dependency research candidates by identifier."""

    return {
        candidate.get("identifier"): candidate
        for candidate in research_report.get("candidates", [])
        if candidate.get("identifier")
    }


def build_candidate_plans(research_report, compatibility_report):
    """Build concrete candidate plans from compatibility selections."""

    research_index = index_research_candidates(research_report)
    candidate_plans = []

    for compatibility in compatibility_report.get("candidateChecks", []):
        identifier = compatibility.get("identifier")
        research = research_index.get(identifier, {})
        selected_replacement = compatibility.get("selectedReplacement")
        compatibility_status = compatibility.get(
            "compatibilityStatus",
            "PENDING_RESEARCH",
        )
        migration_required = compatibility.get(
            "migrationRequired",
            research.get("migrationRequired", False),
        )

        if not migration_required:
            action = "NO_MIGRATION_REQUIRED"
        elif compatibility_status == "COMPATIBLE" and selected_replacement:
            action = "REPLACE"
        elif compatibility_status == "INCOMPATIBLE":
            action = "INCOMPATIBLE_REPLACEMENT"
        elif compatibility_status == "INSUFFICIENT_CONFIDENCE":
            action = "RESEARCH_CONFIDENCE_TOO_LOW"
        elif compatibility_status == "NO_REPLACEMENT_FOUND":
            action = "NO_REPLACEMENT_CONFIRMED"
        else:
            action = "RESEARCH_REQUIRED"

        candidate_plans.append(
            {
                "dependency": identifier,
                "currentVersion": compatibility.get(
                    "currentVersion",
                    research.get("version"),
                ),
                "scope": compatibility.get(
                    "scope",
                    research.get("scope"),
                ),
                "maintenanceStatus": compatibility.get(
                    "maintenanceStatus",
                    research.get("maintenanceStatus", "UNKNOWN"),
                ),
                "migrationRequired": migration_required,
                "researchStatus": compatibility.get(
                    "researchStatus",
                    research.get("researchStatus", "PENDING"),
                ),
                "researchConfidence": compatibility.get(
                    "researchConfidence",
                    research.get("confidence", 0.0),
                ),
                "compatibilityStatus": compatibility_status,
                "selectedReplacement": selected_replacement,
                "action": action,
                "migrationNotes": research.get("migrationNotes", []),
                "researchSources": research.get("sources", []),
                "compatibilityChecks": compatibility.get(
                    "requiredChecks",
                    [],
                ),
                "rejectionReasons": compatibility.get(
                    "rejectionReasons",
                    [],
                ),
                "automaticChangeAllowed": False,
            }
        )

    return candidate_plans


def consolidate_replacements(candidate_plans):
    """Group old dependencies that share the same selected replacement."""

    grouped = {}

    for candidate in candidate_plans:
        if candidate.get("action") != "REPLACE":
            continue

        replacement = candidate.get("selectedReplacement") or {}
        replacement_identifier = replacement.get("identifier")
        replacement_version = replacement.get("version")

        if not replacement_identifier or not replacement_version:
            continue

        key = "{}:{}".format(
            replacement_identifier,
            replacement_version,
        )

        if key not in grouped:
            grouped[key] = {
                "action": "REPLACE",
                "currentDependencies": [],
                "replacement": {
                    "groupId": replacement.get("groupId"),
                    "artifactId": replacement.get("artifactId"),
                    "identifier": replacement_identifier,
                    "version": replacement_version,
                },
                "requiredSourceChanges": [],
                "confidence": 1.0,
            }

        grouped[key]["currentDependencies"].append(
            {
                "identifier": candidate.get("dependency"),
                "version": candidate.get("currentVersion"),
                "scope": candidate.get("scope"),
            }
        )

        grouped[key]["confidence"] = min(
            grouped[key]["confidence"],
            candidate.get("researchConfidence", 0.0),
        )

        for note in candidate.get("migrationNotes", []):
            if note not in grouped[key]["requiredSourceChanges"]:
                grouped[key]["requiredSourceChanges"].append(note)

    return list(grouped.values())


def summarize_actions(candidate_plans):
    """Count candidate-plan actions."""

    summary = {}

    for candidate in candidate_plans:
        action = candidate.get("action", "UNKNOWN")
        summary[action] = summary.get(action, 0) + 1

    return summary


def determine_failure_confirmation(build_analysis):
    """Determine whether a dependency-related failure is confirmed."""

    return (
        build_analysis.get("buildStatus") == "FAILED"
        and build_analysis.get("classification") == "dependency_related"
        and build_analysis.get("confidence") in ["HIGH", "MEDIUM"]
        and build_analysis.get("verificationRequired") is True
    )


def create_plan(
    build_analysis,
    pom_scan,
    research_report,
    compatibility_report,
    policy,
):
    """Create the migration plan and apply safety gates."""

    build_status = build_analysis.get("buildStatus", "UNKNOWN")
    build_classification = build_analysis.get(
        "classification",
        "unknown",
    )

    candidate_plans = build_candidate_plans(
        research_report,
        compatibility_report,
    )
    replacement_groups = consolidate_replacements(candidate_plans)
    action_summary = summarize_actions(candidate_plans)

    migration_candidates = [
        candidate
        for candidate in candidate_plans
        if candidate.get("migrationRequired") is True
    ]
    compatible_candidates = [
        candidate
        for candidate in migration_candidates
        if candidate.get("action") == "REPLACE"
    ]

    all_migration_candidates_compatible = (
        len(migration_candidates) > 0
        and len(compatible_candidates) == len(migration_candidates)
        and compatibility_report.get(
            "allMigrationCandidatesCompatible"
        ) is True
    )

    dependency_failure_confirmed = determine_failure_confirmation(
        build_analysis
    )

    policy_allows_changes = policy.get(
        "allowAutomaticChanges",
        False,
    )
    policy_allows_branch = policy.get(
        "allowBranchCreation",
        False,
    )

    if build_status == "SUCCESS":
        plan_status = "NO_ACTION_BUILD_HEALTHY"
        remediation_eligible = False
        next_step = "Stop. The daily build is healthy."
    elif build_classification != "dependency_related":
        plan_status = "NO_ACTION_NON_DEPENDENCY_FAILURE"
        remediation_eligible = False
        next_step = (
            "Report the non-dependency build failure. Do not modify "
            "dependencies."
        )
    elif not dependency_failure_confirmed:
        plan_status = "DEPENDENCY_FAILURE_VERIFICATION_REQUIRED"
        remediation_eligible = False
        next_step = (
            "Verify the suspected dependency failure before remediation."
        )
    elif not migration_candidates:
        plan_status = "NO_MIGRATION_CANDIDATE"
        remediation_eligible = False
        next_step = (
            "No migration candidate was identified. Escalate for review."
        )
    elif not all_migration_candidates_compatible:
        plan_status = "COMPATIBILITY_VALIDATION_REQUIRED"
        remediation_eligible = False
        next_step = (
            "Complete dependency research or resolve compatibility failures."
        )
    else:
        plan_status = "READY_FOR_REMEDIATION"
        remediation_eligible = True
        next_step = (
            "Create an isolated feature branch and apply the planned "
            "dependency and source-code changes."
        )

    automatic_changes_allowed = (
        remediation_eligible
        and policy_allows_changes
    )
    branch_creation_allowed = (
        automatic_changes_allowed
        and policy_allows_branch
    )

    for candidate in candidate_plans:
        candidate["automaticChangeAllowed"] = (
            automatic_changes_allowed
            and candidate.get("action") == "REPLACE"
        )

    project = pom_scan.get("project", {})
    platform = compatibility_report.get("platform", {})

    return {
        "planStatus": plan_status,
        "planningMode": policy.get(
            "executionMode",
            "ANALYSIS_ONLY",
        ),
        "project": project,
        "platform": {
            "javaVersion": platform.get("java", {}).get(
                "configuredVersion"
            ),
            "springBootVersion": platform.get("springBoot", {}).get(
                "configuredVersion"
            ),
            "springFrameworkVersion": platform.get(
                "springFramework",
                {},
            ).get("configuredVersion"),
            "namespace": platform.get("namespace"),
        },
        "build": {
            "status": build_status,
            "classification": build_classification,
            "confidence": build_analysis.get("confidence"),
            "failedGoal": build_analysis.get("failedGoal"),
            "affectedFiles": build_analysis.get("affectedFiles", []),
            "dependencyFailureConfirmed": dependency_failure_confirmed,
        },
        "research": {
            "status": research_report.get("researchStatus"),
            "completedCount": research_report.get(
                "researchCompletedCount",
                0,
            ),
            "pendingCount": research_report.get(
                "researchPendingCount",
                0,
            ),
            "migrationCandidateCount": len(migration_candidates),
            "internetResearchPerformed": research_report.get(
                "internetResearchPerformed",
                False,
            ),
        },
        "compatibility": {
            "status": compatibility_report.get("analysisStatus"),
            "platformStatus": compatibility_report.get("platformStatus"),
            "compatibleCandidateCount": compatibility_report.get(
                "compatibleCandidateCount",
                0,
            ),
            "allMigrationCandidatesCompatible": (
                all_migration_candidates_compatible
            ),
        },
        "migrationCandidates": candidate_plans,
        "replacementGroups": replacement_groups,
        "actionSummary": action_summary,
        "remediationEligible": remediation_eligible,
        "policyAllowsAutomaticChanges": policy_allows_changes,
        "policyAllowsBranchCreation": policy_allows_branch,
        "automaticChangesAllowed": automatic_changes_allowed,
        "branchCreationAllowed": branch_creation_allowed,
        "sourceModificationAllowed": automatic_changes_allowed,
        "pullRequestCreationAllowed": (
            branch_creation_allowed
            and policy.get("allowPullRequestCreation", False)
        ),
        "nextStep": next_step,
    }


def write_report(plan, output_file):
    """Write migration-plan.json."""

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
    print("Plan status         : {}".format(plan.get("planStatus")))
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
        "Failure confirmed   : {}".format(
            plan.get("build", {}).get("dependencyFailureConfirmed")
        )
    )
    print(
        "Migration candidates: {}".format(
            plan.get("research", {}).get("migrationCandidateCount", 0)
        )
    )
    print(
        "Compatible          : {}".format(
            plan.get("compatibility", {}).get(
                "compatibleCandidateCount",
                0,
            )
        )
    )
    print(
        "Replacement groups  : {}".format(
            len(plan.get("replacementGroups", []))
        )
    )
    print(
        "Remediation eligible: {}".format(
            plan.get("remediationEligible")
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

    print("Concrete replacements:")

    replacement_groups = plan.get("replacementGroups", [])

    if replacement_groups:
        for group in replacement_groups:
            old_dependencies = ", ".join(
                dependency.get("identifier")
                for dependency in group.get("currentDependencies", [])
            )
            replacement = group.get("replacement", {})
            print(
                "  - [{}] -> {}:{}".format(
                    old_dependencies,
                    replacement.get("identifier"),
                    replacement.get("version"),
                )
            )
    else:
        print("  - None")

    print("Next step           : {}".format(plan.get("nextStep")))
    print("Report              : {}".format(report_path))


def main():
    """Command-line entry point."""

    parser = argparse.ArgumentParser(
        description="Create a concrete dependency migration plan."
    )
    parser.add_argument(
        "--build-analysis",
        default=str(DEFAULT_BUILD_ANALYSIS),
        help="Path to build-analysis.json.",
    )
    parser.add_argument(
        "--pom-scan",
        default=str(DEFAULT_POM_SCAN),
        help="Path to pom-scan.json.",
    )
    parser.add_argument(
        "--research",
        default=str(DEFAULT_RESEARCH),
        help="Path to dependency-research.json.",
    )
    parser.add_argument(
        "--compatibility",
        default=str(DEFAULT_COMPATIBILITY),
        help="Path to compatibility-report.json.",
    )
    parser.add_argument(
        "--policy",
        default=str(DEFAULT_POLICY),
        help="Path to policy.json.",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help="Path for migration-plan.json.",
    )

    args = parser.parse_args()

    try:
        build_analysis = load_json(
            args.build_analysis,
            "Build analysis report",
        )
        pom_scan = load_json(args.pom_scan, "POM scan report")
        research_report = load_json(
            args.research,
            "Dependency research report",
        )
        compatibility_report = load_json(
            args.compatibility,
            "Compatibility report",
        )
        policy = load_json(
            args.policy,
            "Agent policy",
            required=False,
        )

        plan = create_plan(
            build_analysis,
            pom_scan,
            research_report,
            compatibility_report,
            policy,
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
