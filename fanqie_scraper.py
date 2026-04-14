import argparse
import json
import datetime
import sys
try:
    import requests
except ImportError:
    print("缺少 requests 库，请先执行: pip install requests")
    sys.exit(1)

def is_non_empty_string(v):
    return isinstance(v, str) and len(v.strip()) > 0

def normalize_image_url(raw):
    if not raw: return raw
    t = raw.strip()
    if not t: return t
    if t.startswith("//"): return f"https:{t}"
    return t

def extract_initial_state(html):
    marker = "window.__INITIAL_STATE__="
    idx = html.find(marker)
    if idx < 0: return None
    start = idx + len(marker)
    first_brace = html.find("{", start)
    if first_brace < 0: return None
    depth = 0
    end = -1
    for i in range(first_brace, len(html)):
        if html[i] == "{": depth += 1
        elif html[i] == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end < 0: return None
    try:
        return json.loads(html[first_brace:end])
    except:
        return None

def is_valid_cover_url(url):
    if not is_non_empty_string(url): return False
    u = url.strip()
    if u.startswith("data:"): return False
    if not (u.startswith("http://") or u.startswith("https://")): return False
    return True

def compute_report(snapshots):
    per_category = {}
    failures = []
    violations = []
    total_books = 0
    total_missing_title = 0
    total_missing_author = 0
    total_missing_cover = 0
    total_invalid_cover = 0
    total_duplicate_pid = 0

    for s in snapshots:
        books = s.get("books", [])
        dup_ids = set()
        seen = set()
        missing_title = 0
        missing_author = 0
        missing_cover = 0
        invalid_cover = 0

        for b in books:
            pid = str(b.get("platformId", ""))
            if pid:
                if pid in seen: dup_ids.add(pid)
                seen.add(pid)
            if not is_non_empty_string(b.get("title")): missing_title += 1
            if not is_non_empty_string(b.get("author")): missing_author += 1
            
            curl = b.get("coverUrl", "")
            if not is_non_empty_string(curl): missing_cover += 1
            elif not is_valid_cover_url(curl): invalid_cover += 1

        if len(books) == 0: failures.append(s["rankKey"])

        count = len(books)
        title_rate = (count - missing_title) / count if count > 0 else 0
        author_rate = (count - missing_author) / count if count > 0 else 0
        cover_rate = (count - missing_cover - invalid_cover) / count if count > 0 else 0

        meets_thresholds = title_rate >= 0.99 and author_rate >= 0.99 and cover_rate >= 0.95 and len(dup_ids) == 0
        if not meets_thresholds: violations.append(s["rankKey"])

        per_category[s["rankKey"]] = {
            "group": s.get("group"),
            "name": s.get("name"),
            "count": count,
            "missing": {"title": missing_title, "author": missing_author, "coverUrl": missing_cover},
            "invalidCoverUrl": invalid_cover,
            "duplicatePlatformId": len(dup_ids),
            "rates": {
                "titleNonEmpty": round(title_rate, 4),
                "authorNonEmpty": round(author_rate, 4),
                "coverUrlNonEmptyAndValid": round(cover_rate, 4)
            },
            "meetsThresholds": meets_thresholds
        }

        total_books += count
        total_missing_title += missing_title
        total_missing_author += missing_author
        total_missing_cover += missing_cover
        total_invalid_cover += invalid_cover
        total_duplicate_pid += len(dup_ids)

    total_title_rate = (total_books - total_missing_title) / total_books if total_books > 0 else 0
    total_author_rate = (total_books - total_missing_author) / total_books if total_books > 0 else 0
    total_cover_rate = (total_books - total_missing_cover - total_invalid_cover) / total_books if total_books > 0 else 0

    return {
        "perCategory": per_category,
        "failures": failures,
        "violations": violations,
        "summary": {
            "totalBooks": total_books,
            "missing": {"title": total_missing_title, "author": total_missing_author, "coverUrl": total_missing_cover},
            "invalidCoverUrl": total_invalid_cover,
            "duplicatePlatformId": total_duplicate_pid,
            "rates": {
                "titleNonEmpty": round(total_title_rate, 4),
                "authorNonEmpty": round(total_author_rate, 4),
                "coverUrlNonEmptyAndValid": round(total_cover_rate, 4)
            }
        }
    }

