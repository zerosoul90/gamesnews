from bs4 import BeautifulSoup
from simhash import Simhash


def compute_simhash(html_content: str) -> str:
    """Loại bỏ thẻ HTML và tính Simhash để so sánh văn bản."""
    # Bóc tách HTML lấy văn bản thuần
    soup = BeautifulSoup(html_content, "html.parser")
    text = soup.get_text(separator=" ", strip=True)

    # Tính simhash (mặc định băm thành 64 bit)
    hash_value = Simhash(text).value
    return str(hash_value)

def is_duplicate(hash1: str, hash2: str, threshold: int = 3) -> bool:
    """Tính khoảng cách Hamming giữa 2 giá trị Simhash.
    Nếu khoảng cách <= threshold (mặc định = 3), coi như bài viết trùng lặp.
    """
    try:
        val1 = int(hash1)
        val2 = int(hash2)
    except ValueError:
        return False

    distance = bin(val1 ^ val2).count('1')
    return distance <= threshold
