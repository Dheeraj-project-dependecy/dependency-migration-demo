"""Print console notification from final-agent-report.json."""
import json
from pathlib import Path
AGENT_ROOT=Path(__file__).resolve().parent; REPORT_FILE=AGENT_ROOT/'reports'/'final-agent-report.json'
def load_report():
    if not REPORT_FILE.exists(): raise FileNotFoundError('Final agent report not found: {}'.format(REPORT_FILE))
    return json.loads(REPORT_FILE.read_text(encoding='utf-8'))
def message(r):
    if r.get('build',{}).get('status')=='SUCCESS': return 'The Maven build is healthy. Analysis and baseline validation completed successfully, so no remediation is required.'
    if r.get('validation',{}).get('status') not in ['SUCCESS','NOT_EXECUTED']: return 'Validation failed. Inspect validation logs and do not commit or push changes.'
    if r.get('migration',{}).get('automaticChangesAllowed'): return 'A dependency-related failure was confirmed and policy permits automatic remediation.'
    return 'The agent completed analysis, but no automatic remediation action is currently permitted.'
def main():
    try:
        r=load_report(); p=r.get('project',{}); b=r.get('build',{}); pf=r.get('platform',{}); d=r.get('dependencies',{}); rs=r.get('research',{}); c=r.get('compatibility',{}); m=r.get('migration',{}); rm=r.get('remediation',{}); sr=r.get('sourceRemediation',{}); v=r.get('validation',{}); br=r.get('branch',{})
        print('='*60); print('DEPENDENCY MIGRATION AGENT NOTIFICATION'); print('='*60)
        values=[('Agent status',r.get('agentStatus','UNKNOWN')),('Generated at',r.get('generatedAt','UNKNOWN')),('Project',p.get('coordinates','UNKNOWN')),('Project version',p.get('version','UNKNOWN')),('Build status',b.get('status','UNKNOWN')),('Build classification',b.get('classification','unknown')),('Plan status',m.get('planStatus','UNKNOWN')),('Java version',pf.get('javaVersion','UNKNOWN')),('Spring Boot version',pf.get('springBootVersion','UNKNOWN')),('Namespace',pf.get('namespace','UNKNOWN')),('Dependencies',d.get('total',0)),('Migration candidates',rs.get('migrationCandidates',0)),('Compatible',c.get('compatibleCandidates',0)),('Remediation status',rm.get('status','UNKNOWN')),('Planned changes',rm.get('plannedChangeCount',0)),('Source remediation',sr.get('status','NOT_EXECUTED')),('Source files affected',sr.get('filesIdentified',0)),('Files with changes',sr.get('filesWithPlannedChanges',0)),('Planned source ops',sr.get('plannedOperations',0)),('Manual review needed',sr.get('manualReviewRequired',False)),('Source changes applied',sr.get('changesApplied',False)),('Validation status',v.get('status','NOT_EXECUTED')),('Tests run',v.get('testsRun',0)),('Test failures',v.get('testFailures',0)),('Coverage generated',v.get('coverageGenerated',False)),('SonarCloud',v.get('sonarCloudStatus','NOT_EXECUTED')),('Automatic changes',m.get('automaticChangesAllowed',False)),('Branch creation',m.get('branchCreationAllowed',False)),('Branch required',br.get('required',False)),('Branch name',br.get('name')),('Commit allowed',v.get('commitAllowed',False)),('Next step',m.get('nextStep','No next step was provided.'))]
        for key,val in values: print('{:<20}: {}'.format(key,val))
        print('-'*60); print('Notification        : {}'.format(message(r))); print('='*60); return 0
    except (FileNotFoundError,ValueError,json.JSONDecodeError) as e: print('NOTIFIER ERROR: {}'.format(e)); return 2
    except Exception as e: print('Unexpected notifier error: {}'.format(e)); return 3
if __name__=='__main__': raise SystemExit(main())
