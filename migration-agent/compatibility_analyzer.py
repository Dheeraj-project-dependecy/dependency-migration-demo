"""
Analyze project-platform constraints for dependency migration research.

Inputs:
- pom-scan.json
- dependency-research.json

Output:
- compatibility-report.json

This phase is scan-only. It establishes compatibility constraints but does
not select or modify any dependency. Candidate-specific compatibility checks
will be added after internet research provides candidate metadata.
"""

import argparse
import json
import re
from pathlib import Path


def load_json(file_path, description):
    """Load and validate a JSON file."""

    path = Path(file_path).resolve()

    if not path.exists():
        raise FileNotFoundError(
            "{} was not found: {}".format(description, path)
        )

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


def normalize_java_version(value):
    """Convert Java version strings such as 1.8 or 21 into a major number."""

    if value is None:
        return None

    value_text = str(value).strip()

    if value_text.startswith("1."):
        parts = value_text.split(".")

        if len(parts) > 1 and parts[1].isdigit():
            return int(parts[1])

    match = re.match(r"^(\d+)", value_text)

    if match:
        return int(match.group(1))

    return None


def parse_version_numbers(value):
    """Extract numeric version components without assuming SemVer compliance."""

    if value is None:
        return []

    return [
        int(number)
        for number in re.findall(r"\d+", str(value))
    ]


def major_version(value):
    """Return the first numeric version component."""

    numbers = parse_version_numbers(value)

    if numbers:
        return numbers[0]

    return None


def detect_namespace_constraint(java_major, spring_boot_major):
    """Infer the namespace generation expected by the current platform."""

    if spring_boot_major is not None and spring_boot_major >= 3:
        return "jakarta"

    if java_major is not None or spring_boot_major is not None:
        return "javax"

    return "unknown"


def extract_platform(pom_scan):
    """Extract Java and framework constraints from the POM scan."""

    platform = pom_scan.get("platform", {})
    java_info = platform.get("javaVersion", {})
    spring_boot_info = platform.get("springBoot", {})

    java_value = java_info.get("value")
    spring_boot_value = spring_boot_info.get("version")

    java_major = normalize_java_version(java_value)
    spring_boot_major = major_version(spring_boot_value)

    properties = pom_scan.get("properties", {})

    spring_framework_value = (
        properties.get("spring.version")
        or properties.get("spring-framework.version")
    )

    return {
        "java": {
            "configuredVersion": java_value,
            "majorVersion": java_major,
            "sourceProperty": java_info.get("sourceProperty"),
        },
        "springBoot": {
            "configuredVersion": spring_boot_value,
            "majorVersion": spring_boot_major,
            "source": spring_boot_info.get("source"),
        },
        "springFramework": {
            "configuredVersion": spring_framework_value,
            "majorVersion": major_version(spring_framework_value),
        },
        "namespace": detect_namespace_constraint(
            java_major,
            spring_boot_major,
        ),
    }


def build_constraints(platform):
    """Create constraints that internet-researched candidates must satisfy."""

    java_major = platform.get("java", {}).get("majorVersion")
    spring_boot_major = platform.get("springBoot", {}).get("majorVersion")
    namespace = platform.get("namespace")

    constraints = []

    if java_major is not None:
        constraints.append(
            {
                "name": "java-runtime",
                "operator": "supports",
                "requiredValue": java_major,
                "description": (
                    "Replacement must support Java {} or lower runtime "
                    "requirements compatible with the project."
                ).format(java_major),
                "mandatory": True,
            }
        )

    if spring_boot_major is not None:
        constraints.append(
            {
                "name": "spring-boot-generation",
                "operator": "compatible-with",
                "requiredValue": spring_boot_major,
                "description": (
                    "Replacement must explicitly support Spring Boot {}.x."
                ).format(spring_boot_major),
                "mandatory": True,
            }
        )

    if namespace != "unknown":
        constraints.append(
            {
                "name": "java-ee-namespace",
                "operator": "uses",
                "requiredValue": namespace,
                "description": (
                    "Replacement must be compatible with the {} namespace."
                ).format(namespace),
                "mandatory": True,
            }
        )

    constraints.extend(
        [
            {
                "name": "artifact-availability",
                "operator": "exists-in",
                "requiredValue": "Maven Central or configured repository",
                "description": (
                    "The exact replacement artifact and version must be "
                    "available from an approved Maven repository."
                ),
                "mandatory": True,
            },
            {
                "name": "official-compatibility-evidence",
                "operator": "minimum-count",
                "requiredValue": 1,
                "description": (
                    "At least one official source must confirm platform "
                    "compatibility or provide migration guidance."
                ),
                "mandatory": True,
            },
            {
                "name": "total-research-evidence",
                "operator": "minimum-count",
                "requiredValue": 2,
                "description": (
                    "At least two trustworthy sources must support an "
                    "automatic migration recommendation."
                ),
                "mandatory": True,
            },
        ]
    )

    return constraints


