"""
Run Maven dependency analysis and generate a structured scan report.

This component is scan-only.

It does not:
- modify pom.xml
- update dependencies
- modify source code
- create Git branches
- access the internet
"""

import argparse
import json
import re
import shutil
import subprocess
from pathlib import Path


DEPENDENCY_PATTERN = re.compile(
    r"^([|+\-\s\\]*)"
    r"([\w.\-]+):"
    r"([\w.\-]+):"
    r"([\w.\-]+):"
    r"([^:\s]+):"
    r"([\w.\-]+)"
    r"(?:\s+\((.*)\))?$"
)


PROJECT_PATTERN = re.compile(
    r"^([\w.\-]+):"
    r"([\w.\-]+):"
    r"([\w.\-]+):"
    r"([^:\s]+)$"
)


def run_dependency_tree(project_root, text_output_file):
    """Run Maven dependency:tree and save the full textual output."""

    project_path = Path(project_root).resolve()
    pom_path = project_path / "pom.xml"

    if not project_path.exists():
        raise FileNotFoundError(
            "Project root does not exist: {}".format(project_path)
        )

    if not project_path.is_dir():
        raise ValueError(
            "Project root is not a directory: {}".format(project_path)
        )

    if not pom_path.exists():
        raise FileNotFoundError(
            "pom.xml does not exist: {}".format(pom_path)
        )

    output_path = Path(text_output_file).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    maven_command = shutil.which("mvn.cmd")

    if maven_command is None:
        maven_command = shutil.which("mvn")

    if maven_command is None:
        raise FileNotFoundError(
            "Maven was not found in the PATH available to Python. "
            "Ensure the Maven bin directory is configured in PATH."
        )

    command = [
        maven_command,
        "dependency:tree",
    ]

    completed_process = subprocess.run(
        command,
        cwd=str(project_path),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=False,
    )

    output_path.write_text(
        completed_process.stdout,
        encoding="utf-8",
    )

    return {
        "exitCode": completed_process.returncode,
        "output": completed_process.stdout,
        "outputFile": str(output_path),
        "command": " ".join(command),
    }


def remove_maven_prefix(line):
    """Remove Maven log prefixes such as [INFO] and [WARNING]."""

    cleaned_line = line.strip()

    prefixes = [
        "[INFO]",
        "[WARNING]",
        "[ERROR]",
        "[DEBUG]",
    ]

    for prefix in prefixes:
        if cleaned_line.startswith(prefix):
            cleaned_line = cleaned_line[len(prefix):].strip()
            break

    return cleaned_line


