import json

REPORTS = {
    "build":
        "migration-agent/reports/build-analysis.json",

    "pom":
        "migration-agent/reports/pom-scan.json",

    "dependency":
        "migration-agent/reports/dependency-scan.json",

    "research":
        "migration-agent/reports/dependency-research.json",

    "compatibility":
        "migration-agent/reports/compatibility-report.json",

    "migration":
        "migration-agent/reports/migration-plan.json"
}

OUTPUT_FILE = (
    "migration-agent/reports/final-agent-report.json"
)


def load_json(path):
    with open(path, "r") as file:
        return json.load(file)


def main():

    report = {}

    for key, path in REPORTS.items():
        report[key] = load_json(path)

    with open(OUTPUT_FILE, "w") as file:
        json.dump(
            report,
            file,
            indent=2
        )

    print("Final report generated")


if __name__ == "__main__":
    main()