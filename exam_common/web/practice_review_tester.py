#!/usr/bin/env python3
"""Invoke the saved-attempt tester outside the editor's no-new-privileges sandbox."""
import json
import os
import sys
import urllib.error
import urllib.request

URL = 'http://127.0.0.1:5000/exam_api/practice-variants/review-test'


def main():
    try:
        with urllib.request.urlopen(URL, timeout=10) as response:
            token = json.load(response)['token']
        payload = json.dumps({'token': token, 'directory': os.getcwd(), 'args': sys.argv[1:]}).encode()
        request = urllib.request.Request(URL, data=payload, headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(request, timeout=130) as response:
            result = json.load(response)
        print(result.get('output', ''), end='')
        return result.get('returncode', 1)
    except urllib.error.HTTPError as error:
        try:
            message = json.load(error).get('error', 'Saved-attempt testing failed.')
        except (ValueError, KeyError):
            message = 'Saved-attempt testing failed.'
        print(message, file=sys.stderr)
        return 1
    except (OSError, ValueError, KeyError) as error:
        print('Saved-attempt tester unavailable: ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
