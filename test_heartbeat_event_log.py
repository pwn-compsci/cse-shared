"""Exercise the shipped heartbeat without starting its monitoring loop."""
import ast
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parent


def shipped_writer():
    tree = ast.parse((ROOT/'common/pex_heartbeat').read_text())
    nodes = [node for node in tree.body if isinstance(node, (ast.Import, ast.ImportFrom))
             or isinstance(node, ast.FunctionDef) and node.name == 'update_event_log']
    namespace = {}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), 'pex_heartbeat', 'exec'), namespace)
    return namespace['update_event_log'], tree


class HeartbeatEventLogTest(unittest.TestCase):
    def test_shipped_writer_requires_no_local_helper(self):
        update, tree = shipped_writer()
        self.assertFalse(any(isinstance(node, ast.ImportFrom) and node.module == 'event_log'
                             for node in tree.body))
        with tempfile.TemporaryDirectory() as temp:
            file = Path(temp)/'log.json'
            file.write_bytes(b'{broken')
            update(file, lambda data: data.update({'requirements': {'ccFile': 'CC_abc.c'},
                                                 '/home/hacker/main.c': []}))
            self.assertEqual(next(Path(temp).glob('*.malformed-*')).read_bytes(), b'{broken')
            update(file, lambda data: data['/home/hacker/main.c'].append({'hashed_filename': 't_abc.c'}))
            data = json.loads(file.read_text())
            self.assertEqual(data['requirements']['ccFile'], 'CC_abc.c')
            self.assertEqual(len(data['/home/hacker/main.c']), 1)

    def test_shipped_writer_matches_cross_language_test_helper(self):
        _, tree = shipped_writer()
        shipped = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                       and node.name == 'update_event_log')
        helper = ast.parse((ROOT/'common/event_log.py').read_text())
        expected = next(node for node in helper.body if isinstance(node, ast.FunctionDef)
                        and node.name == 'update_event_log')
        self.assertEqual(ast.dump(shipped), ast.dump(expected))
