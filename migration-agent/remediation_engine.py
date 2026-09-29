"""
Generate a concrete remediation specification from migration-plan.json.

Input:
- migration-agent/reports/migration-plan.json

Output:
- migration-agent/reports/remediation-report.json

Version 1.1 behavior:
- Converts replacementGroups into detailed POM and Java source instructions.
- Consolidates duplicate replacement dependencies.
- Detects likely affected source files without changing them.
- Applies migration-plan and policy safety gates.
- Never modifies pom.xml, Java files, tests, or Git branches.
"""

import argparse
import json
from pathlib import Path


AGENT_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = AGENT_ROOT.parent
DEFAULT_PLAN = AGENT_ROOT / "reports" / "migration-plan.json"
DEFAULT_POLICY = AGENT_ROOT / "policy.json"
DEFAULT_OUTPUT = AGENT_ROOT / "reports" / "remediation-report.json"


SPRINGFOX_SOURCE_MAPPINGS = {
    "imports": [
        {
            "from": "io.swagger.annotations.Api",
            "to": "io.swagger.v3.oas.annotations.tags.Tag",
        },
        {
            "from": "io.swagger.annotations.ApiOperation",
            "to": "io.swagger.v3.oas.annotations.Operation",
        },
    ],
    "annotations": [
        {
            "from": "@Api",
            "to": "@Tag",
        },
        {
            "from": "@ApiOperation",
            "to": "@Operation",
        },
    ],
    "springfoxSymbols": [
        "Docket",
        "DocumentationType",
        "RequestHandlerSelectors",
        "PathSelectors",
        "EnableSwagger2",
        "springfox.documentation",
        "io.swagger.annotations",
    ],
}


def load_json(file_path, description, required=True):
    """Load and validate one JSON input file."""

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


def split_identifier(identifier):
    """Split groupId:artifactId coordinates safely."""

    if not identifier or ":" not in identifier:
        return {
            "groupId": None,
            "artifactId": None,
        }

    group_id, artifact_id = identifier.split(":", 1)

    return {
        "groupId": group_id,
        "artifactId": artifact_id,
    }


def dependency_operation(operation, dependency):
    """Create one structured Maven dependency operation."""

    identifier = dependency.get("identifier")
    coordinates = split_identifier(identifier)

    return {
        "operation": operation,
        "groupId": dependency.get("groupId") or coordinates.get("groupId"),
        "artifactId": (
            dependency.get("artifactId")
            or coordinates.get("artifactId")
        ),
        "version": dependency.get("version"),
        "scope": dependency.get("scope"),
        "identifier": identifier,
    }


def create_pom_operations(replacement_groups):
    """Create deduplicated remove and add operations for pom.xml."""

    remove_operations = []
    add_operations = []
    removed = set()
    added = set()

    for group in replacement_groups:
        for current in group.get("currentDependencies", []):
            identifier = current.get("identifier")

            if not identifier or identifier in removed:
                continue

            removed.add(identifier)
            remove_operations.append(
                dependency_operation("REMOVE", current)
            )

        replacement = group.get("replacement", {})
        replacement_identifier = replacement.get("identifier")
        replacement_version = replacement.get("version")
        replacement_key = "{}:{}".format(
            replacement_identifier,
            replacement_version,
        )

        if (
            replacement_identifier
            and replacement_version
            and replacement_key not in added
        ):
            added.add(replacement_key)
            add_operations.append(
                dependency_operation("ADD", replacement)
            )

    return remove_operations, add_operations


def java_files(project_root):
    """Return Java files under src/main/java and src/test/java."""

    locations = [
        project_root / "src" / "main" / "java",
        project_root / "src" / "test" / "java",
    ]
    files = []

    for location in locations:
        if location.exists():
            files.extend(location.rglob("*.java"))

    return files


def scan_affected_source_files(project_root):
    """Identify source files that reference old Swagger or Springfox APIs."""

    affected = []
    search_terms = list(SPRINGFOX_SOURCE_MAPPINGS["springfoxSymbols"])
    search_terms.extend(
        mapping["from"]
        for mapping in SPRINGFOX_SOURCE_MAPPINGS["annotations"]
    )

    for java_file in java_files(project_root):
        try:
            content = java_file.read_text(
                encoding="utf-8",
                errors="replace",
            )
        except OSError:
            continue

        matched_terms = [
            term
            for term in search_terms
            if term in content
        ]

        if not matched_terms:
            continue

        try:
            relative_path = java_file.relative_to(project_root)
            displayed_path = str(relative_path).replace("\\", "/")
        except ValueError:
            displayed_path = str(java_file)

        affected.append(
            {
                "file": displayed_path,
                "matchedTerms": sorted(set(matched_terms)),
                "changesApplied": False,
            }
        )

    return affected


