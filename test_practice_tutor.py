"""Tutor bridge authentication and actual startup staging regressions."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
from unittest.mock import patch
import pytest
from flask import Flask

ROOT = Path(__file__).parent
BUNDLE = ROOT / 'common/bin/practice_tutor'


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


tutor = module('tutor_bridge', BUNDLE / 'bridge.py')
installer = module('tutor_installer', ROOT / 'common/bin/install_practice_tutor.py')


def client(authenticated=True):
    app = Flask(__name__)
    tutor.register_routes(app, lambda: '123', lambda: authenticated)
    return app.test_client()


def test_nonpilot_does_not_install():
    config = dict(course_code='cse240',module='pex20',challenge='level-20-03',is_practice_exam=True)
    assert not installer.opted_in(config)
    config['practice_tutor'] = dict(enabled=True,course_dir='/cse/cse240-fc26')
    assert installer.opted_in(config)
    config['challenge'] = 'level-20-01'
    assert not installer.opted_in(config)


def test_context_requires_authentication_and_browser_session_token():
    browser = client()
    with patch.object(tutor, 'enabled', return_value=True), patch.object(tutor.subprocess, 'run') as run:
        assert browser.post('/exam_api/tutor/context').status_code == 403
        run.assert_not_called()
        token = browser.get('/exam_api/tutor/session').json['token']
        run.return_value.stdout = b'{"files":{}}'
        assert browser.post('/exam_api/tutor/context',headers={'X-Tutor-Token':token}).status_code == 200
        assert run.call_args.kwargs['user'] == 'hacker'
        assert run.call_args.kwargs['extra_groups'] == []
        assert 'CHATBOT_API_KEY' not in run.call_args.kwargs['env']
    with patch.object(tutor, 'enabled', return_value=True):
        assert client(False).get('/exam_api/tutor/session').status_code == 403


def test_identity_and_source_cannot_be_spoofed_by_browser(tmp_path):
    settings = tmp_path / 'settings.json'
    settings.write_text('{"endpoint_key":"secret","expires_at":4102444800}')
    browser = client()
    with patch.object(tutor, 'enabled', return_value=True), patch.object(tutor, 'SECRET', settings), patch.object(tutor.subprocess, 'run') as run, patch.object(tutor.requests, 'post') as post:
        token = browser.get('/exam_api/tutor/session').json['token']
        run.return_value.stdout = b'{"files":{"main.c":"saved"}}'
        post.return_value.status_code = 200
        post.return_value.json.return_value = {'reply':'concept'}
        result = browser.post('/exam_api/tutor/messages',json={'message':'help','pwn_college_id':'999','context':{'forged':True}},headers={'X-Tutor-Token':token})
        assert result.status_code == 200
        assert post.call_args.kwargs['json']['pwn_college_id'] == '123'
        assert post.call_args.kwargs['json']['context'] == {'files':{'main.c':'saved'}}
        assert post.call_args.kwargs['headers']['Authorization'] == 'Bearer secret'
        assert 'secret' not in result.get_data(as_text=True)


@pytest.mark.skipif(os.geteuid() != 0, reason='Root-owned startup staging; run with sudo')
def test_actual_install_and_repeat_start_preserve_snapshot_before_cleanup():
    with tempfile.TemporaryDirectory(dir='/root',prefix='tutor-test-') as directory:
        root = Path(directory)
        challenge = root / 'challenge'
        web = challenge / 'web'; web.mkdir(parents=True)
        (web / 'nginx.conf').write_text((ROOT / 'exam_common/web/nginx.conf').read_text())
        runtime = root / 'runtime'
        with patch.object(installer, 'RUNTIME', runtime):
            installer.install_assets(challenge, BUNDLE)
            installer.install_assets(challenge, BUNDLE)
            assert (web / 'nginx.conf').read_text().count(installer.SCRIPT) == 1
            assert (web / 'practice_tutor.py').is_file()
            assert (web / 'tutor_context.py').is_file()
            template = challenge / 'template'; template.mkdir()
            (template / 'main.c').write_text('Rendered requirement: exit option 8')
            private = challenge / 'model'; private.mkdir()
            (private / 'main.c').write_text('private solution')
            installer.snapshot(challenge)
            snapshot = (runtime / 'rendered.json').read_text()
            assert 'exit option 8' in snapshot
            assert 'private solution' not in snapshot
            assert (runtime / 'rendered.json').stat().st_mode & 0o777 == 0o644
            target = root / 'private.json'
            installer.write_file(target, '{"endpoint_key":"test"}', 0o600)
            assert target.stat().st_uid == 0
            assert target.stat().st_mode & 0o777 == 0o600
            staged = module('staged_tutor_bridge',web / 'practice_tutor.py')
            app = Flask(__name__)
            staged.register_routes(app,lambda:'123',lambda:True)
            with patch.object(staged,'enabled',return_value=True):
                response = app.test_client().get('/exam_api/tutor/')
                assert response.status_code == 200
                assert b'data-tutor-standalone' in response.data
                assert b'widget.js' in response.data
                assert b'Aita' in app.test_client().get('/exam_api/tutor/widget.js').data


def test_mud_optin_and_no_widget_without_provisioned_enrollment(tmp_path):
    config=dict(course_code='cse240',module='25-proj-mud',challenge='p25-level-01',
                practice_tutor=dict(enabled=True,course_dir='/cse/intro-to-programming-languages'))
    assert installer.opted_in(config)
    config_path=tmp_path/'level.json';config_path.write_text(json.dumps(config))
    secret=tmp_path/'settings.json'
    with patch.object(tutor,'CONFIG',config_path),patch.object(tutor,'SECRET',secret):
        assert not tutor.enabled()
        secret.write_text(json.dumps(dict(module='25-proj-mud',challenge='p25-level-01',endpoint_key='capability')))
        assert tutor.enabled()
        secret.write_text(json.dumps(dict(module='25-proj-mud',challenge='p25-level-02',endpoint_key='capability')))
        assert not tutor.enabled()
    config['challenge']='p25-level-09'
    assert not installer.opted_in(config)


def test_mud_denied_provisioning_never_installs_editor_assets(tmp_path):
    config=dict(course_code='cse240',module='25-proj-mud',challenge='p25-level-01',
                practice_tutor=dict(enabled=True,course_dir='/cse/intro-to-programming-languages'))
    config_path=tmp_path/'level.json';config_path.write_text(json.dumps(config))
    with patch.object(installer,'CONFIG',config_path),patch.object(installer,'SETTINGS',tmp_path/'settings.json'),patch.object(installer.os,'geteuid',return_value=0),patch.object(installer,'provision',side_effect=PermissionError()),patch.object(installer,'install_project_assets') as install,patch('sys.argv',['install']):
        installer.main()
    install.assert_not_called()


def test_mud_bridge_uses_container_assignment_not_browser(tmp_path):
    config_path=tmp_path/'level.json';config_path.write_text(json.dumps(dict(module='25-proj-mud',challenge='p25-level-04')))
    secret=tmp_path/'settings.json';secret.write_text(json.dumps(dict(endpoint_key='secret',expires_at=4102444800)))
    browser=client()
    with patch.object(tutor,'enabled',return_value=True),patch.object(tutor,'CONFIG',config_path),patch.object(tutor,'SECRET',secret),patch.object(tutor.subprocess,'run') as run,patch.object(tutor.requests,'post') as post:
        token=browser.get('/exam_api/tutor/session').json['token']
        run.return_value.stdout=b'{"files":{}}';post.return_value.status_code=200;post.return_value.json.return_value={'reply':'concept'}
        result=browser.post('/exam_api/tutor/messages',json=dict(message='help',module='pex20',challenge='forged'),headers={'X-Tutor-Token':token})
        assert result.status_code==200
        assert post.call_args.kwargs['json']['module']=='25-proj-mud'
        assert post.call_args.kwargs['json']['challenge']=='p25-level-04'


def test_project_editor_patch_is_idempotent_and_preserves_clipboard_routes(tmp_path):
    editor=tmp_path/'editor';route=editor/'out/node/routes/vscode.js';html=editor/'lib/vscode/out/vs/code/browser/workbench/workbench.html'
    route.parent.mkdir(parents=True);html.parent.mkdir(parents=True)
    route.write_text('exports.router = express.Router();\n// existing clipboard routes\n')
    html.write_text('<head><script src="clipboard.js"></script></head>')
    def write(path,content,mode=0o644):path.write_text(content)
    with patch.object(installer,'write_file',side_effect=write):
        installer.patch_project_editor(editor,BUNDLE)
        installer.patch_project_editor(editor,BUNDLE)
    assert route.read_text().count('// AITA_PROJECT_ROUTES')==1
    assert 'existing clipboard routes' in route.read_text()
    assert html.read_text().count('exam_api/tutor/widget.js')==1
    assert 'clipboard.js' in html.read_text()
