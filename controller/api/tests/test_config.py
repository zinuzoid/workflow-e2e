"""
Unit tests for the Deis api app.

Run the tests with "./manage.py test api"
"""

from __future__ import unicode_literals

import json
import mock
import requests

from django.test import TransactionTestCase
from django.test.utils import override_settings

from api.models import Config


def mock_import_repository_task(*args, **kwargs):
    resp = requests.Response()
    resp.status_code = 200
    resp._content_consumed = True
    return resp


@override_settings(CELERY_ALWAYS_EAGER=True)
class ConfigTest(TransactionTestCase):

    """Tests setting and updating config values"""

    fixtures = ['tests.json']

    def setUp(self):
        self.assertTrue(
            self.client.login(username='autotest', password='password'))
        body = {'id': 'autotest', 'domain': 'autotest.local', 'type': 'mock',
                'hosts': 'host1,host2', 'auth': 'base64string', 'options': {}}
        response = self.client.post('/api/clusters', json.dumps(body),
                                    content_type='application/json')
        self.assertEqual(response.status_code, 201)

    @mock.patch('requests.post', mock_import_repository_task)
    def test_config(self):
        """
        Test that config is auto-created for a new app and that
        config can be updated using a PATCH
        """
        url = '/api/apps'
        body = {'cluster': 'autotest'}
        response = self.client.post(url, json.dumps(body), content_type='application/json')
        self.assertEqual(response.status_code, 201)
        app_id = response.data['id']
        # check to see that an initial/empty config was created
        url = "/api/apps/{app_id}/config".format(**locals())
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn('values', response.data)
        self.assertEqual(response.data['values'], json.dumps({}))
        config1 = response.data
        # set an initial config value
        body = {'values': json.dumps({'NEW_URL1': 'http://localhost:8080/'})}
        response = self.client.post(url, json.dumps(body), content_type='application/json')
        self.assertEqual(response.status_code, 201)
        self.assertIn('x-deis-release', response._headers)
        config2 = response.data
        self.assertNotEqual(config1['uuid'], config2['uuid'])
        self.assertIn('NEW_URL1', json.loads(response.data['values']))
        # read the config
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        config3 = response.data
        self.assertEqual(config2, config3)
        self.assertIn('NEW_URL1', json.loads(response.data['values']))
        # set an additional config value
        body = {'values': json.dumps({'NEW_URL2': 'http://localhost:8080/'})}
        response = self.client.post(url, json.dumps(body), content_type='application/json')
        self.assertEqual(response.status_code, 201)
        config3 = response.data
        self.assertNotEqual(config2['uuid'], config3['uuid'])
        self.assertIn('NEW_URL1', json.loads(response.data['values']))
        self.assertIn('NEW_URL2', json.loads(response.data['values']))
        # read the config again
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        config4 = response.data
        self.assertEqual(config3, config4)
        self.assertIn('NEW_URL1', json.loads(response.data['values']))
        self.assertIn('NEW_URL2', json.loads(response.data['values']))
        # unset a config value
        body = {'values': json.dumps({'NEW_URL2': None})}
        response = self.client.post(url, json.dumps(body), content_type='application/json')
        self.assertEqual(response.status_code, 201)
        config5 = response.data
        self.assertNotEqual(config4['uuid'], config5['uuid'])
        self.assertNotIn('NEW_URL2', json.dumps(response.data['values']))
        # unset all config values
        body = {'values': json.dumps({'NEW_URL1': None})}
        response = self.client.post(url, json.dumps(body), content_type='application/json')
        self.assertEqual(response.status_code, 201)
        self.assertNotIn('NEW_URL1', json.dumps(response.data['values']))
        # disallow put/patch/delete
        self.assertEqual(self.client.put(url).status_code, 405)
        self.assertEqual(self.client.patch(url).status_code, 405)
        self.assertEqual(self.client.delete(url).status_code, 405)
        return config5

    @mock.patch('requests.post', mock_import_repository_task)
    def test_config_set_same_key(self):
        """
        Test that config sets on the same key function properly
        """
        url = '/api/apps'
        body = {'cluster': 'autotest'}
        response = self.client.post(url, json.dumps(body), content_type='application/json')
        self.assertEqual(response.status_code, 201)
        app_id = response.data['id']
        url = "/api/apps/{app_id}/config".format(**locals())
        # set an initial config value
        body = {'values': json.dumps({'PORT': '5000'})}
        response = self.client.post(url, json.dumps(body), content_type='application/json')
        self.assertEqual(response.status_code, 201)
        self.assertIn('PORT', json.loads(response.data['values']))
        # reset same config value
        body = {'values': json.dumps({'PORT': '5001'})}
        response = self.client.post(url, json.dumps(body), content_type='application/json')
        self.assertEqual(response.status_code, 201)
        self.assertIn('PORT', json.loads(response.data['values']))
        self.assertEqual(json.loads(response.data['values'])['PORT'], '5001')

    @mock.patch('requests.post', mock_import_repository_task)
    def test_config_str(self):
        """Test the text representation of a node."""
        config5 = self.test_config()
        config = Config.objects.get(uuid=config5['uuid'])
        self.assertEqual(str(config), "{}-{}".format(config5['app'], config5['uuid'][:7]))

    @mock.patch('requests.post', mock_import_repository_task)
    def test_limit_memory(self):
        """
        Test that limit is auto-created for a new app and that
        limits can be updated using a PATCH
        """
        url = '/api/apps'
        body = {'cluster': 'autotest'}
        response = self.client.post(url, json.dumps(body), content_type='application/json')
        self.assertEqual(response.status_code, 201)
        app_id = response.data['id']
        url = '/api/apps/{app_id}/config'.format(**locals())
        # check default limit
        response = self.client.get(url, content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertIn('memory', response.data)
        self.assertEqual(json.loads(response.data['memory']), {})
        # regression test for https://github.com/deis/deis/issues/1563
        self.assertNotIn('"', response.data['memory'])
        # set an initial limit
        mem = {'web': '1G'}
        body = {'memory': json.dumps(mem)}
        response = self.client.post(url, json.dumps(body), content_type='application/json')
        self.assertEqual(response.status_code, 201)
        self.assertIn('x-deis-release', response._headers)
        limit1 = response.data
        # check memory limits
        response = self.client.get(url, content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertIn('memory', response.data)
        memory = json.loads(response.data['memory'])
        self.assertIn('web', memory)
        self.assertEqual(memory['web'], '1G')
        # set an additional value
        body = {'memory': json.dumps({'worker': '512M'})}
        response = self.client.post(url, json.dumps(body), content_type='application/json')
        self.assertEqual(response.status_code, 201)
        limit2 = response.data
        self.assertNotEqual(limit1['uuid'], limit2['uuid'])
        memory = json.loads(response.data['memory'])
        self.assertIn('worker', memory)
        self.assertEqual(memory['worker'], '512M')
        self.assertIn('web', memory)
        self.assertEqual(memory['web'], '1G')
        # read the limit again
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        limit3 = response.data
        self.assertEqual(limit2, limit3)
        memory = json.loads(response.data['memory'])
        self.assertIn('worker', memory)
        self.assertEqual(memory['worker'], '512M')
        self.assertIn('web', memory)
        self.assertEqual(memory['web'], '1G')
        # regression test for https://github.com/deis/deis/issues/1613
        # ensure that config:set doesn't wipe out previous limits
        body = {'values': json.dumps({'NEW_URL2': 'http://localhost:8080/'})}
        response = self.client.post(url, json.dumps(body), content_type='application/json')
        self.assertEqual(response.status_code, 201)
        self.assertIn('NEW_URL2', json.loads(response.data['values']))
        # read the limit again
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        memory = json.loads(response.data['memory'])
        self.assertIn('worker', memory)
        self.assertEqual(memory['worker'], '512M')
        self.assertIn('web', memory)
        self.assertEqual(memory['web'], '1G')
        # unset a value
        body = {'memory': json.dumps({'worker': None})}
        response = self.client.post(url, json.dumps(body), content_type='application/json')
        self.assertEqual(response.status_code, 201)
        limit4 = response.data
        self.assertNotEqual(limit3['uuid'], limit4['uuid'])
        self.assertNotIn('worker', json.dumps(response.data['memory']))
        # disallow put/patch/delete
        self.assertEqual(self.client.put(url).status_code, 405)
        self.assertEqual(self.client.patch(url).status_code, 405)
        self.assertEqual(self.client.delete(url).status_code, 405)
        return limit4

    @mock.patch('requests.post', mock_import_repository_task)
    def test_limit_cpu(self):
        """
        Test that CPU limits can be set
        """
        url = '/api/apps'
        body = {'cluster': 'autotest'}
        response = self.client.post(url, json.dumps(body), content_type='application/json')
        self.assertEqual(response.status_code, 201)
        app_id = response.data['id']
        url = '/api/apps/{app_id}/config'.format(**locals())
        # check default limit
        response = self.client.get(url, content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertIn('cpu', response.data)
        self.assertEqual(json.loads(response.data['cpu']), {})
        # regression test for https://github.com/deis/deis/issues/1563
        self.assertNotIn('"', response.data['cpu'])
        # set an initial limit
        body = {'cpu': json.dumps({'web': '1024'})}
        response = self.client.post(url, json.dumps(body), content_type='application/json')
        self.assertEqual(response.status_code, 201)
        self.assertIn('x-deis-release', response._headers)
        limit1 = response.data
        # check memory limits
        response = self.client.get(url, content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertIn('cpu', response.data)
        cpu = json.loads(response.data['cpu'])
        self.assertIn('web', cpu)
        self.assertEqual(cpu['web'], '1024')
        # set an additional value
        body = {'cpu': json.dumps({'worker': '512'})}
        response = self.client.post(url, json.dumps(body), content_type='application/json')
        self.assertEqual(response.status_code, 201)
        limit2 = response.data
        self.assertNotEqual(limit1['uuid'], limit2['uuid'])
        cpu = json.loads(response.data['cpu'])
        self.assertIn('worker', cpu)
        self.assertEqual(cpu['worker'], '512')
        self.assertIn('web', cpu)
        self.assertEqual(cpu['web'], '1024')
        # read the limit again
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        limit3 = response.data
        self.assertEqual(limit2, limit3)
        cpu = json.loads(response.data['cpu'])
        self.assertIn('worker', cpu)
        self.assertEqual(cpu['worker'], '512')
        self.assertIn('web', cpu)
        self.assertEqual(cpu['web'], '1024')
        # unset a value
        body = {'memory': json.dumps({'worker': None})}
        response = self.client.post(url, json.dumps(body), content_type='application/json')
        self.assertEqual(response.status_code, 201)
        limit4 = response.data
        self.assertNotEqual(limit3['uuid'], limit4['uuid'])
        self.assertNotIn('worker', json.dumps(response.data['memory']))
        # disallow put/patch/delete
        self.assertEqual(self.client.put(url).status_code, 405)
        self.assertEqual(self.client.patch(url).status_code, 405)
        self.assertEqual(self.client.delete(url).status_code, 405)
        return limit4
