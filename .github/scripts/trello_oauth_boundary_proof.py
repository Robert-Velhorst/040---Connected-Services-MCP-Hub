"""Counterfactual source proof on an owned GitHub-hosted synthetic loopback."""
import hashlib,json,os,pathlib,platform,subprocess,sys
assert os.environ.get('GITHUB_ACTIONS')=='true'
assert os.environ.get('GITHUB_REPOSITORY')=='Robert-Velhorst/040---Connected-Services-MCP-Hub'
assert os.environ.get('RUNNER_ENVIRONMENT')=='github-hosted'
assert platform.python_version()=='3.15.2'
root=pathlib.Path(__file__).resolve().parents[2];out=root/'OAUTH_BOUNDARY_EVIDENCE';out.mkdir(exist_ok=True)
base='04bd754a1f668b65893ab0cf61886b10035697b1'
def git(*args):return subprocess.check_output(['git','-C',str(root),*args])
def source_identity():
    payloads={}
    for row in git('ls-tree','-rz','HEAD').split(b'\0'):
        if not row:continue
        left,name=row.split(b'\t');mode,kind,blob=left.decode().split();assert kind=='blob'
        path=root/os.fsdecode(name);data=os.readlink(path).encode() if mode=='120000' else path.read_bytes()
        assert hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()==blob
        payloads[os.fsdecode(name)]={'mode':mode,'blob':blob,'sha256':hashlib.sha256(data).hexdigest()}
    return {'head':git('rev-parse','HEAD').decode().strip(),'tree':git('rev-parse','HEAD^{tree}').decode().strip(),'payloads':payloads}
before=source_identity();(out/'source-before.json').write_text(json.dumps(before,indent=2)+'\n')
record={'SDK_python':platform.python_version(),'original_cases_edited':False,'real_Trello_or_credential_store_acceptance':False,'actual_operator_data_used':False,'deployment':False}
try:
    original=git('show',base+':trello/oauth_connect.py');original_path=out/'original-oauth_connect.py';original_path.write_bytes(original)
    record['original_source_sha256']=hashlib.sha256(original).hexdigest()
    for stage,source in [('original',original_path),('patched',root/'trello/oauth_connect.py')]:
        report=out/(stage+'-cases.json');result=subprocess.run([sys.executable,'-B',str(root/'trello/test_oauth_callback_security.py'),'--source',str(source),'--report',str(report)],cwd=root/'trello',capture_output=True,text=True,timeout=120)
        (out/(stage+'-cases.log')).write_text(result.stdout+result.stderr);observed=json.loads(report.read_text());record[stage]=observed
        assert observed['testsRun']==19 and observed['skipped']==0
        if stage=='original':assert result.returncode!=0 and observed['failures']==13 and observed['errors']==2
        else:assert result.returncode==0 and observed['success']
    original_cases={}
    for name in git('ls-tree','-r','--name-only',base,'trello').decode().splitlines():
        if pathlib.PurePosixPath(name).name.startswith('test_'):
            original_cases[name]=hashlib.sha256(git('show',base+':'+name)).hexdigest()
            assert hashlib.sha256((root/name).read_bytes()).hexdigest()==original_cases[name]
    assert len(original_cases)==8;record['original_case_file_hashes']=original_cases
    result=subprocess.run([sys.executable,'-m','pytest','-q'],cwd=root/'trello',capture_output=True,text=True,timeout=180)
    (out/'complete-current-pytest.log').write_text(result.stdout+result.stderr);record['all_source_pytest_exit_code']=result.returncode
    assert result.returncode==0,result.stdout+result.stderr
    record['source_boundary_component_acceptance']=True
except BaseException as error:
    record['failure']=repr(error);record['source_boundary_component_acceptance']=False
    raise
finally:
    after=source_identity();(out/'source-after.json').write_text(json.dumps(after,indent=2)+'\n');record['all_tracked_payloads_unchanged']=before==after
    (out/'receipt.json').write_text(json.dumps(record,indent=2)+'\n');assert before==after
    print(json.dumps({'component_acceptance':record.get('source_boundary_component_acceptance'),'failure':record.get('failure')}))
