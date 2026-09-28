import json
from pathlib import Path

PLAN_FILE = "migration-agent/reports/migration-plan.json"
OUTPUT_FILE = "migration-agent/reports/remediation-report.json"


def main():

    with open(PLAN_FILE, "r") as file:
        plan = json.load(file)

    result = {
        "status": "NO_ACTION",
        "remediationAllowed": False,
        "reason": plan.get("planStatus")
    }

    with open(OUTPUT_FILE, "w") as file:
        json.dump(result, file, indent=2)

    print("Remediation Status:", result["status"])


if __name__ == "__main__":
    main()