def main():
    parser = argparse.ArgumentParser(description="番茄小说排行榜本地抓取脚本 (Python)")
    parser.add_argument("--categories", default="scripts/fanqie-categories.json", help="分类 JSON 文件路径")
    parser.add_argument("--max", type=int, help="每个分类最大抓取数量")
    parser.add_argument("--out", default="fanqie-snapshots.json", help="输出 JSON 文件路径")
    parser.add_argument("--upload-url", help="推送接口 URL (可选)")
    parser.add_argument("--key", help="推送接口鉴权密钥 (x-market-import-key)")
    args = parser.parse_args()

    try:
        with open(args.categories, "r", encoding="utf-8") as f:
            categories = json.load(f)
    except Exception as e:
        print(f"读取分类文件失败 {args.categories}: {e}")
        sys.exit(1)

    date_str = datetime.datetime.now().strftime("%Y-%m-%d")
    snapshots = []

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://fanqienovel.com/"
    }

    print(f"开始抓取 {len(categories)} 个分类...")
    for cat in categories:
        rank_key = cat.get("rankKey", "")
        name = cat.get("name", "")
        group = cat.get("group", "")
        
        empty_snapshot = {"rankKey": rank_key, "group": group, "name": name, "books": []}
        if not rank_key.startswith("rank/"):
            snapshots.append(empty_snapshot)
            continue

        url = f"https://fanqienovel.com/{rank_key}"
        try:
            res = requests.get(url, headers=headers, timeout=10)
            if res.status_code != 200:
                print(f"  [失败] {name} ({rank_key}) - HTTP {res.status_code}")
                snapshots.append(empty_snapshot)
                continue

            html = res.text
            state = extract_initial_state(html)
            if not state:
                print(f"  [失败] {name} ({rank_key}) - 无法解析 __INITIAL_STATE__")
                snapshots.append(empty_snapshot)
                continue
            
            book_list = state.get("rank", {}).get("book_list", [])
            if args.max:
                book_list = book_list[:args.max]
            
            books = []
            for i, b in enumerate(book_list):
                platform_id = str(b.get("bookId", "")).strip()
                if not platform_id: continue
                
                title = str(b.get("bookName", "")).strip() or "未知书名"
                author = str(b.get("author", "")).strip() or "未知作者"
                intro = str(b.get("abstract", "")).strip() or "暂无简介"
                cover_url = normalize_image_url(b.get("thumbUri", ""))
                
                wc_str = b.get("wordNumber", "")
                word_count = int(wc_str) if str(wc_str).isdigit() else None
                
                ok_cover = is_valid_cover_url(cover_url)
                
                books.append({
                    "platformId": platform_id,
                    "rank": i + 1,
                    "isNew": True,
                    "title": title,
                    "author": author,
                    "category": name,
                    "intro": intro,
                    "coverUrl": cover_url if ok_cover else "",
                    "wordCount": word_count
                })
            
            snapshots.append({
                "rankKey": rank_key,
                "group": group,
                "name": name,
                "books": books
            })
            print(f"  [成功] {name} ({rank_key}) - 抓取到 {len(books)} 本")
        except Exception as e:
            print(f"  [异常] {name} ({rank_key}) - {e}")
            snapshots.append(empty_snapshot)

    report = compute_report(snapshots)
    payload = {"date": date_str, "snapshots": snapshots}
    
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        
    report_out = args.out.replace(".json", ".report.json")
    if report_out == args.out:
        report_out = args.out + ".report.json"
        
    with open(report_out, "w", encoding="utf-8") as f:
        report_data = {"date": date_str}
        report_data.update(report)
        json.dump(report_data, f, ensure_ascii=False, indent=2)

    print(f"\n抓取完成! 数据已保存至 {args.out} 和 {report_out}")

    if args.upload_url:
        print(f"\n正在推送数据至: {args.upload_url} ...")
        push_headers = {
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json"
        }
        if args.key:
            push_headers["x-market-import-key"] = args.key
            
        try:
            res = requests.post(args.upload_url, headers=push_headers, json={"payload": payload}, timeout=30)
            print(f"推送结果: HTTP {res.status_code}")
            try:
                print(json.dumps(res.json(), indent=2, ensure_ascii=False))
            except:
                print(res.text[:2000])
        except Exception as e:
            print(f"推送异常: {e}")

if __name__ == "__main__":
    main()