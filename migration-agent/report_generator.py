import json
from datetime import datetime


def load_json(path):
    with open(path, "r") as file:
        return json.load(file)


def main():

    build = load_json(
        "migration-agent/reports/build-analysis.json"
    )

    pom = load_json(
        "migration-agent/reports/pom-scan.json"
    )

    dependency = load_json(
        "migration-agent/reports/dependency-scan.json"
    )

    migration = load_json(
        "migration-agent/reports/migration-plan.json"
    )

    final_report = {
        "agentStatus": "SUCCESS",

        "generatedAt": datetime.now().isoformat(),

        "project": "{}:{}".format(
            pom["project"]["groupId"],
            pom["project"]["artifactId"]
        ),

        "buildStatus": build["buildStatus"],

        "planStatus": migration["planStatus"],

        "javaVersion":
            pom["platform"]["javaVersion"]["value"],

        "springBootVersion":
            pom["platform"]["springBoot"]["version"],

        "dependencyCount":
            dependency["analysis"]["totalDependencies"],

        "migrationCandidateCount":
            migration["research"]["candidateCount"],

        "automaticChangesAllowed":
            migration["automaticChangesAllowed"],

        "branchCreationAllowed":
            migration["branchCreationAllowed"],

        "nextStep":
            migration["nextStep"]
    }

    with open(
        "migration-agent/reports/final-agent-report.json",
        "w"
    ) as file:
        json.dump(
            final_report,
            file,
            indent=2
        )

    print("Final report generated")
    print(
        json.dumps(
            final_report,
            indent=2
        )
    )


if __name__ == "__main__":
    main()