from fastapi.testclient import TestClient
from mock_fsp.main import app
from mock_fsp.storage import rows

def test_mock_operator_validation_upsert_and_persistence(tmp_path,monkeypatch):
    monkeypatch.setenv('MOCK_STORAGE_PATH',str(tmp_path/'registry.sqlite'))
    monkeypatch.setenv('DEMO_MOCK_KEY','test-only-key')
    participant={'id':'test-operator','display_name':'Тестовый участник','email':'demo@example.test'}
    achievement={'id':'test-award','participant_id':'test-operator','title':'Тестовый турнир','place':1,'rank':'Кандидат','is_team':True,'team_name':'Команда'}
    with TestClient(app) as client:
        assert client.put('/operator/participants',json=participant).status_code==403
        monkeypatch.setenv('MOCK_DEMO_MODE','true')
        assert client.put('/operator/participants',json=participant,headers={'X-Demo-Key':'wrong'}).status_code==403
        headers={'X-Demo-Key':'test-only-key'}
        assert client.put('/operator/participants',json={**participant,'id':'../bad'},headers=headers).status_code==422
        assert client.put('/operator/participants',json=participant,headers=headers).status_code==200
        assert client.put('/operator/achievements',json={**achievement,'place':-1},headers=headers).status_code==422
        assert client.put('/operator/achievements',json=achievement,headers=headers).status_code==200
        achievement['title']='Обновлённый турнир'
        assert client.put('/operator/achievements',json=achievement,headers=headers).status_code==200
    # New client and storage connection read the same file, not Python module lists.
    with TestClient(app) as restarted:
        data=restarted.get('/participants/test-operator/achievements').json()
        assert len(data)==1 and data[0]['title']=='Обновлённый турнир'
        assert data[0]['rank']=='Кандидат' and data[0]['is_team']
        assert len([p for p in restarted.get('/participants').json() if p['id']=='test-operator'])==1
