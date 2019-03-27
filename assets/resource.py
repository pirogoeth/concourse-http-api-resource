#!/usr/bin/env python3

import io
import json
import logging as log
import os
import sys
import tempfile
import typing

import requests


class FileReference(object):
    """ FileReference is created to represent a file reference
        inside of a resource parameter.

        "@path/to/file" is a reference to a file which is returned, verbatim.
        "-@path/to/file" is a reference to a file which will have it's contents
            `strip()`'d before being inserted.
    """

    path: str = None
    strip: bool = False

    class Unparseable(Exception):
        """ Unparseable exception is thrown when the file reference
            can not be parsed.
        """

        def __init__(self, value):
            self.value = value

        def __str__(self):
            return f"Could not parse file path out of value `{self.value}`"

        def __repr__(self):
            return str(self)

    @classmethod
    def parse(cls, value: str, **kw) -> "FileReference":
        path = None
        strip = False

        if value.startswith("@"):
            path = value[1:]
        elif value.startswith("-@"):
            path = value[2:]
            strip = True
        else:
            raise FileReference.Unparseable(value)

        return cls(path, strip=strip, **kw)

    def __init__(self, path, strip=False, bounding_path=None):
        self.path = path
        self.strip = strip
        self.bound = bounding_path

    @property
    def target_path(self):
        """ Return the path that will be opened with the provided `bound`
        """

        return self.resolve_path(bound=self.bound)

    @property
    def contents(self):
        """ Return the internal contents
        """

        with io.open(self.target_path, "r") as resource:
            data = resource.read()
            return data if not self.strip else data.strip()

    def resolve_path(self, bound=None):
        """ Normalize/expand/resolve the internal path such that
            the result will not be outside of the tree bounded
            by `bound`.
        """

        if bound is None:
            bound = os.getcwd()

        path = self.path
        if path[0] == os.path.sep:
            path = path[1:]

        path = os.path.normpath(os.path.join(bound, path))
        if os.path.commonpath([path, bound]) != bound:
            raise Exception("Can not traverse outside of working directory")

        if not os.path.exists(path) or not os.path.isfile(path):
            raise Exception(f"Path `{path}` not found or is not a file")

        return path


class HTTPResource:
    """HTTP resource implementation."""

    def cmd(self, arg, data):
        """Make the requests."""

        method = data.get('method', 'GET')
        uri = data['uri']
        headers = data.get('headers', {})
        json_data = data.get('json', None)
        ssl_verify = data.get('ssl_verify', True)
        ok_responses = data.get('ok_responses', [200, 201, 202, 204])
        form_data = data.get('form_data')

        if isinstance(ssl_verify, bool):
            verify = ssl_verify
        elif isinstance(ssl_verify, str):
            verify = str(tempfile.NamedTemporaryFile(
                delete=False,
                prefix='ssl-',
            ).write(verify))

        request_data = None
        if form_data:
            request_data = {k: json.dumps(v, ensure_ascii=False) for k, v in form_data.items()}

        response = requests.request(method, uri, json=json_data,
                                    data=request_data, headers=headers, verify=verify)

        log.info('http response code: %s', response.status_code)
        log.info('http response text: %s', response.text)

        if response.status_code not in ok_responses:
            raise Exception('Unexpected response {}'.format(response.status_code))

        return (response.status_code, response.text)

    def run(self, command_name: str, json_data: str, command_argument: typing.List[str]):
        """Parse input/arguments, perform requested command return output."""

        with tempfile.NamedTemporaryFile(delete=False, prefix=command_name + '-') as f:
            f.write(bytes(json_data, 'utf-8'))

        data = json.loads(json_data)
        resource_dir = command_argument[0]

        # allow debug logging to console for tests
        if os.environ.get('RESOURCE_DEBUG', False) or data.get('source', {}).get('debug', False):
            log.basicConfig(level=log.DEBUG)
        else:
            logfile = tempfile.NamedTemporaryFile(delete=False, prefix='log')
            log.basicConfig(level=log.DEBUG, filename=logfile.name)
            stderr = log.StreamHandler()
            stderr.setLevel(log.INFO)
            log.getLogger().addHandler(stderr)

        log.debug('command: %s', command_name)
        log.debug('input: %s', data)
        log.debug('args: %s', command_argument)
        log.debug('resource directory: %s', resource_dir)
        log.debug('environment: %s', os.environ)

        # initialize values with Concourse environment variables
        values = {k: v for k, v in os.environ.items() if k.startswith('BUILD_') or k == 'ATC_EXTERNAL_URL'}

        # combine source and params
        params = data.get('source', {})
        params.update(data.get('params', {}))

        # allow also to interpolate params
        values.update(params)

        # apply templating of environment variables onto parameters
        rendered_params = self._interpolate(params, values)

        # inject any file reference parameters
        rendered_params = self._inject_file_contents(
            rendered_params,
            resource_dir,
        )

        status_code, text = self.cmd(command_argument, rendered_params)

        # return empty version object
        response = {"version": {}}

        if os.environ.get('TEST', False):
            response.update(json.loads(text))

        return json.dumps(response)

    def _interpolate(self, data, values):
        """ Recursively apply values using format on all string key and values in data.
        """

        if isinstance(data, str):
            return data.format(**values)
        elif isinstance(data, list):
            return [self._interpolate(x, values) for x in data]
        elif isinstance(data, dict):
            return {self._interpolate(k, values): self._interpolate(v, values)
                    for k, v in data.items()}
        else:
            return data

    def _inject_file_contents(self, data, bounding_path):
        """ If a value starts with an "@" or "-@", load the path following the "@" or "-@"
            as a file and replace the value with the contents of the file.
        """

        if isinstance(data, str):
            try:
                file_ref = FileReference.parse(data, bounding_path=bounding_path)
                log.debug(
                    f"trying to expand data `{data}` into file "
                    f"reference with path `{file_ref.target_path}`"
                )
                return file_ref.contents
            except FileReference.Unparseable:
                return data
            except Exception:
                log.exception(f"error injecting file contents for data: `{data}`")
                return data
        elif isinstance(data, list):
            return [self._inject_file_contents(item, bounding_path) for item in data]
        elif isinstance(data, dict):
            return {k: self._inject_file_contents(v, bounding_path) for k, v in data.items()}
        else:
            return data


print(HTTPResource().run(os.path.basename(__file__), sys.stdin.read(), sys.argv[1:]))
