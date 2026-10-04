"""
Preview Java source changes from remediation-report.json.

Current version is dry-run only. It:
- reads remediation-report.json and policy.json
- inspects affected Java files
- identifies import, annotation, and Springfox configuration changes
- generates source-remediation-report.json
- never writes to Java source files

A future apply mode can reuse the generated preview after branch and policy
safety controls are implemented.
"""

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path


AGENT_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = AGENT_ROOT.parent
REPORTS_ROOT = AGENT_ROOT / "reports"
DEFAULT_REMEDIATION_REPORT = REPORTS_ROOT / "remediation-report.json"
DEFAULT_POLICY = AGENT_ROOT / "policy.json"
DEFAULT_OUTPUT = REPORTS_ROOT / "source-remediation-report.json"


DEFAULT_IMPORT_MAPPINGS = [
    {
        "from": "io.swagger.annotations.Api",
        "to": "io.swagger.v3.oas.annotations.tags.Tag",
    },
    {
        "from": "io.swagger.annotations.ApiOperation",
        "to": "io.swagger.v3.oas.annotations.Operation",
    },
]

DEFAULT_ANNOTATION_MAPPINGS = [
    {
        "from": "@ApiOperation",
        "to": "@Operation",
    },
    {
        "from": "@Api",
        "to": "@Tag",
    },
]

SPRINGFOX_CONFIGURATION_SYMBOLS = [
    "Docket",
    "DocumentationType",
    "RequestHandlerSelectors",
    "PathSelectors",
    "EnableSwagger2",
    "springfox.documentation",
]


def load_json(file_path, description, required=True):
    """Load and validate one JSON file."""

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


def normalize_relative_path(value):
    """Normalize a report path for the current operating system."""

    return Path(str(value).replace("\\", "/"))


def extract_report_operations(remediation_report):
    """Read source mappings from the remediation report."""

    import_mappings = []
    annotation_mappings = []
    configuration_symbols = []

    for planned_change in remediation_report.get("plannedChanges", []):
        if planned_change.get("type") != "JAVA_SOURCE_MIGRATION":
            continue

        for operation in planned_change.get("operations", []):
            operation_name = operation.get("operation")

            if operation_name == "REPLACE_IMPORTS":
                import_mappings.extend(operation.get("mappings", []))
            elif operation_name == "REPLACE_ANNOTATIONS":
                annotation_mappings.extend(operation.get("mappings", []))
            elif operation_name == "REMOVE_OR_REPLACE_SPRINGFOX_CONFIGURATION":
                configuration_symbols.extend(operation.get("symbols", []))

    if not import_mappings:
        import_mappings = list(DEFAULT_IMPORT_MAPPINGS)

    if not annotation_mappings:
        annotation_mappings = list(DEFAULT_ANNOTATION_MAPPINGS)

    if not configuration_symbols:
        configuration_symbols = list(SPRINGFOX_CONFIGURATION_SYMBOLS)

    return {
        "importMappings": unique_mappings(import_mappings),
        "annotationMappings": unique_mappings(annotation_mappings),
        "configurationSymbols": sorted(set(configuration_symbols)),
    }


def unique_mappings(mappings):
    """Deduplicate from/to mappings while preserving order."""

    result = []
    seen = set()

    for mapping in mappings:
        source = mapping.get("from")
        target = mapping.get("to")
        key = (source, target)

        if not source or not target or key in seen:
            continue

        seen.add(key)
        result.append({"from": source, "to": target})

    return result


def count_import_occurrences(content, old_import):
    """Count an exact Java import declaration."""

    pattern = re.compile(
        r"(?m)^\s*import\s+" + re.escape(old_import) + r"\s*;\s*$"
    )
    return len(pattern.findall(content))


def count_annotation_occurrences(content, old_annotation):
    """Count an annotation without matching longer annotation names."""

    annotation_name = old_annotation.lstrip("@")
    pattern = re.compile(
        r"@" + re.escape(annotation_name) + r"(?![A-Za-z0-9_])"
    )
    return len(pattern.findall(content))


