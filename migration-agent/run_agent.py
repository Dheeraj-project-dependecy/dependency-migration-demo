"""
Migration Agent Orchestrator

Runs all agent stages sequentially.

No remediation.
No branch creation.
No dependency modification.
"""

import subprocess
import sys


STEPS = [
    {
        "name": "Build Analysis",
        "command": [
            sys.executable,
            "migration-agent/build_analyzer.py",
            "--build-log",
            "migration-agent/reports/maven-build.log"
        ]
    },
    {
        "name": "POM Scanner",
        "command": [
            sys.executable,
            "migration-agent/pom_scanner.py"
        ]
    },
    {
        "name": "Dependency Scanner",
        "command": [
            sys.executable,
            "migration-agent/dependency_scanner.py",
            "--project-root",
            "."
        ]
    },
    {
        "name": "Dependency Research",
        "command": [
            sys.executable,
            "migration-agent/dependency_researcher.py"
        ]
    },
    {
        "name": "Compatibility Analyzer",
        "command": [
            sys.executable,
            "migration-agent/compatibility_analyzer.py"
        ]
    },
    {
        "name": "Migration Planner",
        "command": [
            sys.executable,
            "migration-agent/migration_planner.py"
        ]
    }
]


def execute_step(step_number, total_steps, step):
    print()
    print(
        "[{}/{}] {}".format(
            step_number,
            total_steps,
            step["name"]
        )
    )

    result = subprocess.run(
        step["command"]
    )

    if result.returncode != 0:
        print(
            "FAILED: {}".format(
                step["name"]
            )
        )
        return False

    print(
        "SUCCESS: {}".format(
            step["name"]
        )
    )

    return True


def main():

    print("=" * 60)
    print("DEPENDENCY MIGRATION AGENT")
    print("=" * 60)

    total_steps = len(STEPS)

    for index, step in enumerate(STEPS, start=1):

        success = execute_step(
            index,
            total_steps,
            step
        )

        if not success:
            print()
            print("Pipeline stopped.")
            return 1

    print()
    print("=" * 60)
    print("AGENT EXECUTION COMPLETE")
    print("=" * 60)

    print(
        "Migration Plan Report:"
    )
    print(
        "migration-agent/reports/migration-plan.json"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())