"""Generate consolidated executive report."""
import argparse, json
from datetime import datetime, timezone
from pathlib import Path
AGENT_ROOT=Path(__file__).resolve().parent
REPORTS_ROOT=AGENT_ROOT/'reports'
DEFAULT_OUTPUT=REPORTS_ROOT/'final-agent-report.json'

def load_json(name, required=True):
    p=REPORTS_ROOT/name
    if not p.exists():
        if required: raise FileNotFoundError('Required report was not found: {}'.format(p))
        return {}
    try: return json.loads(p.read_text(encoding='utf-8'))
    except json.JSONDecodeError as e: raise ValueError('Invalid JSON in {}: {}'.format(p,e))

def create_final_report():
    build=load_json('build-analysis.json'); pom=load_json('pom-scan.json')
    dep=load_json('dependency-scan.json'); research=load_json('dependency-research.json')
    compat=load_json('compatibility-report.json'); migration=load_json('migration-plan.json')
    remediation=load_json('remediation-report.json'); validation=load_json('validation-report.json',False)
    branch=load_json('branch-report.json',False); source=load_json('source-remediation-report.json',False)
    project=pom.get('project',{}); platform=pom.get('platform',{}); da=dep.get('analysis',{})
    mr=migration.get('research',{}); mc=migration.get('compatibility',{}); tests=validation.get('tests',{})
    coverage=validation.get('coverage',{}); sonar=validation.get('sonarCloud',{})
    candidate_count=mr.get('migrationCandidateCount',research.get('migrationCandidatesFound',0))
    compatible_count=mc.get('compatibleCandidateCount',compat.get('compatibleCandidateCount',0))
    failed=[]
    if build.get('buildStatus') not in ['SUCCESS','FAILED']: failed.append('build-analysis')
    if dep.get('scanStatus')!='SUCCESS': failed.append('dependency-scan')
    if validation and validation.get('validationStatus')!='SUCCESS': failed.append('validation')
    return {
      'agentStatus':'SUCCESS' if not failed else 'FAILED','generatedAt':datetime.now(timezone.utc).isoformat(),
      'project':{'groupId':project.get('groupId'),'artifactId':project.get('artifactId'),'version':project.get('version'),'coordinates':'{}:{}'.format(project.get('groupId'),project.get('artifactId'))},
      'build':{'status':build.get('buildStatus','UNKNOWN'),'classification':build.get('classification','unknown'),'confidence':build.get('confidence'),'actionable':build.get('actionable',False)},
      'platform':{'javaVersion':platform.get('javaVersion',{}).get('value'),'springBootVersion':platform.get('springBoot',{}).get('version'),'namespace':compat.get('platform',{}).get('namespace')},
      'dependencies':{'total':da.get('totalDependencies',0),'direct':da.get('directDependencyCount',0),'transitive':da.get('transitiveDependencyCount',0),'conflicts':da.get('conflictCount',0)},
      'research':{'status':research.get('researchStatus','UNKNOWN'),'completed':research.get('researchCompletedCount',0),'pending':research.get('researchPendingCount',0),'migrationCandidates':candidate_count,'internetResearchPerformed':research.get('internetResearchPerformed',False)},
      'compatibility':{'status':compat.get('analysisStatus','UNKNOWN'),'platformStatus':compat.get('platformStatus','UNKNOWN'),'compatibleCandidates':compatible_count,'allMigrationCandidatesCompatible':compat.get('allMigrationCandidatesCompatible',False),'automaticMigrationAllowed':compat.get('automaticMigrationAllowed',False)},
      'migration':{'planStatus':migration.get('planStatus','UNKNOWN'),'replacementGroupCount':len(migration.get('replacementGroups',[])),'remediationEligible':migration.get('remediationEligible',False),'automaticChangesAllowed':migration.get('automaticChangesAllowed',False),'branchCreationAllowed':migration.get('branchCreationAllowed',False),'nextStep':migration.get('nextStep')},
      'remediation':{'status':remediation.get('status','UNKNOWN'),'allowed':remediation.get('remediationAllowed',False),'plannedChangeCount':len(remediation.get('plannedChanges',[])),'affectedSourceFileCount':remediation.get('affectedSourceFileCount',0),'changesApplied':remediation.get('changesApplied',False)},
      'sourceRemediation':{'available':bool(source),'status':source.get('status','NOT_EXECUTED'),'dryRun':source.get('dryRun',True),'filesIdentified':source.get('filesIdentified',0),'filesWithPlannedChanges':source.get('filesWithPlannedChanges',0),'filesModified':source.get('filesModified',0),'plannedOperations':source.get('totalPlannedOperations',0),'manualReviewRequired':source.get('manualReviewRequired',False),'manualReviewFiles':source.get('manualReviewFiles',[]),'changesApplied':source.get('changesApplied',False)},
      'validation':{'available':bool(validation),'status':validation.get('validationStatus','NOT_EXECUTED'),'testsRun':tests.get('tests',0),'testFailures':tests.get('failures',0),'testErrors':tests.get('errors',0),'testsSkipped':tests.get('skipped',0),'testsSuccessful':validation.get('testsSuccessful',False),'coverageGenerated':coverage.get('reportFound',False),'sonarCloudStatus':sonar.get('status','NOT_EXECUTED'),'commitAllowed':validation.get('commitAllowed',False)},
      'branch':{'required':branch.get('branchRequired',False),'name':branch.get('branchName')},'failedComponents':failed,
      'summary':{'planStatus':migration.get('planStatus','UNKNOWN'),'migrationCandidateCount':candidate_count,'compatibleCandidateCount':compatible_count,'sourceFilesAffected':source.get('filesIdentified',0),'sourceFilesWithChanges':source.get('filesWithPlannedChanges',0),'manualReviewRequired':source.get('manualReviewRequired',False),'automaticChangesAllowed':migration.get('automaticChangesAllowed',False),'branchCreationAllowed':migration.get('branchCreationAllowed',False),'nextStep':migration.get('nextStep')}
    }

def main():
    p=argparse.ArgumentParser(); p.add_argument('--output',default=str(DEFAULT_OUTPUT)); a=p.parse_args()
    try:
        r=create_final_report(); out=Path(a.output).resolve(); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(r,indent=2),encoding='utf-8')
        print('='*60); print('FINAL AGENT REPORT'); print('='*60); print('Agent status        : {}'.format(r['agentStatus'])); print('Plan status         : {}'.format(r['summary']['planStatus'])); print('Migration candidates: {}'.format(r['summary']['migrationCandidateCount'])); print('Compatible          : {}'.format(r['summary']['compatibleCandidateCount'])); print('Source files affected: {}'.format(r['summary']['sourceFilesAffected'])); print('Manual review       : {}'.format(r['summary']['manualReviewRequired'])); print('Validation status   : {}'.format(r['validation']['status'])); print('Tests run           : {}'.format(r['validation']['testsRun'])); print('Coverage generated  : {}'.format(r['validation']['coverageGenerated'])); print('Report              : {}'.format(out)); return 0
    except (FileNotFoundError,ValueError) as e: print('ERROR: {}'.format(e)); return 2
    except Exception as e: print('Unexpected report generator error: {}'.format(e)); return 3
if __name__=='__main__': raise SystemExit(main())
