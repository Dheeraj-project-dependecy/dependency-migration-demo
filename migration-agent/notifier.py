import json

REPORT_FILE = (
    "migration-agent/reports/final-agent-report.json"
)


def main():

    with open(REPORT_FILE, "r") as file:
        report = json.load(file)

    migration_plan = report["migration"]

    print("=" * 50)
    print("DEPENDENCY MIGRATION AGENT")
    print("=" * 50)

    print(
        "Plan Status:",
        migration_plan["planStatus"]
    )

    print(
        "Auto Changes:",
        migration_plan["automaticChangesAllowed"]
    )

    print(
        "Candidates:",
        migration_plan["research"]["candidateCount"]
    )

    print("=" * 50)


if __name__ == "__main__":
    main()