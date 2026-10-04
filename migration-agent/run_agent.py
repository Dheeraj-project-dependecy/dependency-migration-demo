"""Orchestrate migration agent pipeline."""
import json, subprocess, sys
from pathlib import Path
AGENT_ROOT=Path(__file__).resolve().parent; PROJECT_ROOT=AGENT_ROOT.parent; REPORTS_ROOT=AGENT_ROOT/'reports'; POLICY_FILE=AGENT_ROOT/'policy.json'
STEPS=[
{'name':'Build Analysis','script':'build_analyzer.py','arguments':['--build-log',str(REPORTS_ROOT/'maven-build.log')]},
{'name':'POM Scanner','script':'pom_scanner.py','arguments':['--pom',str(PROJECT_ROOT/'pom.xml')]},
{'name':'Dependency Scanner','script':'dependency_scanner.py','arguments':['--project-root',str(PROJECT_ROOT)]},
{'name':'Dependency Research','script':'dependency_researcher.py','arguments':[]},
{'name':'Compatibility Analyzer','script':'compatibility_analyzer.py','arguments':[]},
{'name':'Migration Planner','script':'migration_planner.py','arguments':[]},
{'name':'Remediation Engine','script':'remediation_engine.py','arguments':[]},
{'name':'Source Remediator','script':'source_remediator.py','arguments':['--dry-run']},
{'name':'Validation Engine','script':'validation_engine.py','arguments':[]},
{'name':'Branch Manager','script':'branch_manager.py','arguments':[]},
{'name':'Report Generator','script':'report_generator.py','arguments':[]},
{'name':'Notifier','script':'notifier.py','arguments':[]}]
def load(name):
 p=REPORTS_ROOT/name
 try:return json.loads(p.read_text(encoding='utf-8')) if p.exists() else {}
 except json.JSONDecodeError:return {}
def policy(): return json.loads(POLICY_FILE.read_text(encoding='utf-8'))
def execute(i,n,s):
 print(); print('-'*60); print('[{}/{}] {}'.format(i,n,s['name'])); print('-'*60)
 p=AGENT_ROOT/s['script']
 if not p.exists(): return {'name':s['name'],'status':'FAILED','exitCode':2}
 result=subprocess.run([sys.executable,str(p)]+s.get('arguments',[]),cwd=str(PROJECT_ROOT),shell=False)
 status='SUCCESS' if result.returncode==0 else 'FAILED'; print(); print('{}: {}'.format(status,s['name'])); return {'name':s['name'],'status':status,'exitCode':result.returncode}
def summary(results,p):
 mp=load('migration-plan.json'); rr=load('remediation-report.json'); sr=load('source-remediation-report.json'); vr=load('validation-report.json'); br=load('branch-report.json'); fr=load('final-agent-report.json'); fs=fr.get('summary',{}); fv=fr.get('validation',{})
 ok=sum(x['status']=='SUCCESS' for x in results); failed=len(results)-ok
 print(); print('='*60); print('AGENT EXECUTION SUMMARY'); print('='*60)
 values=[('Agent version',p.get('version')),('Execution mode',p.get('executionMode')),('Successful steps',ok),('Failed steps',failed),('Plan status',mp.get('planStatus','UNKNOWN')),('Automatic changes',mp.get('automaticChangesAllowed',False)),('Branch creation',mp.get('branchCreationAllowed',False)),('Migration candidates',mp.get('research',{}).get('migrationCandidateCount',fs.get('migrationCandidateCount',0))),('Remediation status',rr.get('status','UNKNOWN')),('Source remediation',sr.get('status','NOT_EXECUTED')),('Source files affected',sr.get('filesIdentified',0)),('Files with changes',sr.get('filesWithPlannedChanges',0)),('Manual review needed',sr.get('manualReviewRequired',False)),('Validation status',vr.get('validationStatus',fv.get('status','NOT_EXECUTED'))),('Tests run',vr.get('tests',{}).get('tests',fv.get('testsRun',0))),('Coverage generated',vr.get('coverage',{}).get('reportFound',fv.get('coverageGenerated',False))),('Branch required',br.get('branchRequired',False)),('Branch name',br.get('branchName')),('Final agent status',fr.get('agentStatus','UNKNOWN')),('Final next step',fs.get('nextStep',mp.get('nextStep','None'))),('Reports directory',REPORTS_ROOT)]
 for k,v in values: print('{:<20}: {}'.format(k,v))
def main():
 try:p=policy()
 except Exception as e: print('Unable to load policy: {}'.format(e)); return 2
 print('='*60); print(p.get('agentName','DEPENDENCY MIGRATION AGENT').upper()); print('='*60); print('Agent version       : {}'.format(p.get('version'))); print('Execution mode      : {}'.format(p.get('executionMode'))); print('Project root        : {}'.format(PROJECT_ROOT))
 results=[]
 for i,s in enumerate(STEPS,1):
  r=execute(i,len(STEPS),s); results.append(r)
  if r['status']=='FAILED': print('AGENT PIPELINE STOPPED'); summary(results,p); return r['exitCode'] or 1
 print(); print('='*60); print('AGENT EXECUTION COMPLETE'); print('='*60); summary(results,p); return 0
if __name__=='__main__': raise SystemExit(main())
