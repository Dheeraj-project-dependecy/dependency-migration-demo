# Module Description

## build_analyzer.py

Analyzes Maven build logs.

Responsibilities:

- Detect build success/failure
- Classify failures
- Generate build-analysis.json

---

## pom_scanner.py

Scans pom.xml.

Responsibilities:

- Extract Java version
- Extract Spring Boot version
- Extract dependencies
- Generate pom-scan.json

---

## dependency_scanner.py

Runs Maven dependency tree analysis.

Responsibilities:

- Identify resolved dependencies
- Identify transitive dependencies
- Detect conflicts
- Generate dependency-scan.json

---

## dependency_researcher.py

Creates dependency research candidates.

Responsibilities:

- Build research queue
- Generate dependency-research.json

---

## compatibility_analyzer.py

Creates compatibility requirements.

Responsibilities:

- Validate Java compatibility
- Validate Spring Boot compatibility
- Generate compatibility-report.json

---

## migration_planner.py

Creates migration plans.

Responsibilities:

- Combine analysis reports
- Determine next action
- Generate migration-plan.json

---

## remediation_engine.py

Creates remediation decisions.

Responsibilities:

- Decide whether remediation is allowed
- Generate remediation-report.json

---

## branch_manager.py

Manages branch planning.

Responsibilities:

- Generate branch metadata
- Generate branch-report.json

---

## report_generator.py

Creates executive summary report.

Responsibilities:

- Aggregate all reports
- Generate final-agent-report.json

---

## notifier.py

Displays execution results.

Responsibilities:

- Read final report
- Print execution summary

---

## run_agent.py

Primary entry point.

Responsibilities:

- Execute all modules
- Control workflow
- Generate final execution summary