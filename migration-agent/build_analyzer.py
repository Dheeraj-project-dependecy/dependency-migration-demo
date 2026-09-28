"""
Analyze a Maven build log and classify the build result.

This is a scan-only component.

It does not:
- modify pom.xml
- modify Java code
- modify tests
- create Git branches
- push commits
"""

import argparse
import json
import re
from pathlib import Path


DEPENDENCY_ERROR_PATTERNS = {
    "dependency_resolution_failure": [
        r"Could not resolve dependencies",
        r"Could not find artifact",
        r"Failed to collect dependencies",
        r"Could not transfer artifact",
        r"DependencyResolutionException",
        r"Non-resolvable parent POM",
        r"Could not resolve artifact",
    ],
    "missing_class_or_package": [
        r"package\s+[\w.]+\s+does not exist",
        r"cannot find symbol",
        r"ClassNotFoundException",
        r"NoClassDefFoundError",
    ],
    "binary_incompatibility": [
        r"NoSuchMethodError",
        r"AbstractMethodError",
        r"IncompatibleClassChangeError",
        r"UnsupportedClassVersionError",
    ],
    "dependency_conflict": [
        r"omitted for conflict",
        r"Require upper bound dependencies error",
        r"dependency convergence error",
        r"version conflict",
    ],
}


NON_DEPENDENCY_ERROR_PATTERNS = {
    "java_syntax_error": [
        r"';' expected",
        r"illegal start of expression",
        r"reached end of file while parsing",
        r"not a statement",
        r"class, interface, or enum expected",
    ],
    "test_assertion_failure": [
        r"AssertionError",
        r"expected:.*but was:",
        r"expected.*but was",
        r"Failures:\s*[1-9]",
    ],
    "environment_or_configuration_failure": [
        r"Connection refused",
        r"UnknownHostException",
        r"ConnectException",
        r"Missing required property",
        r"Could not resolve placeholder",
        r"Access denied",
        r"Authentication failed",
        r"401 Unauthorized",
        r"403 Forbidden",
    ],
}


DEPENDENCY_HINTS = {
    "springfox": [
        "io.swagger.annotations",
        "springfox.documentation",
        "Docket",
        "DocumentationType",
        "ApiOperation",
        "ApiIgnore",
    ],
    "springdoc": [
        "org.springdoc",
        "io.swagger.v3.oas.annotations",
        "GroupedOpenApi",
        "OpenAPI",
    ],
    "jackson": [
        "com.fasterxml.jackson",
        "ObjectMapper",
        "JsonProcessingException",
    ],
    "spring": [
        "org.springframework",
        "SpringApplication",
        "ApplicationContext",
    ],
}


def read_log(log_path):
    """
    Read a Maven build log written using UTF-8, UTF-16, or Windows encoding.

    PowerShell may write redirected command output using UTF-16. Trying several
    encodings ensures BUILD SUCCESS and BUILD FAILURE remain detectable.
    """

    if not log_path.exists():
        raise FileNotFoundError(
            "Maven build log does not exist: {}".format(log_path)
        )

    if not log_path.is_file():
        raise ValueError(
            "Maven build log path is not a file: {}".format(log_path)
        )

    raw_data = log_path.read_bytes()

    encodings = [
        "utf-8-sig",
        "utf-16",
        "utf-16-le",
        "utf-16-be",
        "cp1252",
    ]

    for encoding in encodings:
        try:
            decoded_text = raw_data.decode(encoding)

            recognizable_content = any(
                marker in decoded_text
                for marker in [
                    "BUILD SUCCESS",
                    "BUILD FAILURE",
                    "[INFO]",
                    "[ERROR]",
                ]
            )

            if recognizable_content:
                return decoded_text

        except (UnicodeDecodeError, UnicodeError):
            continue

    return raw_data.decode(
        "utf-8",
        errors="replace",
    )