def calculate_depth(prefix):
    """Calculate dependency depth from Maven tree characters."""

    if not prefix:
        return 0

    normalized = prefix.replace("\\-", "+-")
    marker_position = normalized.rfind("+-")

    if marker_position < 0:
        return 0

    leading_part = normalized[:marker_position]

    # Maven normally uses three-character tree segments such as "|  " or "   ".
    return (len(leading_part) // 3) + 1


def parse_dependency_tree(tree_output):
    """Parse Maven dependency-tree output into structured dependency entries."""

    dependencies = []
    project = None

    # Each stack entry stores the most recent dependency found at a depth.
    dependency_stack = {}

    for raw_line in tree_output.splitlines():
        line = remove_maven_prefix(raw_line)

        if not line:
            continue

        project_match = PROJECT_PATTERN.match(line)

        if project_match and project is None:
            project = {
                "groupId": project_match.group(1),
                "artifactId": project_match.group(2),
                "type": project_match.group(3),
                "version": project_match.group(4),
                "coordinates": line,
            }
            continue

        match = DEPENDENCY_PATTERN.match(line)

        if not match:
            continue

        prefix = match.group(1)
        depth = calculate_depth(prefix)

        dependency = {
            "groupId": match.group(2),
            "artifactId": match.group(3),
            "type": match.group(4),
            "version": match.group(5),
            "scope": match.group(6),
            "depth": depth,
            "note": match.group(7),
        }

        dependency["identifier"] = "{}:{}".format(
            dependency["groupId"],
            dependency["artifactId"],
        )

        dependency["coordinates"] = "{}:{}:{}:{}:{}".format(
            dependency["groupId"],
            dependency["artifactId"],
            dependency["type"],
            dependency["version"],
            dependency["scope"],
        )

        parent = dependency_stack.get(depth - 1)

        if parent:
            dependency["parentIdentifier"] = parent.get("identifier")
            dependency["parentCoordinates"] = parent.get("coordinates")
        else:
            dependency["parentIdentifier"] = None
            dependency["parentCoordinates"] = None

        dependency_stack[depth] = dependency

        # Remove stale entries from deeper levels.
        stale_depths = [
            existing_depth
            for existing_depth in dependency_stack
            if existing_depth > depth
        ]

        for stale_depth in stale_depths:
            del dependency_stack[stale_depth]

        dependencies.append(dependency)

    return {
        "project": project,
        "dependencies": dependencies,
    }


def analyze_dependencies(parsed_tree):
    """Generate summary information from parsed dependencies."""

    dependencies = parsed_tree.get("dependencies", [])

    direct_dependencies = []
    transitive_dependencies = []
    conflicts = []
    omitted_dependencies = []
    scopes = {}
    versions_by_identifier = {}

    for dependency in dependencies:
        depth = dependency.get("depth", 0)

        if depth == 1:
            direct_dependencies.append(dependency)
        elif depth > 1:
            transitive_dependencies.append(dependency)

        note = dependency.get("note") or ""
        lowercase_note = note.lower()

        if "conflict" in lowercase_note:
            conflicts.append(dependency)

        if "omitted" in lowercase_note:
            omitted_dependencies.append(dependency)

        scope = dependency.get("scope") or "unknown"
        scopes[scope] = scopes.get(scope, 0) + 1

        identifier = dependency.get("identifier")
        version = dependency.get("version")

        versions_by_identifier.setdefault(identifier, [])

        if version not in versions_by_identifier[identifier]:
            versions_by_identifier[identifier].append(version)

    multiple_version_candidates = []

    for identifier, versions in versions_by_identifier.items():
        if len(versions) > 1:
            multiple_version_candidates.append(
                {
                    "identifier": identifier,
                    "versions": versions,
                }
            )

    return {
        "totalDependencies": len(dependencies),
        "directDependencyCount": len(direct_dependencies),
        "transitiveDependencyCount": len(transitive_dependencies),
        "conflictCount": len(conflicts),
        "omittedDependencyCount": len(omitted_dependencies),
        "multipleVersionCandidateCount": len(multiple_version_candidates),
        "scopeCounts": scopes,
        "directDependencies": direct_dependencies,
        "conflicts": conflicts,
        "omittedDependencies": omitted_dependencies,
        "multipleVersionCandidates": multiple_version_candidates,
    }


def scan_dependencies(project_root, text_output_file):
    """Run and analyze the Maven dependency tree."""

    execution = run_dependency_tree(
        project_root,
        text_output_file,
    )

    if execution["exitCode"] != 0:
        return {
            "scanStatus": "FAILED",
            "buildExitCode": execution["exitCode"],
            "command": execution["command"],
            "dependencyTreeFile": execution["outputFile"],
            "error": "Maven dependency:tree command failed.",
        }

    parsed_tree = parse_dependency_tree(execution["output"])
    analysis = analyze_dependencies(parsed_tree)

    return {
        "scanStatus": "SUCCESS",
        "buildExitCode": execution["exitCode"],
        "command": execution["command"],
        "dependencyTreeFile": execution["outputFile"],
        "project": parsed_tree["project"],
        "dependencies": parsed_tree["dependencies"],
        "analysis": analysis,
    }


def write_json_report(scan_result, output_file):
    """Write the dependency scan report to JSON."""

    output_path = Path(output_file).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    output_path.write_text(
        json.dumps(scan_result, indent=2),
        encoding="utf-8",
    )

    return output_path


def print_summary(scan_result, report_path):
    """Print a readable dependency scan summary."""

    print("=" * 60)
    print("MAVEN DEPENDENCY SCAN")
    print("=" * 60)

    print(
        "Scan status         : {}".format(
            scan_result.get("scanStatus")
        )
    )

    if scan_result.get("scanStatus") != "SUCCESS":
        print(
            "Error               : {}".format(
                scan_result.get("error")
            )
        )
        print(
            "Dependency tree file: {}".format(
                scan_result.get("dependencyTreeFile")
            )
        )
        print(
            "JSON report         : {}".format(report_path)
        )
        return

    analysis = scan_result.get("analysis", {})

    print(
        "Total dependencies  : {}".format(
            analysis.get("totalDependencies", 0)
        )
    )
    print(
        "Direct dependencies : {}".format(
            analysis.get("directDependencyCount", 0)
        )
    )
    print(
        "Transitive deps     : {}".format(
            analysis.get("transitiveDependencyCount", 0)
        )
    )
    print(
        "Conflicts detected  : {}".format(
            analysis.get("conflictCount", 0)
        )
    )
    print(
        "Omitted entries     : {}".format(
            analysis.get("omittedDependencyCount", 0)
        )
    )
    print(
        "Multiple versions   : {}".format(
            analysis.get("multipleVersionCandidateCount", 0)
        )
    )

    print("Direct dependency list:")

    direct_dependencies = analysis.get(
        "directDependencies",
        [],
    )

    for dependency in direct_dependencies:
        print(
            "  - {}:{}:{} [{}]".format(
                dependency.get("groupId"),
                dependency.get("artifactId"),
                dependency.get("version"),
                dependency.get("scope"),
            )
        )

    print(
        "Text tree           : {}".format(
            scan_result.get("dependencyTreeFile")
        )
    )
    print(
        "JSON report         : {}".format(report_path)
    )


def main():
    """Command-line entry point."""

    parser = argparse.ArgumentParser(
        description="Scan the resolved Maven dependency tree."
    )

    parser.add_argument(
        "--project-root",
        default=".",
        help="Maven project root containing pom.xml.",
    )
    parser.add_argument(
        "--tree-output",
        default="migration-agent/reports/dependency-tree.txt",
        help="Path for the Maven dependency-tree output.",
    )
    parser.add_argument(
        "--output",
        default="migration-agent/reports/dependency-scan.json",
        help="Path for the structured JSON report.",
    )

    args = parser.parse_args()

    try:
        scan_result = scan_dependencies(
            args.project_root,
            args.tree_output,
        )

        report_path = write_json_report(
            scan_result,
            args.output,
        )

        print_summary(
            scan_result,
            report_path,
        )

        if scan_result.get("scanStatus") == "SUCCESS":
            return 0

        return 1

    except (FileNotFoundError, ValueError) as error:
        print("ERROR: {}".format(error))
        return 2

    except Exception as error:
        print(
            "Unexpected dependency scanner error: {}".format(error)
        )
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
