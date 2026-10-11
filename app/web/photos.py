"""One image per profile, stored durably without publishing candidate files."""
from io import BytesIO
import uuid
import warnings
from PIL import Image, ImageOps, UnidentifiedImageError
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db.session import get_session
from app.modules.auth.dependencies import get_current_user_optional, require_role
from app.modules.auth.models import User, UserRole
from app.modules.candidates.models import CandidateProfile
from app.modules.employers.models import EmployerProfile
from app.modules.matching.publication import check_csrf

router = APIRouter(include_in_schema=False)
MAX_UPLOAD = 4 * 1024 * 1024


def clean_photo(data: bytes, landscape: bool = False) -> bytes:
    if not data or len(data) > MAX_UPLOAD:
        raise ValueError('Выберите изображение размером до 4 МБ.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as image:
                if image.format not in ('JPEG','PNG','WEBP') or image.width * image.height > 12_000_000:
                    raise ValueError('Используйте JPEG, PNG или WebP, не более 12 мегапикселей.')
                if getattr(image,'n_frames',1) != 1:
                    raise ValueError('Используйте неподвижную фотографию.')
                image = ImageOps.exif_transpose(image)
                image.thumbnail((1600,1000) if landscape else (1000,1200), Image.Resampling.LANCZOS)
                if 'A' in image.getbands():
                    white=Image.new('RGB',image.size,'white');white.paste(image,mask=image.getchannel('A'));image=white
                else:
                    image=image.convert('RGB')
                out=BytesIO();image.save(out,format='JPEG',quality=85,optimize=True)
                return out.getvalue()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValueError('Файл не удалось прочитать. Используйте JPEG, PNG или WebP.') from exc


async def save_photo(request, user, db, model, destination, photo, token, remove):
    check_csrf(request,user.id,token)
    row=db.scalar(select(model).where(model.user_id==user.id).with_for_update())
    if not row:
        raise HTTPException(404,'Профиль не найден')
    if remove:
        row.photo_data=row.photo_version=None
    else:
        try:
            row.photo_data=clean_photo(await photo.read(MAX_UPLOAD+1) if photo else b'',model==EmployerProfile)
        except ValueError as exc:
            db.rollback()
            from urllib.parse import urlencode
            return RedirectResponse(destination+'?'+urlencode({'photo_error':str(exc)}),303)
        finally:
            if photo:await photo.close()
        row.photo_version=uuid.uuid4().hex
    db.commit()
    return RedirectResponse(destination+'?photo_saved=1',303)


@router.post('/candidate/profile/photo')
async def candidate_upload(request: Request,photo: UploadFile | None = File(None),token: str = Form(''),
    remove: bool = Form(False),user: User = Depends(require_role(UserRole.CANDIDATE)),db: Session = Depends(get_session)):
    return await save_photo(request,user,db,CandidateProfile,'/candidate/profile',photo,token,remove)


@router.post('/employer/profile/photo')
async def company_upload(request: Request,photo: UploadFile | None = File(None),token: str = Form(''),
    remove: bool = Form(False),user: User = Depends(require_role(UserRole.EMPLOYER)),db: Session = Depends(get_session)):
    return await save_photo(request,user,db,EmployerProfile,'/employer/profile',photo,token,remove)


@router.get('/profile-images/candidate/{profile_id}')
def candidate_photo(profile_id: int,user: User | None = Depends(get_current_user_optional),db: Session = Depends(get_session)):
    profile=db.get(CandidateProfile,profile_id)
    allowed=bool(profile and user and profile.user_id==user.id)
    if profile and user and user.role==UserRole.EMPLOYER and user.is_email_verified:
        from app.modules.career.service import can_view_candidate
        from app.modules.matching.queries import visible_candidates
        from app.modules.matching.schemas import CandidateSearchQuery
        company=db.scalar(select(EmployerProfile).where(EmployerProfile.user_id==user.id))
        allowed=bool(company and (can_view_candidate(db,company.id,profile_id) or
            db.execute(visible_candidates(CandidateSearchQuery()).where(CandidateProfile.id==profile_id)).first()))
    if not allowed or not profile.photo_version:
        raise HTTPException(404,'Изображение недоступно')
    return image_response(profile.photo_data)


@router.get('/profile-images/company/{profile_id}')
def company_photo(profile_id: int,db: Session = Depends(get_session)):
    company=db.scalar(select(EmployerProfile).join(User).where(EmployerProfile.id==profile_id,
        User.is_active.is_(True),User.role==UserRole.EMPLOYER))
    if not company or not company.photo_version:
        raise HTTPException(404,'Изображение недоступно')
    return image_response(company.photo_data)


def image_response(data):
    if not data:raise HTTPException(404,'Изображение недоступно')
    return Response(data,media_type='image/jpeg',headers={'Cache-Control':'private, no-store',
        'X-Content-Type-Options':'nosniff','Content-Security-Policy':"default-src 'none'"})
