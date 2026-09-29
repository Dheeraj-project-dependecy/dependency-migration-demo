"""
Enrich resolved Maven dependencies with migration research metadata.

Version 1.1 functionality:
- Read dependency-scan.json.
- Extract direct dependencies.
- Match dependencies against the built-in migration knowledge base.
- Mark known migration candidates as COMPLETE.
- Leave unknown dependencies pending for future internet research.
- Generate dependency-research.json.

This component does not:
- access the internet
- modify pom.xml
- modify source code
- create Git branches
- invoke Groq
"""

import argparse
import json
from pathlib import Path


# Temporary Version 1.1 knowledge base.
# This will be replaced by trusted internet research in a later enhancement.
KNOWN_MIGRATIONS = {
    "io.springfox:springfox-swagger2": {
        "maintenanceStatus": "LEGACY",
        "migrationRequired": True,
        "latestKnownVersion": "3.0.0",
        "replacementCandidates": [
            {
                "groupId": "org.springdoc",
                "artifactId": "springdoc-openapi-ui",
                "identifier": "org.springdoc:springdoc-openapi-ui",
                "version": None,
                "versionSelectionStatus": "COMPATIBILITY_CHECK_REQUIRED",
            }
        ],
        "migrationNotes": [
            "Replace Swagger 2 annotations with OpenAPI 3 annotations.",
            "Replace or remove Springfox Docket configuration.",
            "Validate the replacement against Java and Spring Boot constraints.",
        ],
        "confidence": 0.95,
        "sourceType": "INTERNAL_KNOWLEDGE_BASE",
    },
    "io.springfox:springfox-swagger-ui": {
        "maintenanceStatus": "LEGACY",
        "migrationRequired": True,
        "latestKnownVersion": "3.0.0",
        "replacementCandidates": [
            {
                "groupId": "org.springdoc",
                "artifactId": "springdoc-openapi-ui",
                "identifier": "org.springdoc:springdoc-openapi-ui",
                "version": None,
                "versionSelectionStatus": "COMPATIBILITY_CHECK_REQUIRED",
            }
        ],
        "migrationNotes": [
            "Replace the Springfox Swagger UI dependency.",
            "Select a SpringDoc version compatible with the current platform.",
        ],
        "confidence": 0.95,
        "sourceType": "INTERNAL_KNOWLEDGE_BASE",
    },
}