def prepare_candidate_checks(research_report, constraints):
    """Attach pending compatibility checks to each research candidate."""

    candidates = research_report.get("candidates", [])
    candidate_checks = []

    check_names = [
        constraint.get("name")
        for constraint in constraints
        if constraint.get("mandatory")
    ]

    for candidate in candidates:
        candidate_checks.append(
            {
                "identifier": candidate.get("identifier"),
                "currentVersion": candidate.get("version"),
                "scope": candidate.get("scope"),
                "compatibilityStatus": "PENDING_RESEARCH",
                "actionable": False,
                "requiredChecks": [
                    {
                        "name": check_name,
                        "status": "PENDING",
                        "evidence": [],
                    }
                    for check_name in check_names
                ],
                "replacementCandidates": [],
                "rejectionReasons": [],
            }
        )

    return candidate_checks


def create_report(pom_scan, research_report):
    """Create the platform compatibility baseline report."""

    platform = extract_platform(pom_scan)
    constraints = build_constraints(platform)
    candidate_checks = prepare_candidate_checks(
        research_report,
        constraints,
    )

    unresolved_platform_values = []

    if platform.get("java", {}).get("majorVersion") is None:
        unresolved_platform_values.append("javaVersion")

    if platform.get("springBoot", {}).get("majorVersion") is None:
        unresolved_platform_values.append("springBootVersion")

    platform_status = (
        "READY"
        if not unresolved_platform_values
        else "INCOMPLETE"
    )

    return {
        "analysisStatus": "BASELINE_COMPLETE",
        "platformStatus": platform_status,
        "platform": platform,
        "constraints": constraints,
        "candidateCount": len(candidate_checks),
        "candidateChecks": candidate_checks,
        "unresolvedPlatformValues": unresolved_platform_values,
        "internetResearchRequired": True,
        "automaticMigrationAllowed": False,
        "nextStep": (
            "Research candidate versions and official compatibility "
            "evidence before evaluating automatic migration."
        ),
    }


def write_report(report, output_file):
    """Write the compatibility baseline as formatted JSON."""

    output_path = Path(output_file).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )
    return output_path


def print_summary(report, report_path):
    """Print a concise compatibility baseline summary."""

    platform = report.get("platform", {})
    java_data = platform.get("java", {})
    spring_boot_data = platform.get("springBoot", {})

    print("=" * 60)
    print("DEPENDENCY COMPATIBILITY BASELINE")
    print("=" * 60)
    print(
        "Platform status     : {}".format(
            report.get("platformStatus")
        )
    )
    print(
        "Java version        : {}".format(
            java_data.get("configuredVersion")
        )
    )
    print(
        "Spring Boot version : {}".format(
            spring_boot_data.get("configuredVersion")
        )
    )
    print(
        "Namespace           : {}".format(
            platform.get("namespace")
        )
    )
    print(
        "Constraints         : {}".format(
            len(report.get("constraints", []))
        )
    )
    print(
        "Candidates pending  : {}".format(
            report.get("candidateCount", 0)
        )
    )
    print(
        "Auto migration      : {}".format(
            report.get("automaticMigrationAllowed")
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
        description=(
            "Prepare platform compatibility constraints for dependency "
            "migration research."
        )
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
        "--output",
        default="migration-agent/reports/compatibility-report.json",
        help="Path for compatibility-report.json.",
    )

    args = parser.parse_args()

    try:
        pom_scan = load_json(args.pom_scan, "POM scan report")
        research_report = load_json(
            args.research,
            "Dependency research report",
        )
        report = create_report(pom_scan, research_report)
        report_path = write_report(report, args.output)
        print_summary(report, report_path)
        return 0

    except (FileNotFoundError, ValueError) as error:
        print("ERROR: {}".format(error))
        return 2

    except Exception as error:
        print(
            "Unexpected compatibility analyzer error: {}".format(
                error
            )
        )
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
