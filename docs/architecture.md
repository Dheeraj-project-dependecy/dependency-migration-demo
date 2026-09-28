# Architecture

## Overview

The Self-Healing Legacy Dependency Migration Agent is a modular framework that analyzes Maven-based Java applications and generates migration recommendations.

## Component Architecture

run_agent.py
    ↓
build_analyzer.py
    ↓
pom_scanner.py
    ↓
dependency_scanner.py
    ↓
dependency_researcher.py
    ↓
compatibility_analyzer.py
    ↓
migration_planner.py
    ↓
remediation_engine.py
    ↓
branch_manager.py
    ↓
report_generator.py
    ↓
notifier.py

## Layers

### Analysis Layer

- build_analyzer.py
- pom_scanner.py
- dependency_scanner.py
- dependency_researcher.py
- compatibility_analyzer.py

### Planning Layer

- migration_planner.py

### Remediation Layer

- remediation_engine.py
- branch_manager.py

### Reporting Layer

- report_generator.py
- notifier.py

### Orchestration Layer

- run_agent.py