def load_dependency_scan(input_file):
    """Load and validate dependency-scan.json."""

    input_path = Path(input_file).resolve()

    if not input_path.exists():
        raise FileNotFoundError(
            "Dependency scan report was not found: {}".format(input_path)
        )

    if not input_path.is_file():
        raise ValueError(
            "Dependency scan path is not a file: {}".format(input_path)
        )

    try:
        return json.loads(input_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(
            "Dependency scan report is not valid JSON: {}".format(error)
        )


def create_identifier(dependency):
    """Create a groupId:artifactId identifier."""

    group_id = dependency.get("groupId")
    artifact_id = dependency.get("artifactId")

    if not group_id or not artifact_id:
        return None

    return "{}:{}".format(group_id, artifact_id)


def create_base_candidate(dependency, identifier):
    """Create the common candidate structure."""

    return {
        "groupId": dependency.get("groupId"),
        "artifactId": dependency.get("artifactId"),
        "version": dependency.get("version"),
        "scope": dependency.get("scope"),
        "type": dependency.get("type"),
        "identifier": identifier,
        "coordinates": dependency.get("coordinates"),
        "depth": dependency.get("depth"),
        "researchStatus": "PENDING",
        "researchRequired": True,
        "maintenanceStatus": "UNKNOWN",
        "migrationRequired": False,
        "latestKnownVersion": None,
        "replacementCandidates": [],
        "migrationNotes": [],
        "sources": [],
        "confidence": 0.0,
    }


def enrich_candidate(candidate):
    """Enrich a candidate using the temporary migration knowledge base."""

    identifier = candidate.get("identifier")
    migration_info = KNOWN_MIGRATIONS.get(identifier)

    if migration_info is None:
        candidate["researchStatus"] = "PENDING_INTERNET_RESEARCH"
        candidate["researchRequired"] = True
        return candidate

    candidate["researchStatus"] = "COMPLETE"
    candidate["researchRequired"] = False
    candidate["maintenanceStatus"] = migration_info.get(
        "maintenanceStatus",
        "UNKNOWN",
    )
    candidate["migrationRequired"] = migration_info.get(
        "migrationRequired",
        False,
    )
    candidate["latestKnownVersion"] = migration_info.get(
        "latestKnownVersion"
    )
    candidate["replacementCandidates"] = migration_info.get(
        "replacementCandidates",
        [],
    )
    candidate["migrationNotes"] = migration_info.get(
        "migrationNotes",
        [],
    )
    candidate["confidence"] = migration_info.get("confidence", 0.0)
    candidate["sources"] = [
        {
            "type": migration_info.get(
                "sourceType",
                "INTERNAL_KNOWLEDGE_BASE",
            ),
            "reference": "KNOWN_MIGRATIONS",
            "verifiedOnline": False,
        }
    ]

    return candidate


def build_research_candidates(scan_data):
    """Create and enrich candidates from direct Maven dependencies."""

    analysis = scan_data.get("analysis", {})
    direct_dependencies = analysis.get("directDependencies", [])

    candidates = []
    seen_identifiers = set()

    for dependency in direct_dependencies:
        identifier = dependency.get("identifier")

        if not identifier:
            identifier = create_identifier(dependency)

        if not identifier or identifier in seen_identifiers:
            continue

        seen_identifiers.add(identifier)

        candidate = create_base_candidate(dependency, identifier)
        candidate = enrich_candidate(candidate)
        candidates.append(candidate)

    return candidates


def create_report(scan_data, candidates):
    """Create the dependency research report."""

    completed = [
        candidate
        for candidate in candidates
        if candidate.get("researchStatus") == "COMPLETE"
    ]

    pending = [
        candidate
        for candidate in candidates
        if candidate.get("researchStatus") != "COMPLETE"
    ]

    migration_candidates = [
        candidate
        for candidate in candidates
        if candidate.get("migrationRequired") is True
    ]

    return {
        "researchStatus": (
            "PARTIAL"
            if pending
            else "COMPLETE"
        ),
        "project": scan_data.get("project"),
        "dependenciesFound": len(candidates),
        "researchCompletedCount": len(completed),
        "researchPendingCount": len(pending),
        "migrationCandidatesFound": len(migration_candidates),
        "researchCompleted": [
            candidate.get("identifier")
            for candidate in completed
        ],
        "researchPending": [
            candidate.get("identifier")
            for candidate in pending
        ],
        "migrationCandidates": [
            candidate.get("identifier")
            for candidate in migration_candidates
        ],
        "candidates": candidates,
        "internetResearchPerformed": False,
        "knowledgeSource": "INTERNAL_KNOWLEDGE_BASE",
        "automaticMigrationAllowed": False,
        "note": (
            "Known migrations were enriched from the temporary internal "
            "knowledge base. Online verification and candidate-version "
            "selection are still required before automatic remediation."
        ),
    }


def write_report(report, output_file):
    """Write dependency-research.json."""

    output_path = Path(output_file).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )
    return output_path


def print_summary(report, report_path):
    """Print a concise research summary."""

    print("=" * 60)
    print("DEPENDENCY RESEARCH")
    print("=" * 60)
    print(
        "Research status      : {}".format(
            report.get("researchStatus")
        )
    )
    print(
        "Dependencies found  : {}".format(
            report.get("dependenciesFound", 0)
        )
    )
    print(
        "Research completed  : {}".format(
            report.get("researchCompletedCount", 0)
        )
    )
    print(
        "Research pending    : {}".format(
            report.get("researchPendingCount", 0)
        )
    )
    print(
        "Migration candidates: {}".format(
            report.get("migrationCandidatesFound", 0)
        )
    )

    print("Known migration candidates:")

    migration_candidates = report.get("migrationCandidates", [])

    if migration_candidates:
        for identifier in migration_candidates:
            print("  - {}".format(identifier))
    else:
        print("  - None")

    print(
        "Online verification : {}".format(
            report.get("internetResearchPerformed")
        )
    )
    print("Report              : {}".format(report_path))


def main():
    """Command-line entry point."""

    parser = argparse.ArgumentParser(
        description="Enrich Maven dependencies with migration research data."
    )
    parser.add_argument(
        "--input",
        default="migration-agent/reports/dependency-scan.json",
        help="Path to dependency-scan.json.",
    )
    parser.add_argument(
        "--output",
        default="migration-agent/reports/dependency-research.json",
        help="Path for dependency-research.json.",
    )

    args = parser.parse_args()

    try:
        scan_data = load_dependency_scan(args.input)
        candidates = build_research_candidates(scan_data)
        report = create_report(scan_data, candidates)
        report_path = write_report(report, args.output)
        print_summary(report, report_path)
        return 0

    except (FileNotFoundError, ValueError) as error:
        print("ERROR: {}".format(error))
        return 2

    except Exception as error:
        print(
            "Unexpected dependency researcher error: {}".format(error)
        )
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
