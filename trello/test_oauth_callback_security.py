"""Synthetic loopback regressions; no Trello request or credential-store access."""
import argparse
import http.client
import importlib.util
import json
from pathlib import Path
import secrets
import threading
import unittest
from urllib.parse import urlencode

SOURCE = Path(__file__).with_name('oauth_connect.py')


class CallbackStateTests(unittest.TestCase):
    def setUp(self):
        spec=importlib.util.spec_from_file_location('trello_oauth_under_review',SOURCE)
        self.module=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.module)
        self.server=self.module.ConnectServer(('127.0.0.1',0),self.module.ConnectHandler)
        self.server.state=secrets.token_urlsafe(32)
        self.worker=threading.Thread(target=self.server.serve_forever,daemon=True);self.worker.start()

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.worker.join(timeout=3)
        self.assertFalse(self.worker.is_alive())

    def request(self,method,path,body=None):
        connection=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=3)
        try:
            connection.request(method,path,body=body,headers={'Content-Type':'application/json'} if body is not None else {})
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


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--source',type=Path,default=SOURCE);parser.add_argument('--report',type=Path,required=True);args=parser.parse_args();SOURCE=args.source.resolve()
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(CallbackStateTests))
    args.report.write_text(json.dumps({'testsRun':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),'success':result.wasSuccessful()},indent=2)+'\n')
    raise SystemExit(0 if result.wasSuccessful() else 1)