def matched_lines(log_text, patterns):
    """Return unique log lines matching the supplied patterns."""

    matches = []

    for line in log_text.splitlines():
        for pattern in patterns:
            if re.search(pattern, line, flags=re.IGNORECASE):
                cleaned_line = line.strip()

                if cleaned_line and cleaned_line not in matches:
                    matches.append(cleaned_line)

                break

    return matches[:20]


def extract_failed_goal(log_text):
    """Extract the Maven goal that failed."""

    pattern = (
        r"Failed to execute goal\s+"
        r"([^\s]+)\s+"
        r"\(([^)]+)\)"
    )

    match = re.search(
        pattern,
        log_text,
        flags=re.IGNORECASE,
    )

    if not match:
        return None

    return "{} ({})".format(
        match.group(1),
        match.group(2),
    )


def extract_error_files(log_text):
    """Extract Java source file paths mentioned in build errors."""

    files = []

    patterns = [
        r"(/[^\s:\[\]]+\.java)",
        r"([A-Za-z\]:[\\/][^\[\]\r\n]+?\.java)",
    ]

    for pattern in patterns:
        for match in re.finditer(pattern, log_text):
            file_path = match.group(1).strip()
            file_path = file_path.replace("\\", "/")

            if file_path not in files:
                files.append(file_path)

    return files[:20]


def detect_dependency_families(log_text):
    """Detect dependency families mentioned in the build log."""

    detected_families = []
    lowercase_log = log_text.lower()

    for dependency_name, hints in DEPENDENCY_HINTS.items():
        for hint in hints:
            if hint.lower() in lowercase_log:
                detected_families.append(dependency_name)
                break

    return detected_families


def detect_build_status(log_text):
    """
    Return the final Maven build status.

    The last status is used in case the log contains output from more than one
    Maven execution.
    """

    build_statuses = re.findall(
        r"BUILD\s+(SUCCESS|FAILURE)",
        log_text,
        flags=re.IGNORECASE,
    )

    if not build_statuses:
        if "[ERROR] Failed to execute goal" in log_text:
            return "FAILED"

        return "UNKNOWN"

    final_status = build_statuses[-1].upper()

    if final_status == "SUCCESS":
        return "SUCCESS"

    return "FAILED"


def classify_build(log_text):
    """
    Classify the Maven build conservatively.

    Dependency-related results remain non-actionable until a separate dependency
    scanner verifies the finding against pom.xml and the Maven dependency tree.
    """

    build_status = detect_build_status(log_text)

    if build_status == "SUCCESS":
        return {
            "buildStatus": "SUCCESS",
            "classification": "healthy",
            "confidence": "HIGH",
            "actionable": False,
            "verificationRequired": False,
            "suspectedDependencyFamilies": [],
            "dependencyCategories": [],
            "nonDependencyCategories": [],
            "dependencyScore": 0,
            "nonDependencyScore": 0,
            "failedGoal": None,
            "affectedFiles": [],
            "evidence": [
                "The final Maven result is BUILD SUCCESS."
            ],
        }

    dependency_evidence = []
    dependency_categories = []

    for category, patterns in DEPENDENCY_ERROR_PATTERNS.items():
        category_matches = matched_lines(log_text, patterns)

        if category_matches:
            dependency_categories.append(category)
            dependency_evidence.extend(category_matches)

    non_dependency_evidence = []
    non_dependency_categories = []

    for category, patterns in NON_DEPENDENCY_ERROR_PATTERNS.items():
        category_matches = matched_lines(log_text, patterns)

        if category_matches:
            non_dependency_categories.append(category)
            non_dependency_evidence.extend(category_matches)

    suspected_families = detect_dependency_families(log_text)
    affected_files = extract_error_files(log_text)
    failed_goal = extract_failed_goal(log_text)

    dependency_score = 0
    non_dependency_score = 0

    if dependency_evidence:
        dependency_score += 3

    if suspected_families:
        dependency_score += 2

    strong_dependency_categories = {
        "dependency_resolution_failure",
        "binary_incompatibility",
        "dependency_conflict",
    }

    if strong_dependency_categories.intersection(
        set(dependency_categories)
    ):
        dependency_score += 3

    if "missing_class_or_package" in dependency_categories:
        dependency_score += 2

    if non_dependency_evidence:
        non_dependency_score += 3

    if "java_syntax_error" in non_dependency_categories:
        non_dependency_score += 3

    if "test_assertion_failure" in non_dependency_categories:
        non_dependency_score += 2

    if (
        "environment_or_configuration_failure"
        in non_dependency_categories
    ):
        non_dependency_score += 3

    if (
        dependency_score >= 5
        and dependency_score > non_dependency_score
    ):
        classification = "dependency_related"

        if dependency_score >= 7:
            confidence = "HIGH"
        else:
            confidence = "MEDIUM"

        verification_required = True
        evidence = dependency_evidence

    elif non_dependency_score >= 5:
        classification = "non_dependency_related"
        confidence = "HIGH"
        verification_required = False
        evidence = non_dependency_evidence

    else:
        classification = "unknown"
        confidence = "LOW"
        verification_required = False
        evidence = dependency_evidence + non_dependency_evidence

    if not evidence:
        evidence = [
            "Build failure detected, but no known failure signature matched."
        ]

    return {
        "buildStatus": build_status,
        "classification": classification,
        "confidence": confidence,
        "actionable": False,
        "verificationRequired": verification_required,
        "suspectedDependencyFamilies": suspected_families,
        "dependencyCategories": dependency_categories,
        "nonDependencyCategories": non_dependency_categories,
        "dependencyScore": dependency_score,
        "nonDependencyScore": non_dependency_score,
        "failedGoal": failed_goal,
        "affectedFiles": affected_files,
        "evidence": evidence[:20],
    }


