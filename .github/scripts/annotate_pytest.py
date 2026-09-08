"""Đổi phần cuối output pytest thành một annotation của GitHub Actions.

Vì sao cần: log của Actions chỉ xem được khi đã đăng nhập, còn annotation thì
REST API trả về không cần token (`/check-runs/{id}/annotations`). Máy dev không
có Docker nên Mongo/Meilisearch chỉ tồn tại trên CI — đây là đường duy nhất để
biết CI hỏng ở đâu mà không mở được log.

Để ở file riêng, không viết thẳng vào `ci.yml`: nhúng heredoc Python vào một
block scalar YAML đã làm hỏng cả workflow một lần — chuỗi có `\n` bị xuống dòng
thật, block scalar đứt, workflow không parse được nên không job nào chạy.
"""

from __future__ import annotations

import pathlib
import sys

MAX_CHARS = 8000


def main() -> int:
    path = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "pytest.log")
    if not path.exists():
        print(f"::error title=pytest::không có {path}")
        return 0

    tail = path.read_text(errors="replace")[-MAX_CHARS:]
    # Annotation là MỘT dòng. Không mã hoá thì chỉ dòng đầu tiên lọt ra ngoài.
    escaped = tail.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    print(f"::error title=pytest::{escaped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
