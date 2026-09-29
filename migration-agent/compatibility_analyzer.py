"""
Evaluate dependency replacement candidates against project-platform constraints.

Inputs:
- migration-agent/reports/pom-scan.json
- migration-agent/reports/dependency-research.json
- migration-agent/policy.json

Output:
- migration-agent/reports/compatibility-report.json

Version 1.1 functionality:
- Detect Java, Spring Boot, Spring Framework, and namespace constraints.
- Evaluate replacement candidates produced by dependency_researcher.py.
- Select a compatible SpringDoc v1 replacement for the legacy demo platform.
- Keep unknown dependencies pending for future internet research.
- Never modify pom.xml, source code, tests, or Git branches.
"""

import argparse
import json
import re
from pathlib import Path


AGENT_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = AGENT_ROOT.parent
DEFAULT_POM_SCAN = AGENT_ROOT / "reports" / "pom-scan.json"
DEFAULT_RESEARCH_REPORT = AGENT_ROOT / "reports" / "dependency-research.json"
DEFAULT_POLICY = AGENT_ROOT / "policy.json"
DEFAULT_OUTPUT = AGENT_ROOT / "reports" / "compatibility-report.json"


# Temporary compatibility catalog for the functional MVP.
# Later, dependency_researcher.py will populate these facts from trusted
# internet sources and this catalog can be removed.
COMPATIBILITY_CATALOG = {
    "org.springdoc:springdoc-openapi-ui": [
        {
            "version": "1.8.0",
            "minimumJava": 8,
            "maximumJava": None,
            "supportedSpringBootMajors": [1, 2],
            "namespace": "javax",
            "status": "COMPATIBLE_LINE_ARCHIVED",
            "evidence": [
                {
                    "type": "OFFICIAL_DOCUMENTATION",
                    "url": "https://springdoc.org/v1/",
                    "claim": (
                        "SpringDoc v1 supports Spring Boot 1 and 2 and "
                        "documents springdoc-openapi-ui version 1.8.0."
                    ),
                },
                {
                    "type": "OFFICIAL_MIGRATION_GUIDE",
                    "url": (
                        "https://springdoc.org/v1/"
                        "migrating-from-springfox.html"
                    ),
                    "claim": (
                        "Remove Springfox dependencies, add "
                        "springdoc-openapi-ui 1.8.0, and migrate Swagger 2 "
                        "annotations to OpenAPI 3 annotations."
                    ),
                },
            ],
        }
    ]
}


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


def normalize_java_version(value):
    """Convert Java version strings such as 1.8 or 21 to major numbers."""

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


def version_major(value):
    """Return the first numeric component from a version string."""

    if value is None:
        return None

    match = re.search(r"\d+", str(value))

    if not match:
        return None

    return int(match.group(0))


def find_resolved_dependency_version(research_report, identifier):
    """Find a resolved dependency version in the research candidates."""

    for candidate in research_report.get("candidates", []):
        if candidate.get("identifier") == identifier:
            return candidate.get("version")

    return None


def find_spring_framework_version(pom_scan, research_report):
    """Find Spring Framework version from properties or resolved dependencies."""

    properties = pom_scan.get("properties", {})

    configured = (
        properties.get("spring.version")
        or properties.get("spring-framework.version")
    )

    if configured:
        return configured

    return find_resolved_dependency_version(
        research_report,
        "org.springframework:spring-core",
    )


def extract_platform(pom_scan, research_report):
    """Extract the project platform used for compatibility decisions."""

    platform = pom_scan.get("platform", {})
    java_info = platform.get("javaVersion", {})
    spring_boot_info = platform.get("springBoot", {})

    java_value = java_info.get("value")
    spring_boot_value = spring_boot_info.get("version")
    spring_framework_value = find_spring_framework_version(
        pom_scan,
        research_report,
    )

    java_major = normalize_java_version(java_value)
    spring_boot_major = version_major(spring_boot_value)
    spring_framework_major = version_major(spring_framework_value)

    namespace = "unknown"

    if spring_boot_major is not None:
        namespace = "jakarta" if spring_boot_major >= 3 else "javax"

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
            "majorVersion": spring_framework_major,
        },
        "namespace": namespace,
    }


