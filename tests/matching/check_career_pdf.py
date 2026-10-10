"""Explicit one-document check against the owned local Compose app, not production."""
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse
import os
import re
import uuid
import httpx
from pypdf import PdfReader

def main():
    base=os.environ['CAREER_APP_URL'];mail=os.environ['CAREER_MAIL_URL']
    if urlparse(base).hostname not in ('localhost','127.0.0.1'):
        raise RuntimeError('Only local isolated application allowed')
    email='career-pdf-'+uuid.uuid4().hex[:12]+'@example.com'
    with httpx.Client(base_url=base,timeout=30) as client:
        result=client.post('/api/v1/auth/register',json={'email':email,'password':'pdf-test1234','role':'candidate','full_name':'Екатерина Проверочная','processing_consent':True})
        result.raise_for_status()
        messages=httpx.get(mail+'/api/v1/messages').json()['messages']
        msg=next(m for m in messages if any(r['Address']==email for r in m['To']))
        body=httpx.get(mail+'/api/v1/message/'+msg['ID']).json()['Text']
        link=re.search(r'https?://[^\s<]+/auth/verify\?token=[A-Za-z0-9_\-]+',body).group(0)
        assert link.startswith(base+'/auth/verify?') and 'http://app:' not in link
        client.get(link).raise_for_status()
        token=client.post('/api/v1/auth/login',json={'email':email,'password':'pdf-test1234'}).json()['access_token']
        client.headers['Authorization']='Bearer '+token
        sentence='Разработка распределённых систем, транзакции PostgreSQL, интеграция сервисов и поддержка команды. '
        client.patch('/api/v1/candidates/me',json={'full_name':'Екатерина Проверочная — специалист по разработке распределённых информационных систем','phone':'+7 000 111-22-33','location':'Москва','about':sentence*35+'КОНЕЦ_ОПИСАНИЯ','work_format':'remote','desired_role':'Разработчик программного обеспечения','desired_salary_from':120000,'desired_salary_to':180000}).raise_for_status()
        client.post('/api/v1/candidates/me/skills',json={'skill':'Python','level':'middle'}).raise_for_status()
        client.post('/api/v1/candidates/me/experiences',json={'company_name':'Тестовая команда','position':'Разработчик','description':sentence*15+'КОНЕЦ_ОПЫТА','started_at':'2024-01-01','is_current':True}).raise_for_status()
        response=client.get('/candidate/profile/resume.pdf');response.raise_for_status()
    assert response.content.startswith(b'%PDF-')
    pdf=PdfReader(BytesIO(response.content));text='\n'.join(page.extract_text() or '' for page in pdf.pages)
    for marker in ('Екатерина','Проверочная','КОНЕЦ_ОПИСАНИЯ','КОНЕЦ_ОПЫТА','Python',email,'+7 000 111-22-33'):
        assert marker in text,marker
    assert len(pdf.pages)>=2
    target=Path('test-results/career-resume.pdf');target.parent.mkdir(exist_ok=True);target.write_bytes(response.content)
    print(f'PDF OK: {len(pdf.pages)} pages; Cyrillic, long fields, skills and owner contacts; {target}')
    print('Mail verification URL OK: '+base+'/auth/verify (query omitted)')

if __name__=='__main__':main()