def create_source_operations(replacement_groups, affected_files):
    """Create structured source-migration instructions."""

    replacement_identifiers = {
        group.get("replacement", {}).get("identifier")
        for group in replacement_groups
    }

    operations = []

    if "org.springdoc:springdoc-openapi-ui" not in replacement_identifiers:
        return operations

    operations.append(
        {
            "operation": "REPLACE_IMPORTS",
            "mappings": SPRINGFOX_SOURCE_MAPPINGS["imports"],
            "affectedFiles": [
                item.get("file")
                for item in affected_files
                if "io.swagger.annotations" in item.get("matchedTerms", [])
            ],
        }
    )
    operations.append(
        {
            "operation": "REPLACE_ANNOTATIONS",
            "mappings": SPRINGFOX_SOURCE_MAPPINGS["annotations"],
            "affectedFiles": [
                item.get("file")
                for item in affected_files
                if any(
                    term in item.get("matchedTerms", [])
                    for term in ["@Api", "@ApiOperation"]
                )
            ],
        }
    )
    operations.append(
        {
            "operation": "REMOVE_OR_REPLACE_SPRINGFOX_CONFIGURATION",
            "symbols": [
                "Docket",
                "DocumentationType",
                "RequestHandlerSelectors",
                "PathSelectors",
                "EnableSwagger2",
            ],
            "recommendation": (
                "Remove a single legacy Docket configuration when default "
                "SpringDoc scanning is sufficient. Otherwise replace it "
                "with a compatible OpenAPI or GroupedOpenApi configuration."
            ),
            "affectedFiles": [
                item.get("file")
                for item in affected_files
                if any(
                    term in item.get("matchedTerms", [])
                    for term in [
                        "Docket",
                        "DocumentationType",
                        "RequestHandlerSelectors",
                        "PathSelectors",
                        "EnableSwagger2",
                        "springfox.documentation",
                    ]
                )
            ],
        }
    )

    return operations


def create_validation_steps():
    """Define validation commands for the later apply phase."""

    return [
        {
            "order": 1,
            "name": "Compile",
            "command": "mvn clean compile",
            "required": True,
        },
        {
            "order": 2,
            "name": "Unit Tests",
            "command": "mvn test",
            "required": True,
        },
        {
            "order": 3,
            "name": "Verification and Coverage",
            "command": "mvn clean verify",
            "required": True,
            "expectedArtifact": "target/site/jacoco/jacoco.xml",
        },
        {
            "order": 4,
            "name": "SonarCloud Analysis",
            "command": "mvn sonar:sonar -Dsonar.token=<environment-token>",
            "required": False,
            "secretRequirement": "SONAR_TOKEN environment variable",
        },
    ]


def determine_state(plan, policy):
    """Apply plan and policy gates to the remediation decision."""

    plan_status = plan.get("planStatus", "UNKNOWN")
    remediation_eligible = plan.get("remediationEligible") is True
    plan_allows_changes = plan.get("automaticChangesAllowed") is True
    policy_allows_changes = policy.get("allowAutomaticChanges", False)

    if plan_status == "NO_ACTION_BUILD_HEALTHY":
        return {
            "status": "NO_ACTION",
            "reason": "The current build is healthy.",
            "remediationAllowed": False,
        }

    if not remediation_eligible:
        return {
            "status": "BLOCKED",
            "reason": (
                "The migration plan has not passed the remediation gates."
            ),
            "remediationAllowed": False,
        }

    if not policy_allows_changes:
        return {
            "status": "PLAN_READY_POLICY_BLOCKED",
            "reason": (
                "A compatible migration plan exists, but policy disables "
                "automatic changes."
            ),
            "remediationAllowed": False,
        }

    if not plan_allows_changes:
        return {
            "status": "PLAN_READY_NOT_AUTHORIZED",
            "reason": (
                "The migration plan did not authorize automatic changes."
            ),
            "remediationAllowed": False,
        }

    return {
        "status": "READY_TO_APPLY",
        "reason": (
            "The dependency failure, compatibility checks, and policy gates "
            "allow remediation."
        ),
        "remediationAllowed": True,
    }