def build_constraints(platform, policy):
    """Build mandatory constraints from platform and policy information."""

    constraints = []
    java_major = platform.get("java", {}).get("majorVersion")
    spring_boot_major = platform.get("springBoot", {}).get("majorVersion")
    namespace = platform.get("namespace")

    if java_major is not None:
        constraints.append(
            {
                "name": "java-runtime",
                "requiredValue": java_major,
                "mandatory": True,
            }
        )

    if spring_boot_major is not None:
        constraints.append(
            {
                "name": "spring-boot-generation",
                "requiredValue": spring_boot_major,
                "mandatory": True,
            }
        )

    if namespace != "unknown":
        constraints.append(
            {
                "name": "java-ee-namespace",
                "requiredValue": namespace,
                "mandatory": True,
            }
        )

    constraints.extend(
        [
            {
                "name": "artifact-availability",
                "requiredValue": True,
                "mandatory": True,
            },
            {
                "name": "official-compatibility-evidence",
                "requiredValue": 1,
                "mandatory": True,
            },
            {
                "name": "minimum-confidence",
                "requiredValue": policy.get(
                    "minimumConfidenceScore",
                    0.8,
                ),
                "mandatory": True,
            },
        ]
    )

    return constraints


def evaluate_catalog_entry(catalog_entry, platform):
    """Evaluate one exact replacement version against project constraints."""

    checks = []
    rejection_reasons = []

    java_major = platform.get("java", {}).get("majorVersion")
    boot_major = platform.get("springBoot", {}).get("majorVersion")
    namespace = platform.get("namespace")

    minimum_java = catalog_entry.get("minimumJava")
    maximum_java = catalog_entry.get("maximumJava")

    java_passed = (
        java_major is not None
        and minimum_java is not None
        and java_major >= minimum_java
        and (maximum_java is None or java_major <= maximum_java)
    )

    checks.append(
        {
            "name": "java-runtime",
            "status": "PASSED" if java_passed else "FAILED",
            "required": {
                "minimum": minimum_java,
                "maximum": maximum_java,
            },
            "actual": java_major,
        }
    )

    if not java_passed:
        rejection_reasons.append(
            "Replacement does not support the configured Java version."
        )

    supported_boot = catalog_entry.get("supportedSpringBootMajors", [])
    boot_passed = boot_major in supported_boot

    checks.append(
        {
            "name": "spring-boot-generation",
            "status": "PASSED" if boot_passed else "FAILED",
            "required": supported_boot,
            "actual": boot_major,
        }
    )

    if not boot_passed:
        rejection_reasons.append(
            "Replacement does not support Spring Boot {}.x.".format(
                boot_major
            )
        )

    required_namespace = catalog_entry.get("namespace")
    namespace_passed = namespace == required_namespace

    checks.append(
        {
            "name": "java-ee-namespace",
            "status": "PASSED" if namespace_passed else "FAILED",
            "required": required_namespace,
            "actual": namespace,
        }
    )

    if not namespace_passed:
        rejection_reasons.append(
            "Replacement namespace is not compatible with the project."
        )

    evidence = catalog_entry.get("evidence", [])
    evidence_passed = len(evidence) >= 1

    checks.append(
        {
            "name": "official-compatibility-evidence",
            "status": "PASSED" if evidence_passed else "FAILED",
            "required": 1,
            "actual": len(evidence),
            "evidence": evidence,
        }
    )

    if not evidence_passed:
        rejection_reasons.append(
            "No official compatibility evidence was recorded."
        )

    compatible = all(
        check.get("status") == "PASSED"
        for check in checks
    )

    return {
        "version": catalog_entry.get("version"),
        "status": "COMPATIBLE" if compatible else "INCOMPATIBLE",
        "catalogStatus": catalog_entry.get("status"),
        "checks": checks,
        "evidence": evidence,
        "rejectionReasons": rejection_reasons,
    }


def evaluate_replacement(replacement, platform):
    """Evaluate one replacement coordinate and select a compatible version."""

    identifier = replacement.get("identifier")
    catalog_versions = COMPATIBILITY_CATALOG.get(identifier, [])

    if not catalog_versions:
        return {
            "identifier": identifier,
            "groupId": replacement.get("groupId"),
            "artifactId": replacement.get("artifactId"),
            "requestedVersion": replacement.get("version"),
            "selectedVersion": None,
            "status": "PENDING_INTERNET_RESEARCH",
            "checks": [],
            "evidence": [],
            "reason": (
                "No compatibility metadata is available for this replacement."
            ),
        }

    requested_version = replacement.get("version")
    evaluations = []

    for catalog_entry in catalog_versions:
        if (
            requested_version is not None
            and catalog_entry.get("version") != requested_version
        ):
            continue

        evaluation = evaluate_catalog_entry(
            catalog_entry,
            platform,
        )
        evaluations.append(evaluation)

    compatible_evaluations = [
        evaluation
        for evaluation in evaluations
        if evaluation.get("status") == "COMPATIBLE"
    ]

    if compatible_evaluations:
        selected = compatible_evaluations[0]

        return {
            "identifier": identifier,
            "groupId": replacement.get("groupId"),
            "artifactId": replacement.get("artifactId"),
            "requestedVersion": requested_version,
            "selectedVersion": selected.get("version"),
            "status": "COMPATIBLE",
            "checks": selected.get("checks", []),
            "evidence": selected.get("evidence", []),
            "reason": (
                "A compatible replacement version was selected for the "
                "current Java, Spring Boot, and namespace constraints."
            ),
        }

    return {
        "identifier": identifier,
        "groupId": replacement.get("groupId"),
        "artifactId": replacement.get("artifactId"),
        "requestedVersion": requested_version,
        "selectedVersion": None,
        "status": "INCOMPATIBLE",
        "checks": evaluations,
        "evidence": [],
        "reason": (
            "No catalog version satisfies the current project constraints."
        ),
    }


