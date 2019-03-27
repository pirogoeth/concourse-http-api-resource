import json
import subprocess

import pytest

from helpers import cmd


def test_out(httpbin):
    """Test out action with minimal input."""

    data = {
        'source': {
            'uri': httpbin + '/status/200',
        },
        'version': {}
    }
    subprocess.check_output(
        ['/opt/resource/out', '/opt/resource-tests'],
        input=json.dumps(data).encode(),
    )


def test_out_failure(httpbin):
    """Test action failing if not OK http response."""

    data = {
        'source': {
            'uri': httpbin + '/status/404',
        },
        'version': {}
    }
    with pytest.raises(subprocess.CalledProcessError):
        subprocess.check_output(
            ['/opt/resource/out', '/opt/resource-tests'],
            input=json.dumps(data).encode(),
        )


def test_auth(httpbin):
    """Test basic authentication."""

    data = {
        'source': {
            'uri': 'http://user:password@{0.host}:{0.port}/basic-auth/user/password'.format(httpbin),
        },
    }
    subprocess.check_output(
        ['/opt/resource/out', '/opt/resource-tests'],
        input=json.dumps(data).encode(),
    )


def test_json(httpbin):
    """Json should be passed as JSON content."""

    source = {
        'uri': httpbin + '/post',
        'method': 'POST',
        'json': {
            'test': 123,
        },
        'version': {}
    }

    output = cmd('out', source, args=["/opt/resource-tests"])

    assert output['json']['test'] == 123
    assert output['version'] == {}


def test_interpolation(httpbin):
    """Values should be interpolated recursively."""

    source = {
        'uri': httpbin + '/post',
        'method': 'POST',
        'json': {
            'object': {
                'test': '{BUILD_NAME}'
            },
            'array': [
                '{BUILD_NAME}'
            ]
        }
    }

    output = cmd('out', source, args=["/opt/resource-tests"])

    assert output['json']['object']['test'] == '1'
    assert output['json']['array'][0] == '1'
    assert output['version'] == {}


def test_empty_check(httpbin):
    """Check must return an empty response but not nothing."""

    source = {
        'uri': httpbin + '/post',
        'method': 'POST',
    }

    check = cmd('check', source, args=["/opt/resource-tests"])

    assert check == []


def test_data_urlencode(httpbin):
    """Test passing URL encoded data."""

    source = {
        'uri': httpbin + '/post',
        'method': 'POST',
        'form_data': {
            'field': {
                'test': 123,
            },
        }
    }

    output = cmd('out', source, args=["/opt/resource-tests"])

    assert output['form'] == {'field': '{"test": 123}'}
    assert output['version'] == {}


def test_data_ensure_ascii(httpbin):
    """Test form_data json ensure_ascii."""

    source = {
        'uri': httpbin + '/post',
        'method': 'POST',
        'form_data': {
            'field': {
                'test': '日本語',
            },
        },
    }

    output = cmd('out', source, args=["/opt/resource-tests"])

    assert output['form'] == {'field': '{"test": "日本語"}'}


def test_params_file_inject(httpbin):
    """ Ensure that file content gets injected to param
    """

    source = {
        "uri": httpbin + "/post",
        "method": "POST",
        "form_data": {
            "triggered_by": {
                "commit_sha": "@data/id.txt",
            },
        },
    }

    output = cmd("out", source, args=["/opt/resource-tests"])

    assert output["form"] == {"triggered_by": '{"commit_sha": "aebe128"}'}


def test_params_file_inject_trim(httpbin):
    """ Ensure that file content gets trimmed and injected to param
    """

    source = {
        "uri": httpbin + "/post",
        "method": "POST",
        "form_data": {
            "triggered_by": {
                "commit_sha": "-@data/padded.txt",
            },
        },
    }

    output = cmd("out", source, args=["/opt/resource-tests"])

    assert output["form"] == {"triggered_by": '{"commit_sha": "cafe430"}'}