def analyze_build_log(log_file):
    """Analyze the supplied Maven build log."""

    log_path = Path(log_file).resolve()
    log_text = read_log(log_path)

    result = classify_build(log_text)
    result["logFile"] = str(log_path)

    return result


def write_report(result, output_file):
    """Write the analysis result to a JSON file."""

    output_path = Path(output_file).resolve()

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_path.write_text(
        json.dumps(result, indent=2),
        encoding="utf-8",
    )

    return output_path


def print_summary(analysis, report_path):
    """Print a readable build-analysis summary."""

    dependency_families = analysis.get(
        "suspectedDependencyFamilies",
        [],
    )

    if dependency_families:
        families_text = ", ".join(dependency_families)
    else:
        families_text = "None"

    print("=" * 60)
    print("MAVEN BUILD ANALYSIS")
    print("=" * 60)
    print(
        "Build status       : {}".format(
            analysis["buildStatus"]
        )
    )
    print(
        "Classification     : {}".format(
            analysis["classification"]
        )
    )
    print(
        "Confidence         : {}".format(
            analysis["confidence"]
        )
    )
    print(
        "Actionable         : {}".format(
            analysis["actionable"]
        )
    )
    print(
        "Verification needed: {}".format(
            analysis.get("verificationRequired", False)
        )
    )
    print(
        "Dependency families: {}".format(
            families_text
        )
    )
    print(
        "Failed goal        : {}".format(
            analysis["failedGoal"]
        )
    )
    print(
        "Affected files     : {}".format(
            len(analysis["affectedFiles"])
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
        description="Analyze a Maven build log."
    )

    parser.add_argument(
        "--build-log",
        required=True,
        help="Path to the Maven build log.",
    )

    parser.add_argument(
        "--output",
        default="migration-agent/reports/build-analysis.json",
        help="Path for the generated JSON report.",
    )

    args = parser.parse_args()

    try:
        analysis = analyze_build_log(args.build_log)

        report_path = write_report(
            analysis,
            args.output,
        )

        print_summary(
            analysis,
            report_path,
        )

        return 0

    except (FileNotFoundError, ValueError) as error:
        print("ERROR: {}".format(error))
        return 2

    except Exception as error:
        print(
            "Unexpected analyzer error: {}".format(error)
        )
        return 3


if __name__ == "__main__":
    raise SystemExit(main())