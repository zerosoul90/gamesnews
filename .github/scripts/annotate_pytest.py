"""Đổi phần cuối output pytest thành annotation của GitHub Actions.

Vì sao cần: log của Actions chỉ xem được khi đã đăng nhập, còn annotation thì
REST API trả về không cần token (`/check-runs/{id}/annotations`). Máy dev không
có Docker nên Mongo/Meilisearch chỉ tồn tại trên CI — đây là đường duy nhất để
biết CI hỏng ở đâu mà không mở được log.

Để ở file riêng, không viết thẳng vào `ci.yml`: nhúng heredoc Python vào một
block scalar YAML đã làm hỏng cả workflow một lần — ký tự xuống dòng trong
chuỗi thành xuống dòng thật, block scalar đứt, workflow không parse được nên
không job nào chạy.
"""

from __future__ import annotations

import pathlib
import sys

# GitHub cắt bớt annotation dài, nên chia thành nhiều mẩu thay vì gửi một khối.
# Mỗi step chỉ hiện tối đa 10 annotation cùng mức; lấy 8 cho chắc.
CHUNK_CHARS = 2500
MAX_CHUNKS = 8

# Viết bằng chr() thay vì ký tự escape: chuỗi này đi qua vài tầng công cụ, và
# một backslash bị nuốt là ký tự xuống dòng thật lọt vào chính file này — đã
# xảy ra hai lần.
CR = chr(13)
LF = chr(10)


def encode(text: str) -> str:
    """Một annotation là MỘT dòng. Không mã hoá thì chỉ dòng đầu lọt ra ngoài."""
    return text.replace("%", "%25").replace(CR, "%0D").replace(LF, "%0A")


def main() -> int:
    path = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "pytest.log")
    if not path.exists():
        print(f"::error title=pytest::không có {path}")
        return 0

    tail = path.read_text(errors="replace")[-CHUNK_CHARS * MAX_CHUNKS :]
    chunks = [tail[i : i + CHUNK_CHARS] for i in range(0, len(tail), CHUNK_CHARS)]

    for number, chunk in enumerate(chunks, start=1):
        print(f"::error title=pytest {number}/{len(chunks)}::{encode(chunk)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
