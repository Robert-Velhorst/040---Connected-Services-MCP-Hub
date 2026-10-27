"""Synthetic loopback regressions; no Trello request or credential-store access."""
import argparse
import http.client
import importlib.util
import json
import os
import tempfile
from unittest.mock import patch
from pathlib import Path
import secrets
import threading
import unittest
from urllib.parse import urlencode

# The image mounts tests separately from the installed application. Resolve the
# real application module through the same import path as the original cases.
installed_spec = importlib.util.find_spec('oauth_connect')
if installed_spec is None or installed_spec.origin is None:
    raise RuntimeError('The installed OAuth consent module is unavailable')
SOURCE = Path(installed_spec.origin)


class CallbackStateTests(unittest.TestCase):
    def setUp(self):
        spec=importlib.util.spec_from_file_location('trello_oauth_under_review',SOURCE)
        self.module=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.module)
        self.temporary=tempfile.TemporaryDirectory(prefix='trello-oauth-boundary-')
        self.settings=Path(self.temporary.name)/'settings.json'
        self.environment=patch.dict(os.environ,{'TRELLO_MCP_SETTINGS_FILE':str(self.settings)})
        self.environment.start()
        self.server=self.module.ConnectServer(('127.0.0.1',0),self.module.ConnectHandler)
        self.server.state=secrets.token_urlsafe(32)
        self.worker=threading.Thread(target=self.server.serve_forever,daemon=True);self.worker.start()

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.worker.join(timeout=3)
        self.assertFalse(self.worker.is_alive())
        self.environment.stop();self.temporary.cleanup()

    def request(self,method,path,body=None,headers=None):
        connection=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=3)
        request_headers={'Content-Type':'application/json'} if body is not None else {}
        if method=='POST':request_headers['Origin']=f'http://127.0.0.1:{self.server.server_port}'
        request_headers.update(headers or {})
        request_headers={key:value for key,value in request_headers.items() if value is not None}
        try:
            connection.request(method,path,body=body,headers=request_headers)
            response=connection.getresponse();return response.status,dict(response.getheaders()),response.read().decode()
        finally:connection.close()

    def callback(self,state):
        return self.request('GET','/callback?'+urlencode({'state':state}))

    def test_callback_without_pending_consent_is_rejected(self):
        self.server.state=None
        status,_,_=self.callback('unsolicited')
        self.assertEqual(status,400)

    def test_callback_cannot_reflect_a_script_end_tag(self):
        payload='</script><script>globalThis.syntheticInjection=true</script>'
        status,headers,body=self.callback(payload)
        self.assertEqual(status,400)
        self.assertTrue(headers['Content-Type'].startswith('text/plain'))
        self.assertNotIn(payload,body)
        self.assertNotIn('<script',body.lower())

    def test_callback_with_wrong_nonce_is_rejected(self):
        status,_,_=self.callback('different-nonce')
        self.assertEqual(status,400)

    def test_unicode_callback_state_is_rejected_cleanly(self):
        status,_,_=self.callback('\u2603')
        self.assertEqual(status,400)

    def test_matching_callback_keeps_fragment_completion_flow(self):
        expected=self.server.state
        status,headers,body=self.callback(expected)
        self.assertEqual(status,200)
        self.assertTrue(headers['Content-Type'].startswith('text/html'))
        self.assertIn('const state = '+json.dumps(expected)+';',body)
        self.assertIn('location.hash.slice(1)',body)
        self.assertIn('fetch("/complete"',body)

    def test_wrong_completion_state_is_rejected_before_credentials(self):
        status,_,body=self.request('POST','/complete',json.dumps({'token':'synthetic-token','state':'different-nonce'}))
        self.assertEqual(status,400)
        self.assertEqual(json.loads(body),{'error':'Authorization state did not match.'})

    def test_unicode_completion_state_is_rejected_cleanly(self):
        status,_,body=self.request('POST','/complete',json.dumps({'token':'synthetic-token','state':'\u2603'}))
        self.assertEqual(status,400)
        self.assertEqual(json.loads(body),{'error':'Authorization state did not match.'})


    def test_external_host_is_rejected(self):
        status,_,_=self.request('GET','/setup',headers={'Host':f'rebinding.example:{self.server.server_port}'})
        self.assertEqual(status,403)

    def raw_get(self,hosts):
        connection=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=3)
        try:
            connection.putrequest('GET','/setup',skip_host=True)
            for host in hosts:connection.putheader('Host',host)
            connection.endheaders();response=connection.getresponse();response.read();return response.status
        finally:connection.close()

    def test_duplicate_host_is_rejected(self):
        host=f'127.0.0.1:{self.server.server_port}'
        self.assertEqual(self.raw_get([host,'rebinding.example']),403)

    def test_missing_host_is_rejected(self):
        self.assertEqual(self.raw_get([]),403)

    def test_external_get_origin_is_rejected(self):
        status,_,_=self.request('GET','/setup',headers={'Origin':'https://external.example'})
        self.assertEqual(status,403)

    def test_cross_site_setup_cannot_write_settings(self):
        status,_,_=self.request('POST','/setup','app_key=synthetic-public-key',{'Content-Type':'application/x-www-form-urlencoded','Origin':'https://external.example'})
        self.assertEqual(status,403);self.assertFalse(self.settings.exists())

    def test_setup_without_origin_is_rejected(self):
        status,_,_=self.request('POST','/setup','app_key=synthetic-public-key',{'Content-Type':'application/x-www-form-urlencoded','Origin':None})
        self.assertEqual(status,403);self.assertFalse(self.settings.exists())

    def test_null_origin_is_rejected(self):
        status,_,_=self.request('POST','/setup','app_key=synthetic-public-key',{'Content-Type':'application/x-www-form-urlencoded','Origin':'null'})
        self.assertEqual(status,403);self.assertFalse(self.settings.exists())

    def test_completion_rejects_form_content_type(self):
        status,_,_=self.request('POST','/complete',json.dumps({'token':'synthetic-token','state':'wrong'}),{'Content-Type':'application/x-www-form-urlencoded'})
        self.assertEqual(status,415)

    def test_oversized_body_is_rejected_before_parsing(self):
        body=json.dumps({'token':'x'*5000,'state':'wrong'})
        status,_,_=self.request('POST','/complete',body)
        self.assertEqual(status,413)

    def test_invalid_content_length_is_rejected_cleanly(self):
        status,_,_=self.request('POST','/complete','{}',{'Content-Length':'invalid'})
        self.assertEqual(status,400)

    def test_same_origin_setup_keeps_public_key_flow(self):
        status,headers,_=self.request('POST','/setup','app_key=synthetic-public-key',{'Content-Type':'application/x-www-form-urlencoded'})
        self.assertEqual(status,302);self.assertEqual(headers['Location'],'/connect')
        self.assertEqual(json.loads(self.settings.read_text()),{'trello_app_key':'synthetic-public-key'})

    def test_chunked_body_is_rejected(self):
        status,_,_=self.request('POST','/complete','{}',{'Transfer-Encoding':'chunked'})
        self.assertEqual(status,400)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--source',type=Path,default=SOURCE);parser.add_argument('--report',type=Path,required=True);args=parser.parse_args();SOURCE=args.source.resolve()
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(CallbackStateTests))
    args.report.write_text(json.dumps({'testsRun':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),'success':result.wasSuccessful()},indent=2)+'\n')
    raise SystemExit(0 if result.wasSuccessful() else 1)