def create_report(plan, policy, project_root):
    """Create the complete remediation specification."""

    replacement_groups = plan.get("replacementGroups", [])
    remove_operations, add_operations = create_pom_operations(
        replacement_groups
    )
    affected_files = scan_affected_source_files(project_root)
    source_operations = create_source_operations(
        replacement_groups,
        affected_files,
    )
    decision = determine_state(plan, policy)

    planned_changes = []

    if remove_operations or add_operations:
        planned_changes.append(
            {
                "target": "pom.xml",
                "type": "MAVEN_DEPENDENCY_UPDATE",
                "removeDependencies": remove_operations,
                "addDependencies": add_operations,
                "changesApplied": False,
            }
        )

    if source_operations:
        planned_changes.append(
            {
                "target": "src/**/*.java",
                "type": "JAVA_SOURCE_MIGRATION",
                "operations": source_operations,
                "changesApplied": False,
            }
        )

    return {
        "status": decision.get("status"),
        "reason": decision.get("reason"),
        "planStatus": plan.get("planStatus"),
        "executionMode": policy.get(
            "executionMode",
            "ANALYSIS_ONLY",
        ),
        "remediationAllowed": decision.get("remediationAllowed"),
        "automaticChangesPolicy": policy.get(
            "allowAutomaticChanges",
            False,
        ),
        "branchCreationPolicy": policy.get(
            "allowBranchCreation",
            False,
        ),
        "replacementGroupCount": len(replacement_groups),
        "affectedSourceFileCount": len(affected_files),
        "affectedSourceFiles": affected_files,
        "plannedChanges": planned_changes,
        "validationSteps": create_validation_steps(),
        "changesApplied": False,
        "validationExecuted": False,
        "commitCreated": False,
        "branchPushed": False,
        "nextStep": (
            "No remediation is required while the build is healthy."
            if decision.get("status") == "NO_ACTION"
            else (
                "Enable policy and execute the future apply phase on an "
                "isolated feature branch."
                if not decision.get("remediationAllowed")
                else (
                    "Create an isolated feature branch, apply the planned "
                    "changes, and execute all validation steps."
                )
            )
        ),
    }


def write_report(report, output_file):
    """Write remediation-report.json."""

    output_path = Path(output_file).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )
    return output_path


def print_summary(report, report_path):
    """Print a concise remediation summary."""

    print("=" * 60)
    print("REMEDIATION ENGINE")
    print("=" * 60)
    print("Status              : {}".format(report.get("status")))
    print("Plan status         : {}".format(report.get("planStatus")))
    print(
        "Remediation allowed : {}".format(
            report.get("remediationAllowed")
        )
    )
    print(
        "Replacement groups  : {}".format(
            report.get("replacementGroupCount", 0)
        )
    )
    print(
        "Affected Java files : {}".format(
            report.get("affectedSourceFileCount", 0)
        )
    )
    print(
        "Planned changes     : {}".format(
            len(report.get("plannedChanges", []))
        )
    )
    print("Changes applied     : {}".format(report.get("changesApplied")))
    print("Reason              : {}".format(report.get("reason")))

    print("Affected files:")

    affected_files = report.get("affectedSourceFiles", [])

    if affected_files:
        for item in affected_files:
            print("  - {}".format(item.get("file")))
    else:
        print("  - None")

    print("Report              : {}".format(report_path))


def main():
    """Command-line entry point."""

    parser = argparse.ArgumentParser(
        description="Generate a dependency remediation specification."
    )
    parser.add_argument(
        "--plan",
        default=str(DEFAULT_PLAN),
        help="Path to migration-plan.json.",
    )
    parser.add_argument(
        "--policy",
        default=str(DEFAULT_POLICY),
        help="Path to policy.json.",
    )
    parser.add_argument(
        "--project-root",
        default=str(PROJECT_ROOT),
        help="Project root containing pom.xml and src.",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help="Path for remediation-report.json.",
    )

    args = parser.parse_args()

    try:
        plan = load_json(args.plan, "Migration plan")
        policy = load_json(
            args.policy,
            "Agent policy",
            required=False,
        )
        project_root = Path(args.project_root).resolve()

        if not (project_root / "pom.xml").exists():
            raise FileNotFoundError(
                "pom.xml was not found under project root: {}".format(
                    project_root
                )
            )

        report = create_report(plan, policy, project_root)
        report_path = write_report(report, args.output)
        print_summary(report, report_path)
        return 0

    except (FileNotFoundError, ValueError) as error:
        print("ERROR: {}".format(error))
        return 2

    except Exception as error:
        print(
            "Unexpected remediation engine error: {}".format(error)
        )
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