def evaluate_candidate(candidate, platform, policy):
    """Evaluate all replacement options for one existing dependency."""

    identifier = candidate.get("identifier")
    research_status = candidate.get("researchStatus")
    replacements = candidate.get("replacementCandidates", [])
    confidence = candidate.get("confidence", 0.0)
    minimum_confidence = policy.get("minimumConfidenceScore", 0.8)

    result = {
        "identifier": identifier,
        "currentVersion": candidate.get("version"),
        "scope": candidate.get("scope"),
        "researchStatus": research_status,
        "migrationRequired": candidate.get("migrationRequired", False),
        "maintenanceStatus": candidate.get(
            "maintenanceStatus",
            "UNKNOWN",
        ),
        "researchConfidence": confidence,
        "minimumConfidenceRequired": minimum_confidence,
        "compatibilityStatus": "PENDING_RESEARCH",
        "actionable": False,
        "selectedReplacement": None,
        "replacementCandidates": [],
        "requiredChecks": [],
        "rejectionReasons": [],
    }

    if research_status != "COMPLETE":
        result["rejectionReasons"].append(
            "Dependency research is not complete."
        )
        return result

    if candidate.get("migrationRequired") is not True:
        result["compatibilityStatus"] = "NOT_REQUIRED"
        return result

    if confidence < minimum_confidence:
        result["compatibilityStatus"] = "INSUFFICIENT_CONFIDENCE"
        result["rejectionReasons"].append(
            "Research confidence is below the configured threshold."
        )
        return result

    if not replacements:
        result["compatibilityStatus"] = "NO_REPLACEMENT_FOUND"
        result["rejectionReasons"].append(
            "No replacement candidates were discovered."
        )
        return result

    evaluated_replacements = [
        evaluate_replacement(replacement, platform)
        for replacement in replacements
    ]

    result["replacementCandidates"] = evaluated_replacements

    compatible_replacements = [
        replacement
        for replacement in evaluated_replacements
        if replacement.get("status") == "COMPATIBLE"
    ]

    if not compatible_replacements:
        if any(
            replacement.get("status") == "PENDING_INTERNET_RESEARCH"
            for replacement in evaluated_replacements
        ):
            result["compatibilityStatus"] = "PENDING_RESEARCH"
        else:
            result["compatibilityStatus"] = "INCOMPATIBLE"

        result["rejectionReasons"].append(
            "No compatible replacement version was selected."
        )
        return result

    selected = compatible_replacements[0]
    result["compatibilityStatus"] = "COMPATIBLE"
    result["actionable"] = True
    result["selectedReplacement"] = {
        "groupId": selected.get("groupId"),
        "artifactId": selected.get("artifactId"),
        "identifier": selected.get("identifier"),
        "version": selected.get("selectedVersion"),
    }
    result["requiredChecks"] = selected.get("checks", [])

    return result