def preview_file(file_path, project_root, operations):
    """Create a dry-run change preview for one Java file."""

    if not file_path.exists():
        return {
            "file": display_path(file_path, project_root),
            "status": "FILE_NOT_FOUND",
            "plannedChanges": [],
            "totalOccurrences": 0,
            "manualReviewRequired": False,
            "changesApplied": False,
        }

    if not file_path.is_file():
        return {
            "file": display_path(file_path, project_root),
            "status": "NOT_A_FILE",
            "plannedChanges": [],
            "totalOccurrences": 0,
            "manualReviewRequired": False,
            "changesApplied": False,
        }

    content = file_path.read_text(encoding="utf-8", errors="replace")
    planned_changes = []
    total_occurrences = 0

    for mapping in operations.get("importMappings", []):
        occurrences = count_import_occurrences(content, mapping["from"])

        if occurrences:
            planned_changes.append(
                {
                    "type": "IMPORT_REPLACEMENT",
                    "from": mapping["from"],
                    "to": mapping["to"],
                    "occurrences": occurrences,
                    "automatic": True,
                }
            )
            total_occurrences += occurrences

    for mapping in operations.get("annotationMappings", []):
        occurrences = count_annotation_occurrences(content, mapping["from"])

        if occurrences:
            planned_changes.append(
                {
                    "type": "ANNOTATION_REPLACEMENT",
                    "from": mapping["from"],
                    "to": mapping["to"],
                    "occurrences": occurrences,
                    "automatic": True,
                    "note": (
                        "Annotation attributes may require manual conversion "
                        "when Swagger 2 and OpenAPI 3 attributes differ."
                    ),
                }
            )
            total_occurrences += occurrences

    matched_configuration_symbols = [
        symbol
        for symbol in operations.get("configurationSymbols", [])
        if symbol in content
    ]

    manual_review_required = bool(matched_configuration_symbols)

    if manual_review_required:
        planned_changes.append(
            {
                "type": "SPRINGFOX_CONFIGURATION_REVIEW",
                "symbols": matched_configuration_symbols,
                "automatic": False,
                "recommendation": (
                    "Review the Springfox configuration. Remove a simple "
                    "Docket configuration if SpringDoc defaults are enough, "
                    "or replace it with a compatible OpenAPI configuration."
                ),
            }
        )

    status = "CHANGES_IDENTIFIED" if planned_changes else "NO_CHANGES_FOUND"

    return {
        "file": display_path(file_path, project_root),
        "status": status,
        "plannedChanges": planned_changes,
        "totalOccurrences": total_occurrences,
        "manualReviewRequired": manual_review_required,
        "changesApplied": False,
    }


def display_path(file_path, project_root):
    """Return a portable project-relative path when possible."""

    try:
        return str(file_path.relative_to(project_root)).replace("\\", "/")
    except ValueError:
        return str(file_path)


def affected_paths(remediation_report, project_root):
    """Collect unique affected Java paths from the remediation report."""

    paths = []
    seen = set()

    for item in remediation_report.get("affectedSourceFiles", []):
        relative_value = item.get("file")

        if not relative_value:
            continue

        relative_path = normalize_relative_path(relative_value)
        absolute_path = (project_root / relative_path).resolve()

        try:
            absolute_path.relative_to(project_root)
        except ValueError:
            continue

        key = str(absolute_path).lower()

        if key in seen:
            continue

        seen.add(key)
        paths.append(absolute_path)

    return paths


def determine_status(remediation_report, policy, files_identified):
    """Determine the dry-run decision without changing source files."""

    remediation_allowed = remediation_report.get("remediationAllowed") is True
    policy_allows_changes = policy.get("allowAutomaticChanges", False) is True
    execution_mode = policy.get("executionMode", "ANALYSIS_ONLY")

    if files_identified == 0:
        return {
            "status": "NO_SOURCE_FILES_IDENTIFIED",
            "reason": "No affected Java source files were identified.",
        }

    if execution_mode == "ANALYSIS_ONLY":
        return {
            "status": "BLOCKED_BY_POLICY",
            "reason": "Execution mode is ANALYSIS_ONLY.",
        }

    if not policy_allows_changes:
        return {
            "status": "BLOCKED_BY_POLICY",
            "reason": "Policy disables automatic changes.",
        }

    if not remediation_allowed:
        return {
            "status": "BLOCKED_BY_REMEDIATION_GATE",
            "reason": "The remediation report does not authorize changes.",
        }

    return {
        "status": "PREVIEW_READY",
        "reason": "Source changes are eligible for a future controlled apply run.",
    }


