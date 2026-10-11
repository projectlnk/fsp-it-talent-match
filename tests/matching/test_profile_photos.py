"""Focused upload validation, replacement and visibility checks."""
from io import BytesIO
from PIL import Image
from sqlalchemy import select
from app.modules.auth.security import create_access_token
from app.modules.auth.models import User
from app.modules.matching.publication import csrf_token
from app.modules.candidates.models import CandidateProfile
from app.modules.employers.models import EmployerProfile
from app.modules.matching.service import set_publication
from app.web.photos import clean_photo, MAX_UPLOAD
from tests.matching.test_career_workflows import career
import pytest


def auth(user):return {'Authorization':'Bearer '+create_access_token(user.id)}

def picture(color='red',size=(240,180)):
    out=BytesIO();image=Image.new('RGB',size,color);exif=Image.Exif();exif[270]='private metadata'
    image.save(out,format='PNG',exif=exif);return out.getvalue()


def test_candidate_upload_replace_remove_and_visibility(career,client):
    db,e,c,company=career;profile=db.scalar(select(CandidateProfile).where(CandidateProfile.user_id==c.id));db.commit()
    url='/candidate/profile/photo';token={'token':csrf_token(c.id)}
    assert client.post(url,headers=auth(c),files={'photo':('photo.png',picture(),'image/png')},follow_redirects=False).status_code==403
    response=client.post(url,headers=auth(c),data=token,files={'photo':('photo.png',picture(),'image/png')},follow_redirects=False)
    assert response.status_code==303 and 'photo_saved=1' in response.headers['location']
    image_url=f'/profile-images/candidate/{profile.id}'
    response=client.get(image_url,headers=auth(c));assert response.status_code==200
    image=Image.open(BytesIO(response.content));assert image.format=='JPEG' and not image.getexif()
    assert response.headers['cache-control']=='private, no-store' and response.headers['x-content-type-options']=='nosniff'
    assert client.get(image_url).status_code==404
    other=db.scalar(select(User).where(User.email=='candidate-secret-1@example.invalid'));db.commit()
    assert client.get(image_url,headers=auth(other)).status_code==404
    assert client.get(image_url,headers=auth(e)).status_code==200
    db.expire_all();version=db.get(CandidateProfile,profile.id).photo_version;db.commit()
    response=client.post(url,headers=auth(c),data=token,files={'photo':('image.svg',b'<svg><script>bad()</script></svg>','image/svg+xml')},follow_redirects=False)
    assert 'photo_error=' in response.headers['location']
    db.expire_all();assert db.get(CandidateProfile,profile.id).photo_version==version;db.commit()
    client.post(url,headers=auth(c),data=token,files={'photo':('new.png',picture('blue'),'image/png')})
    db.expire_all();assert db.get(CandidateProfile,profile.id).photo_version!=version;db.commit()
    with db.begin():set_publication(db,c.id,False)
    db.commit();assert client.get(image_url,headers=auth(e)).status_code==404
    assert client.get(image_url,headers=auth(c)).status_code==200
    assert client.post(url,headers=auth(e),data={'token':csrf_token(e.id)},files={'photo':('new.png',picture(),'image/png')}).status_code==403
    client.post(url,headers=auth(c),data={**token,'remove':'true'})
    assert client.get(image_url,headers=auth(c)).status_code==404


def test_company_image_public_and_owner_only(career,client):
    db,e,c,company=career;db.commit();url='/employer/profile/photo'
    response=client.post(url,headers=auth(e),data={'token':csrf_token(e.id)},files={'photo':('office.webp',picture('gray',(640,360)),'image/webp')},follow_redirects=False)
    assert response.status_code==303
    assert client.get(f'/profile-images/company/{company.id}').status_code==200
    assert client.post(url,headers=auth(c),data={'token':csrf_token(c.id)},files={'photo':('office.png',picture(),'image/png')}).status_code==403
    db.expire_all();e=db.get(User,e.id);e.is_active=False;db.commit()
    assert client.get(f'/profile-images/company/{company.id}').status_code==404


def test_image_sanitizer_bounds_and_format():
    with pytest.raises(ValueError):clean_photo(b'x'*(MAX_UPLOAD+1))
    with pytest.raises(ValueError):clean_photo(b'<svg/>')
    photo=Image.open(BytesIO(clean_photo(picture(size=(2200,1400)),True)))
    assert photo.width<=1600 and photo.height<=1000
    out=BytesIO();Image.new('RGB',(4000,3100)).save(out,format='PNG')
    with pytest.raises(ValueError):clean_photo(out.getvalue())


def test_photo_controls_in_chromium(career, matching_server, browser):
    db, employer, candidate, company = career
    db.commit()
    for user, role in ((candidate, 'candidate'), (employer, 'employer')):
        context = browser.new_context(viewport={'width': 390, 'height': 900})
        context.add_cookies([{'name': 'access_token', 'value': create_access_token(user.id),
                             'url': matching_server}])
        page = context.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(matching_server + f'/{role}/profile')
        assert page.locator('.topnav a[href="/design-preview"]').count() == 0
        editor = page.locator('.photo-editor')
        editor.locator('summary').click()
        editor.locator('input[type=file]').set_input_files({
            'name': 'photo.png', 'mimeType': 'image/png', 'buffer': picture()})
        editor.locator('.photo-upload button').click()
        page.wait_for_url('**/profile?photo_saved=1')
        image = editor.locator('img')
        assert image.evaluate('(img)=>img.complete && img.naturalWidth > 0')
        first_url = image.get_attribute('src')
        for width in (1440, 390, 320):
            page.set_viewport_size({'width': width, 'height': 900})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            ratio = editor.locator('.photo-frame').evaluate('(e)=>e.clientWidth/e.clientHeight')
            assert abs(ratio - (16/9 if role == 'employer' else 4/5)) < .03
        editor.locator('summary').click()
        editor.locator('input[type=file]').set_input_files({
            'name': 'replacement.png', 'mimeType': 'image/png', 'buffer': picture('blue')})
        editor.locator('.photo-upload button').click()
        page.wait_for_load_state('networkidle')
        assert image.get_attribute('src') != first_url
        editor.locator('.photo-remove button').click()
        page.wait_for_load_state('networkidle')
        assert editor.locator('img').count() == 0
        if role == 'employer':
            page.goto(matching_server + '/career/leaderboard')
            assert page.locator('.ranking-table tbody tr.ranking-own').count() == 1
            assert page.locator('.ranking-table tbody .ranking-score').first.inner_text() == '0'
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        assert not errors
        context.close()
