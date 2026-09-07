"""Adapter giả — chứng minh interface trong `adapters/base.py` dùng được.

Không gọi mạng. Phase 0 cấm mọi cuộc gọi ra ngoài; adapter này chỉ phát lại
một kịch bản dựng sẵn nên test kiểm được retry, phân loại lỗi và hook mà không
phụ thuộc bên thứ ba.
"""

from app.adapters.dummy.adapter import DummyAdapter, DummyPayload

__all__ = ["DummyAdapter", "DummyPayload"]
