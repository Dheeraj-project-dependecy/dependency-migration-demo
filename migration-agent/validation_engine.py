"""
Execute Maven validation and generate a structured validation report.

Inputs:
- migration-agent/reports/remediation-report.json
- migration-agent/policy.json

Output:
- migration-agent/reports/validation-report.json
- one log file per validation stage

Validation stages:
1. mvn clean compile
2. mvn test
3. mvn clean verify
4. Verify the JaCoCo XML report
5. Optionally execute SonarCloud analysis when explicitly requested

This component validates the working tree. It does not modify source files,
create Git branches, commit changes, or push to a remote repository.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
import time
from datetime import datetime, timezone
from pathlib import Path


AGENT_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = AGENT_ROOT.parent
REPORTS_ROOT = AGENT_ROOT / "reports"
DEFAULT_REMEDIATION_REPORT = REPORTS_ROOT / "remediation-report.json"
DEFAULT_POLICY = AGENT_ROOT / "policy.json"
DEFAULT_OUTPUT = REPORTS_ROOT / "validation-report.json"
DEFAULT_JACOCO_REPORT = PROJECT_ROOT / "target" / "site" / "jacoco" / "jacoco.xml"
DEFAULT_SUREFIRE_DIRECTORY = PROJECT_ROOT / "target" / "surefire-reports"


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


def locate_maven():
    """Locate Maven on Windows, Linux, or macOS."""

    candidates = [
        "mvn.cmd",
        "mvn",
    ]

    for candidate in candidates:
        resolved = shutil.which(candidate)

        if resolved:
            return resolved

    raise FileNotFoundError(
        "Maven was not found in PATH. Ensure the Maven bin directory is "
        "available to the Python process."
    )


def safe_log_name(stage_name):
    """Convert a stage name into a safe log filename."""

    normalized = re.sub(
        r"[^a-zA-Z0-9]+",
        "-",
        stage_name.strip().lower(),
    )

    return normalized.strip("-") + ".log"


def run_command(stage_name, command, project_root, reports_root):
    """Execute a command, save combined output, and return stage metadata."""

    started_at = datetime.now(timezone.utc)
    started_timer = time.monotonic()

    completed = subprocess.run(
        command,
        cwd=str(project_root),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=False,
    )

    duration_seconds = round(time.monotonic() - started_timer, 3)
    finished_at = datetime.now(timezone.utc)

    log_path = reports_root / safe_log_name(stage_name)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        completed.stdout or "",
        encoding="utf-8",
    )

    status = "SUCCESS" if completed.returncode == 0 else "FAILED"

    return {
        "name": stage_name,
        "status": status,
        "exitCode": completed.returncode,
        "command": command,
        "commandText": " ".join(command),
        "startedAt": started_at.isoformat(),
        "finishedAt": finished_at.isoformat(),
        "durationSeconds": duration_seconds,
        "logFile": str(log_path),
    }




def parse_surefire_reports(surefire_directory):
    """
    Parse Maven Surefire XML reports and return totals.
    """

    summary = {
        "reportDirectory": str(surefire_directory),
        "reportFound": False,
        "reportFileCount": 0,
        "tests": 0,
        "failures": 0,
        "errors": 0,
        "skipped": 0,
        "invalidReportFiles": []
    }

    if not surefire_directory.exists():
        return summary

    xml_files = list(
        surefire_directory.glob("TEST-*.xml")
    )

    summary["reportFound"] = len(xml_files) > 0
    summary["reportFileCount"] = len(xml_files)

    for xml_file in xml_files:
        try:
            tree = ET.parse(xml_file)
            root = tree.getroot()

            summary["tests"] += int(
                root.attrib.get("tests", 0)
            )

            summary["failures"] += int(
                root.attrib.get("failures", 0)
            )

            summary["errors"] += int(
                root.attrib.get("errors", 0)
            )

            summary["skipped"] += int(
                root.attrib.get("skipped", 0)
            )

        except Exception as error:
            summary["invalidReportFiles"].append(
                {
                    "file": str(xml_file),
                    "error": str(error)
                }
            )

    return summary
    if not surefire_directory.exists():
        return summary

    xml_files = list(surefire_directory.glob("TEST-*.xml"))
    summary["reportFound"] = len(xml_files) > 0
    summary["reportFileCount"] = len(xml_files)

    attribute_patterns = {
        "tests": re.compile(r'\btests="(\d+)"'),
        "failures": re.compile(r'\bfailures="(\d+)"'),
        "errors": re.compile(r'\berrors="(\d+)"'),
        "skipped": re.compile(r'\bskipped="(\d+)"'),
    }

    for xml_file in xml_files:
        try:
            content = xml_file.read_text(
                encoding="utf-8",
                errors="replace",
            )
        except OSError:
            continue

        opening_tag = content.split(">", 1)[0]

        for field_name, pattern in attribute_patterns.items():
            match = pattern.search(opening_tag)

            if match:
                summary[field_name] += int(match.group(1))

    return summary


def jacoco_status(jacoco_report):
    """Verify that the JaCoCo XML report exists and is non-empty."""

    exists = jacoco_report.exists()
    size = jacoco_report.stat().st_size if exists else 0

    return {
        "reportFound": exists and size > 0,
        "reportPath": str(jacoco_report),
        "sizeBytes": size,
    }


def should_run_sonar(arguments, policy):
    """Determine whether SonarCloud validation was explicitly enabled."""

    if arguments.run_sonar:
        return True

    validation_policy = policy.get("validation", {})

    return validation_policy.get("runSonarCloud", False) is True


def create_sonar_result(executed, status, reason, stage=None):
    """Create a consistent SonarCloud result object."""

    result = {
        "executed": executed,
        "status": status,
        "reason": reason,
    }

    if stage is not None:
        result["stage"] = stage

    return result


def execute_validation(
    project_root,
    reports_root,
    remediation_report,
    policy,
    run_sonar,
    continue_on_failure,
):
    """Execute compile, tests, verify, coverage, and optional SonarCloud."""

    maven = locate_maven()
    stages = []
    stopped_early = False

    commands = [
        (
            "Compile",
            [maven, "clean", "compile"],
        ),
        (
            "Unit Tests",
            [maven, "test"],
        ),
        (
            "Verification and Coverage",
            [maven, "clean", "verify"],
        ),
    ]

    for stage_name, command in commands:
        stage_result = run_command(
            stage_name,
            command,
            project_root,
            reports_root,
        )
        stages.append(stage_result)

        if (
            stage_result.get("status") == "FAILED"
            and not continue_on_failure
        ):
            stopped_early = True
            break

    surefire = parse_surefire_reports(
        project_root / "target" / "surefire-reports"
    )
    jacoco = jacoco_status(
        project_root / "target" / "site" / "jacoco" / "jacoco.xml"
    )

    required_stages_successful = (
        len(stages) == len(commands)
        and all(
            stage.get("status") == "SUCCESS"
            for stage in stages
        )
    )

    tests_successful = (
        surefire.get("reportFound") is True
        and surefire.get("failures", 0) == 0
        and surefire.get("errors", 0) == 0
    )

    coverage_successful = jacoco.get("reportFound") is True

    sonar = create_sonar_result(
        executed=False,
        status="SKIPPED",
        reason="SonarCloud validation was not requested.",
    )

    if run_sonar:
        sonar_token = os.environ.get("SONAR_TOKEN")

        if not sonar_token:
            sonar = create_sonar_result(
                executed=False,
                status="SKIPPED_MISSING_TOKEN",
                reason=(
                    "SONAR_TOKEN was not found in the environment. "
                    "The token was not read from any project file."
                ),
            )
        elif not required_stages_successful:
            sonar = create_sonar_result(
                executed=False,
                status="SKIPPED_VALIDATION_FAILED",
                reason=(
                    "SonarCloud was skipped because required Maven "
                    "validation did not succeed."
                ),
            )
        else:
            sonar_stage = run_command(
                "SonarCloud Analysis",
                [
                    maven,
                    "sonar:sonar",
                    "-Dsonar.token={}".format(sonar_token),
                ],
                project_root,
                reports_root,
            )

            # Never persist command arguments containing the token.
            sonar_stage["command"] = [
                maven,
                "sonar:sonar",
                "-Dsonar.token=<redacted>",
            ]
            sonar_stage["commandText"] = (
                "{} sonar:sonar -Dsonar.token=<redacted>".format(maven)
            )

            sonar = create_sonar_result(
                executed=True,
                status=sonar_stage.get("status"),
                reason=(
                    "SonarCloud analysis completed."
                    if sonar_stage.get("status") == "SUCCESS"
                    else "SonarCloud analysis failed."
                ),
                stage=sonar_stage,
            )

    required_success = (
        required_stages_successful
        and tests_successful
        and coverage_successful
    )

    if required_success:
        validation_status = "SUCCESS"
    elif stopped_early:
        validation_status = "FAILED_STOPPED_EARLY"
    else:
        validation_status = "FAILED"

    return {
        "validationStatus": validation_status,
        "projectRoot": str(project_root),
        "mavenExecutable": maven,
        "remediationStatus": remediation_report.get("status"),
        "remediationAllowed": remediation_report.get(
            "remediationAllowed",
            False,
        ),
        "changesAppliedBeforeValidation": remediation_report.get(
            "changesApplied",
            False,
        ),
        "baselineValidation": remediation_report.get("changesApplied") is not True,
        "continueOnFailure": continue_on_failure,
        "stoppedEarly": stopped_early,
        "stages": stages,
        "tests": surefire,
        "coverage": jacoco,
        "sonarCloud": sonar,
        "requiredStagesSuccessful": required_stages_successful,
        "testsSuccessful": tests_successful,
        "coverageSuccessful": coverage_successful,
        "commitAllowed": (
            required_success
            and remediation_report.get("changesApplied") is True
        ),
        "nextStep": (
            "Validation passed. Continue to commit review if changes were applied."
            if required_success
            else "Inspect failed-stage logs and do not commit or push changes."
        ),
        "generatedAt": datetime.now(timezone.utc).isoformat(),
    }


def write_report(report, output_file):
    """Write validation-report.json."""

    output_path = Path(output_file).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )
    return output_path


def print_summary(report, report_path):
    """Print a concise validation summary."""

    print("=" * 60)
    print("VALIDATION ENGINE")
    print("=" * 60)
    print(
        "Validation status   : {}".format(
            report.get("validationStatus")
        )
    )
    print(
        "Baseline validation : {}".format(
            report.get("baselineValidation")
        )
    )

    for stage in report.get("stages", []):
        print(
            "{:<20}: {} (exit {})".format(
                stage.get("name"),
                stage.get("status"),
                stage.get("exitCode"),
            )
        )

    tests = report.get("tests", {})
    print(
        "Tests               : {} run, {} failures, {} errors, {} skipped".format(
            tests.get("tests", 0),
            tests.get("failures", 0),
            tests.get("errors", 0),
            tests.get("skipped", 0),
        )
    )
    print(
        "JaCoCo report       : {}".format(
            report.get("coverage", {}).get("reportFound")
        )
    )
    print(
        "SonarCloud          : {}".format(
            report.get("sonarCloud", {}).get("status")
        )
    )
    print(
        "Commit allowed      : {}".format(
            report.get("commitAllowed")
        )
    )
    print("Report              : {}".format(report_path))


def main():
    """Command-line entry point."""

    parser = argparse.ArgumentParser(
        description="Validate Maven compilation, tests, coverage, and SonarCloud."
    )
    parser.add_argument(
        "--project-root",
        default=str(PROJECT_ROOT),
        help="Maven project root containing pom.xml.",
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
        "--output",
        default=str(DEFAULT_OUTPUT),
        help="Path for validation-report.json.",
    )
    parser.add_argument(
        "--run-sonar",
        action="store_true",
        help="Run SonarCloud if SONAR_TOKEN is available.",
    )
    parser.add_argument(
        "--continue-on-failure",
        action="store_true",
        help="Continue later Maven stages after an earlier stage fails.",
    )

    args = parser.parse_args()

    try:
        project_root = Path(args.project_root).resolve()

        if not project_root.exists() or not project_root.is_dir():
            raise ValueError(
                "Project root is not a directory: {}".format(project_root)
            )

        if not (project_root / "pom.xml").exists():
            raise FileNotFoundError(
                "pom.xml was not found under project root: {}".format(
                    project_root
                )
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

        report = execute_validation(
            project_root=project_root,
            reports_root=REPORTS_ROOT,
            remediation_report=remediation_report,
            policy=policy,
            run_sonar=should_run_sonar(args, policy),
            continue_on_failure=args.continue_on_failure,
        )

        report_path = write_report(report, args.output)
        print_summary(report, report_path)

        if report.get("validationStatus") == "SUCCESS":
            return 0

        return 1

    except (FileNotFoundError, ValueError) as error:
        print("ERROR: {}".format(error))
        return 2

    except Exception as error:
        print(
            "Unexpected validation engine error: {}".format(error)
        )
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
