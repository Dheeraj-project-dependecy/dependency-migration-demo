"""
Prepare dependency research candidates from a dependency scan report.

Current phase:
- Read dependency-scan.json.
- Extract direct dependencies.
- Build a structured internet-research queue.
- Write dependency-research.json.

This component does not yet:
- access the internet
- modify pom.xml
- modify source code
- create Git branches
- invoke Groq
"""

import argparse
import json
from pathlib import Path


def load_dependency_scan(input_file):
    """Load the structured dependency scan report."""

    input_path = Path(input_file).resolve()

    if not input_path.exists():
        raise FileNotFoundError(
            "Dependency scan report was not found: {}".format(
                input_path
            )
        )

    if not input_path.is_file():
        raise ValueError(
            "Dependency scan path is not a file: {}".format(
                input_path
            )
        )

    try:
        return json.loads(
            input_path.read_text(encoding="utf-8")
        )
    except json.JSONDecodeError as error:
        raise ValueError(
            "Dependency scan report is not valid JSON: {}".format(
                error
            )
        )


def create_identifier(dependency):
    """Create groupId:artifactId for a dependency."""

    group_id = dependency.get("groupId")
    artifact_id = dependency.get("artifactId")

    if not group_id or not artifact_id:
        return None

    return "{}:{}".format(
        group_id,
        artifact_id,
    )


def build_research_candidates(scan_data):
    """Create research candidates from direct Maven dependencies."""

    analysis = scan_data.get("analysis", {})
    direct_dependencies = analysis.get(
        "directDependencies",
        [],
    )

    candidates = []
    seen_identifiers = set()

    for dependency in direct_dependencies:
        identifier = dependency.get("identifier")

        if not identifier:
            identifier = create_identifier(dependency)

        if not identifier:
            continue

        if identifier in seen_identifiers:
            continue

        seen_identifiers.add(identifier)

        candidate = {
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
            "sources": [],
            "maintenanceStatus": "UNKNOWN",
            "latestKnownVersion": None,
            "replacementCandidates": [],
            "confidence": 0.0,
        }

        candidates.append(candidate)

    return candidates


def create_report(scan_data, candidates):
    """Create the dependency research queue report."""

    project = scan_data.get("project")

    pending_identifiers = [
        candidate.get("identifier")
        for candidate in candidates
        if candidate.get("researchStatus") == "PENDING"
    ]

    return {
        "researchStatus": "PENDING",
        "project": project,
        "dependenciesFound": len(candidates),
        "researchPendingCount": len(pending_identifiers),
        "researchPending": pending_identifiers,
        "candidates": candidates,
        "internetResearchPerformed": False,
        "note": (
            "This report contains research candidates only. "
            "Internet research will be added in the next phase."
        ),
    }


def write_report(report, output_file):
    """Write the dependency research report as JSON."""

    output_path = Path(output_file).resolve()

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_path.write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )

    return output_path


def print_summary(report, report_path):
    """Print a concise dependency research summary."""

    print("=" * 60)
    print("DEPENDENCY RESEARCH QUEUE")
    print("=" * 60)
    print(
        "Dependencies found : {}".format(
            report.get("dependenciesFound", 0)
        )
    )
    print(
        "Research pending   : {}".format(
            report.get("researchPendingCount", 0)
        )
    )
    print("Research queue:")

    pending_dependencies = report.get(
        "researchPending",
        [],
    )

    for dependency_identifier in pending_dependencies:
        print(
            "  - {}".format(
                dependency_identifier
            )
        )

    print(
        "Report             : {}".format(
            report_path
        )
    )


def main():
    """Command-line entry point."""

    parser = argparse.ArgumentParser(
        description=(
            "Prepare dependency candidates for internet research."
        )
    )

    parser.add_argument(
        "--input",
        default=(
            "migration-agent/reports/"
            "dependency-scan.json"
        ),
        help="Path to dependency-scan.json.",
    )

    parser.add_argument(
        "--output",
        default=(
            "migration-agent/reports/"
            "dependency-research.json"
        ),
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
            "Unexpected dependency researcher error: {}".format(
                error
            )
        )
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