def create_report(pom_scan, research_report, policy):
    """Create the functional candidate compatibility report."""

    platform = extract_platform(pom_scan, research_report)
    constraints = build_constraints(platform, policy)

    candidate_checks = [
        evaluate_candidate(candidate, platform, policy)
        for candidate in research_report.get("candidates", [])
    ]

    compatible_candidates = [
        candidate
        for candidate in candidate_checks
        if candidate.get("compatibilityStatus") == "COMPATIBLE"
    ]

    pending_candidates = [
        candidate
        for candidate in candidate_checks
        if candidate.get("compatibilityStatus") == "PENDING_RESEARCH"
    ]

    incompatible_candidates = [
        candidate
        for candidate in candidate_checks
        if candidate.get("compatibilityStatus") == "INCOMPATIBLE"
    ]

    migration_candidates = [
        candidate
        for candidate in candidate_checks
        if candidate.get("migrationRequired") is True
    ]

    all_migration_candidates_compatible = (
        len(migration_candidates) > 0
        and all(
            candidate.get("compatibilityStatus") == "COMPATIBLE"
            for candidate in migration_candidates
        )
    )

    platform_ready = (
        platform.get("java", {}).get("majorVersion") is not None
        and platform.get("springBoot", {}).get("majorVersion") is not None
        and platform.get("namespace") != "unknown"
    )

    return {
        "analysisStatus": "COMPLETE",
        "platformStatus": "READY" if platform_ready else "INCOMPLETE",
        "platform": platform,
        "constraints": constraints,
        "candidateCount": len(candidate_checks),
        "migrationCandidateCount": len(migration_candidates),
        "compatibleCandidateCount": len(compatible_candidates),
        "pendingCandidateCount": len(pending_candidates),
        "incompatibleCandidateCount": len(incompatible_candidates),
        "candidateChecks": candidate_checks,
        "allMigrationCandidatesCompatible": (
            all_migration_candidates_compatible
        ),
        "automaticMigrationAllowed": (
            platform_ready
            and all_migration_candidates_compatible
            and policy.get("allowAutomaticChanges", False)
        ),
        "nextStep": (
            "Pass compatible replacement selections to migration_planner.py."
            if all_migration_candidates_compatible
            else "Complete missing research or resolve incompatibilities."
        ),
    }


def write_report(report, output_file):
    """Write compatibility-report.json."""

    output_path = Path(output_file).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )
    return output_path


def print_summary(report, report_path):
    """Print the functional compatibility summary."""

    platform = report.get("platform", {})

    print("=" * 60)
    print("DEPENDENCY COMPATIBILITY ANALYSIS")
    print("=" * 60)
    print("Platform status     : {}".format(report.get("platformStatus")))
    print(
        "Java version        : {}".format(
            platform.get("java", {}).get("configuredVersion")
        )
    )
    print(
        "Spring Boot version : {}".format(
            platform.get("springBoot", {}).get("configuredVersion")
        )
    )
    print("Namespace           : {}".format(platform.get("namespace")))
    print(
        "Migration candidates: {}".format(
            report.get("migrationCandidateCount", 0)
        )
    )
    print(
        "Compatible          : {}".format(
            report.get("compatibleCandidateCount", 0)
        )
    )
    print(
        "Pending research    : {}".format(
            report.get("pendingCandidateCount", 0)
        )
    )
    print(
        "Incompatible        : {}".format(
            report.get("incompatibleCandidateCount", 0)
        )
    )
    print(
        "All migration ready : {}".format(
            report.get("allMigrationCandidatesCompatible")
        )
    )
    print(
        "Auto migration      : {}".format(
            report.get("automaticMigrationAllowed")
        )
    )

    print("Selected replacements:")

    selected = [
        candidate
        for candidate in report.get("candidateChecks", [])
        if candidate.get("selectedReplacement")
    ]

    if selected:
        for candidate in selected:
            replacement = candidate.get("selectedReplacement", {})
            print(
                "  - {} -> {}:{}".format(
                    candidate.get("identifier"),
                    replacement.get("identifier"),
                    replacement.get("version"),
                )
            )
    else:
        print("  - None")

    print("Report              : {}".format(report_path))


def main():
    """Command-line entry point."""

    parser = argparse.ArgumentParser(
        description="Evaluate migration-candidate compatibility."
    )
    parser.add_argument(
        "--pom-scan",
        default=str(DEFAULT_POM_SCAN),
        help="Path to pom-scan.json.",
    )
    parser.add_argument(
        "--research",
        default=str(DEFAULT_RESEARCH_REPORT),
        help="Path to dependency-research.json.",
    )
    parser.add_argument(
        "--policy",
        default=str(DEFAULT_POLICY),
        help="Path to policy.json.",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help="Path for compatibility-report.json.",
    )

    args = parser.parse_args()

    try:
        pom_scan = load_json(args.pom_scan, "POM scan report")
        research_report = load_json(
            args.research,
            "Dependency research report",
        )
        policy = load_json(
            args.policy,
            "Agent policy",
            required=False,
        )

        report = create_report(pom_scan, research_report, policy)
        report_path = write_report(report, args.output)
        print_summary(report, report_path)
        return 0

    except (FileNotFoundError, ValueError) as error:
        print("ERROR: {}".format(error))
        return 2

    except Exception as error:
        print(
            "Unexpected compatibility analyzer error: {}".format(error)
        )
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
