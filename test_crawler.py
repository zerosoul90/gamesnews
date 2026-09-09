import asyncio
import sys
from app.models.source import Source
from app.services.crawler import crawl_rss
from app.services.entity_matcher import match_entity
from motor.motor_asyncio import AsyncIOMotorClient

async def main():
    sys.stdout.reconfigure(encoding='utf-8')
    print("--- BẮT ĐẦU TEST SCRIPT CRAWLER & ENTITY MATCHING ---")
    
    # 1. Định nghĩa Nguồn (IGN)
    ign_source = Source(
        name="IGN",
        url="https://feeds.feedburner.com/ign/news", # RSS feed của IGN
        language="en"
    )
    
    # 2. Chạy Crawler
    articles = await crawl_rss(ign_source)
    print(f"\n[ Crawler ] Lấy được {len(articles)} bài viết từ {ign_source.name}.")
    
    if not articles:
        return
        
    # 3. Test Khử trùng lặp (Simhash)
    # Vì cùng một luồng ít khi trùng ngay, ta tự làm giả bài viết trùng lặp
    from app.services.dedup import is_duplicate
    print("\n[ Dedup ] Chạy kiểm tra khử trùng lặp...")
    unique_articles = []
    seen_hashes = []
    
    duplicate_count = 0
    for art in articles:
        is_dup = False
        for seen in seen_hashes:
            if is_duplicate(art.simhash, seen):
                is_dup = True
                duplicate_count += 1
                break
        
        if not is_dup:
            seen_hashes.append(art.simhash)
            unique_articles.append(art)
            
    print(f"-> Khử được {duplicate_count} bài trùng lặp bằng thuật toán khoảng cách Hamming.")
    print(f"-> Còn lại {len(unique_articles)} bài độc lập.")
    
    # 4. Test Entity Matching 3 Tầng
    print("\n[ Entity Match ] Chạy bộ lọc 3 tầng trên 10 bài đầu tiên...")
    
    # MOCK DB & Qdrant
    mock_db = None 
    mock_qdrant = None
    
    exact_count = 0
    fuzzy_count = 0
    manual_count = 0
    
    # Giới hạn test 10 bài để khỏi dội log
    for art in unique_articles[:10]:
        print(f"\nBài báo: {art.title}")
        game_id, tier, score = await match_entity(mock_db, art.title, art.original_content, mock_qdrant)
        
        if tier == "exact":
            exact_count += 1
            print(f"  => [PASS] EXACT MATCH (Link store): {game_id}")
        elif tier == "fuzzy":
            fuzzy_count += 1
            print(f"  => [PASS] FUZZY MATCH (Khớp chuỗi {score:.2f}): {game_id}")
        else:
            manual_count += 1
            print("  => [FAIL] Không khớp được. Đẩy vào HÀNG ĐỢI DUYỆT TAY (Manual Review).")
            
    print("\n--- TỔNG KẾT ---")
    print(f"Tổng bài test: 10")
    print(f"Tỉ lệ tự động nhận diện: {(exact_count + fuzzy_count) * 10}%")
    print(f"Đẩy ra duyệt tay: {manual_count * 10}%")
    print("Test hoàn tất. Hệ thống sẵn sàng cho bước Tóm tắt và Dịch thuật (LLM).")

if __name__ == "__main__":
    asyncio.run(main())
