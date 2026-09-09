from typing import Any

from bson import ObjectId
from fastapi import APIRouter, HTTPException

from app.api.admin import AdminAuth
from app.core.deps import MongoDep
from app.core.serialization import jsonify_docs
from app.models.source import Source, SourceStatus
from app.services import sources as service

# `dependencies=[AdminAuth]` cho CẢ router, không phải từng route.
#
# Bản trước quên hẳn chốt này: router nằm dưới tiền tố `/admin/api/...` nên
# nhìn qua tưởng được `api/admin.py` bảo vệ, nhưng nó là một router khác và
# FastAPI không thừa kế dependency theo đường dẫn. Nghĩa là bất kỳ ai cũng
# `POST /admin/api/sources` thêm được một feed RSS — và feed đó chảy thẳng vào
# đường crawl → LLM → hiển thị công khai.
router = APIRouter(
    tags=["sources"],
    prefix="/admin/api/sources",
    dependencies=[AdminAuth],
)


@router.post("")
async def create_source(db: MongoDep, source: Source) -> dict[str, Any]:
    doc = await service.create_source(db, source)
    return dict(jsonify_docs([doc])[0])


@router.get("")
async def get_sources(db: MongoDep) -> list[dict[str, Any]]:
    return jsonify_docs(await service.get_sources(db))


@router.patch("/{source_id}/status")
async def update_status(db: MongoDep, source_id: str, status: SourceStatus) -> dict[str, Any]:
    """Bật/tắt một nguồn.

    `status` khai bằng `SourceStatus` chứ không phải `str`: gõ sai thì nhận 422
    thay vì ghi một trạng thái mà `crawl_all_sources` không bao giờ khớp, khiến
    nguồn im lặng biến mất khỏi mọi lượt crawl.
    """
    if not ObjectId.is_valid(source_id):
        raise HTTPException(status_code=400, detail="source_id không hợp lệ")
    success = await service.update_source_status(db, source_id, status)
    return {"success": success}