def create_report(remediation_report, policy, project_root):
    """Create the source-remediation dry-run report."""

    operations = extract_report_operations(remediation_report)
    source_paths = affected_paths(remediation_report, project_root)
    file_previews = [
        preview_file(file_path, project_root, operations)
        for file_path in source_paths
    ]

    files_with_changes = [
        item
        for item in file_previews
        if item.get("status") == "CHANGES_IDENTIFIED"
    ]
    manual_review_files = [
        item.get("file")
        for item in file_previews
        if item.get("manualReviewRequired") is True
    ]
    total_planned_operations = sum(
        len(item.get("plannedChanges", []))
        for item in file_previews
    )
    decision = determine_status(
        remediation_report,
        policy,
        len(source_paths),
    )

    return {
        "status": decision["status"],
        "reason": decision["reason"],
        "dryRun": True,
        "executionMode": policy.get("executionMode", "ANALYSIS_ONLY"),
        "policyAllowsAutomaticChanges": policy.get(
            "allowAutomaticChanges",
            False,
        ),
        "remediationAllowed": remediation_report.get(
            "remediationAllowed",
            False,
        ),
        "filesIdentified": len(source_paths),
        "filesWithPlannedChanges": len(files_with_changes),
        "filesModified": 0,
        "totalPlannedOperations": total_planned_operations,
        "manualReviewRequired": bool(manual_review_files),
        "manualReviewFiles": manual_review_files,
        "operations": operations,
        "files": file_previews,
        "changesApplied": False,
        "backupCreated": False,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "nextStep": (
            "Review the preview. No source files were modified."
            if file_previews
            else "No affected source files were available for preview."
        ),
    }


def write_report(report, output_file):
    """Write source-remediation-report.json."""

    output_path = Path(output_file).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )
    return output_path


def print_summary(report, report_path):
    """Print a concise source-remediation preview."""

    print("=" * 60)
    print("SOURCE REMEDIATOR")
    print("=" * 60)
    print("Status              : {}".format(report.get("status")))
    print("Dry run             : {}".format(report.get("dryRun")))
    print(
        "Files identified    : {}".format(
            report.get("filesIdentified", 0)
        )
    )
    print(
        "Files with changes  : {}".format(
            report.get("filesWithPlannedChanges", 0)
        )
    )
    print("Files modified      : {}".format(report.get("filesModified", 0)))
    print(
        "Planned operations  : {}".format(
            report.get("totalPlannedOperations", 0)
        )
    )
    print(
        "Manual review       : {}".format(
            report.get("manualReviewRequired", False)
        )
    )
    print("Changes applied     : {}".format(report.get("changesApplied")))
    print("Reason              : {}".format(report.get("reason")))

    print("Preview:")

    for file_result in report.get("files", []):
        print("  {}".format(file_result.get("file")))

        for change in file_result.get("plannedChanges", []):
            change_type = change.get("type")

            if change_type in [
                "IMPORT_REPLACEMENT",
                "ANNOTATION_REPLACEMENT",
            ]:
                print(
                    "    - {}: {} -> {} ({} occurrence(s))".format(
                        change_type,
                        change.get("from"),
                        change.get("to"),
                        change.get("occurrences", 0),
                    )
                )
            else:
                print(
                    "    - {}: manual review required".format(change_type)
                )

    print("Report              : {}".format(report_path))


def main():
    """Command-line entry point."""

    parser = argparse.ArgumentParser(
        description="Preview Java source remediation without changing files."
    )
    parser.add_argument(
        "--remediation-report",
        default=str(DEFAULT_REMEDIATION_REPORT),
        help="Path to remediation-report.json.",
    )
    parser.add_argument(
        "--policy",
        default=str(DEFAULT_POLICY),
        help="Path to policy.json.",
    )
    parser.add_argument(
        "--project-root",
        default=str(PROJECT_ROOT),
        help="Project root containing src and pom.xml.",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help="Path for source-remediation-report.json.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview only. This version is always dry-run.",
    )

    args = parser.parse_args()

    try:
        project_root = Path(args.project_root).resolve()

        if not project_root.exists() or not project_root.is_dir():
            raise ValueError(
                "Project root is not a directory: {}".format(project_root)
            )

        remediation_report = load_json(
            args.remediation_report,
            "Remediation report",
        )
        policy = load_json(
            args.policy,
            "Agent policy",
            required=False,
        )

        report = create_report(
            remediation_report,
            policy,
            project_root,
        )
        report_path = write_report(report, args.output)
        print_summary(report, report_path)
        return 0

    except (FileNotFoundError, ValueError) as error:
        print("ERROR: {}".format(error))
        return 2

    except Exception as error:
        print("Unexpected source remediator error: {}".format(error))
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
