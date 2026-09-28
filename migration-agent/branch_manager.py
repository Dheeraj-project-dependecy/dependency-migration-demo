import json
from pathlib import Path

OUTPUT_FILE = "migration-agent/reports/branch-report.json"


def build_branch_name():

    return "feature/dependency-migration"


def main():

    report = {
        "branchRequired": False,
        "branchName": build_branch_name()
    }

    with open(OUTPUT_FILE, "w") as file:
        json.dump(report, file, indent=2)

    print("Branch Name:", report["branchName"])


if __name__ == "__main__":
    main()