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
    assert not installer.opted_in(config)  # Practice rollout is deferred too.
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
def test_root_owned_assets_and_snapshot_preserve_starter_before_cleanup():
    with tempfile.TemporaryDirectory(dir='/root',prefix='tutor-test-') as directory:
        root = Path(directory)
        challenge = root / 'challenge'
        web = challenge / 'web'; web.mkdir(parents=True)
        runtime = root / 'runtime'
        with patch.object(installer, 'RUNTIME', runtime):
            for source, destination in installer.ASSETS.items():
                installer.write_file(web / destination, (BUNDLE / source).read_text())
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


@pytest.mark.parametrize('flag,value', [('examLevel','level-20-03'),('is_exam',True),('is_practice_exam',True),('practice_exam',True)])
def test_exam_flags_disable_installer_bridge_and_widget_even_with_valid_settings(tmp_path,flag,value):
    config=dict(course_code='cse240',module='25-proj-mud',challenge='p25-level-01',practice_tutor=dict(enabled=True,course_dir='/cse/intro-to-programming-languages'))
    config[flag]=value
    assert not installer.opted_in(config)
    config_path=tmp_path/'level.json';config_path.write_text(json.dumps(config))
    secret=tmp_path/'settings.json';secret.write_text(json.dumps(dict(module='25-proj-mud',challenge='p25-level-01',endpoint_key='valid-admin-capability')))
    with patch.object(tutor,'CONFIG',config_path),patch.object(tutor,'SECRET',secret):
        assert not tutor.enabled()
        browser=client()
        assert browser.get('/exam_api/tutor/widget.js').data==b''
        assert browser.get('/exam_api/tutor/session').status_code==404


def test_exam_runtime_marker_disables_otherwise_allowed_lab():
    config=dict(course_code='cse240',module='25-proj-mud',challenge='p25-level-01',practice_tutor=dict(enabled=True,course_dir='/cse/intro-to-programming-languages'))
    with patch.object(Path,'exists',return_value=True):
        assert not installer.opted_in(config)


def test_nontracked_editor_start_preserves_service_and_drops_privileges(tmp_path):
    from types import SimpleNamespace
    runtime=tmp_path/'runtime';runtime.mkdir()
    (runtime/'editor.json').write_text(json.dumps(dict(editor='/run/aita-code-server',node='/nix/node',tracked=False)))
    user=SimpleNamespace(pw_dir='/home/hacker',pw_name='hacker',pw_uid=1000,pw_gid=1000)
    with patch.object(installer,'RUNTIME',runtime),patch('pwd.getpwnam',return_value=user),patch.object(Path,'exists',return_value=False),patch.object(Path,'is_dir',return_value=True),patch.object(installer.subprocess,'run') as run:
        installer.start_project_editor()
    args=run.call_args.args[0]
    assert args[:3]==['/run/dojo/bin/dojo-service','start','code-service/code-server']
    assert '/run/aita-code-server/out/node/entry.js' in args
    assert '--bind-addr=0.0.0.0:8080' in args
    assert callable(run.call_args.kwargs['preexec_fn'])
    assert run.call_args.kwargs['env']['HOME']=='/home/hacker'
    assert 'ultima-terminal' not in str(args)


def test_pex30_is_a_narrow_practice_opt_in():
    config = dict(course_code='cse240', module='pex30', challenge='level-30-02',
                  examLevel='exam-30-02', is_practice_exam=True,
                  practice_tutor=dict(enabled=True, course_dir='/cse/cse240-fc26'))
    assert installer.opted_in(config)
    for change in [dict(challenge='level-30-01'), dict(is_exam=True), dict(is_practice_exam=False), dict(examLevel='exam-30-01')]:
        assert not installer.opted_in({**config, **change})


def test_practice_bridge_rejects_stale_context_before_forwarding(tmp_path, monkeypatch):
    import sys
    from types import SimpleNamespace
    monkeypatch.setattr(tutor, 'enabled', lambda: True)
    monkeypatch.setattr(tutor, 'target', lambda: dict(module='pex30', challenge='level-30-02', variant='a'))
    monkeypatch.setitem(sys.modules, 'tutor_selection', SimpleNamespace(resolve=lambda attempt: {'workdir':'saved'}))
    key = 'b:'+'1'*32
    context = dict(selection=dict(key=key, label='Saved attempt · Question B'), files={'Movie.cpp':'saved'})
    settings = tmp_path/'settings.json'
    settings.write_text(json.dumps(dict(endpoint_key='secret', expires_at=4102444800)))
    monkeypatch.setattr(tutor, 'SECRET', settings)
    browser = client()
    with patch.object(tutor.subprocess, 'run', return_value=SimpleNamespace(stdout=json.dumps(context))) as run, patch.object(tutor.requests, 'post') as post:
        token = browser.get('/exam_api/tutor/session?attempt=02_saved').json['token']
        headers = {'X-Tutor-Token':token}
        assert browser.post('/exam_api/tutor/messages', json=dict(message='help', attempt='02_saved', context_key='wrong'), headers=headers).status_code == 409
        post.assert_not_called()
        post.return_value.status_code = 200
        post.return_value.json.return_value = {'reply':'concept'}
        assert browser.post('/exam_api/tutor/messages', json=dict(message='help', attempt='02_saved', context_key=key), headers=headers).status_code == 200
        assert post.call_args.kwargs['json']['variant'] == key
        assert post.call_args.kwargs['json']['context']['files'] == {'Movie.cpp':'saved'}
        assert run.call_args.args[0][-1] == '--practice'


@pytest.mark.skipif(os.geteuid() != 0, reason='Root-owned startup staging')
def test_practice_install_stages_overlay_and_selection():
    with tempfile.TemporaryDirectory(dir='/root', prefix='aita-practice-') as directory:
        root = Path(directory)
        web = root/'web'; web.mkdir()
        (web/'nginx.conf').write_text('<!--CSE240_EXAM-->')
        with patch.object(installer, 'RUNTIME', root/'runtime'):
            installer.install_assets(root, BUNDLE)
            installer.install_assets(root, BUNDLE)
        assert (web/'nginx.conf').read_text().count(installer.SCRIPT) == 1
        assert (root/'runtime/practice_tutor/eligibility.py').is_file()
        assert (web/'tutor_selection.py').is_file()
        assert (web/'tutor_practice_context.py').is_file()


@pytest.mark.parametrize('name,source', [
    ('main.rkt', '#lang racket\n(displayln "student work")'),
    ('main.scm', '(display "student work")'),
    ('main.pl', 'student_work(example).'),
])
def test_practice_collector_includes_language_source_and_excludes_unsafe_files(tmp_path, monkeypatch, name, source):
    monkeypatch.syspath_prepend(str(ROOT / 'exam_common/web'))
    import practice_attempts as attempts
    collector = module('language_practice_context', BUNDLE / 'practice_context.py')
    active = tmp_path / 'active'; active.mkdir()
    (active / name).write_text('different active work')
    saved = tmp_path / 'saved'; saved.mkdir()
    (saved / name).write_text(source)
    (saved / ('leak_' + name)).symlink_to(active / name)
    (saved / 'model').mkdir()
    (saved / 'model' / name).write_text('hidden solution')
    with patch.object(attempts, 'feedback', return_value=[]):
        context = collector.collect(dict(workdir=str(saved), home=str(tmp_path),
            config={}, record={}, selection=dict(key='saved')))
    assert context['files'] == {name: source}
