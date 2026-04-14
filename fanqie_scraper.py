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
    parser.add_argument("--max", type=int, default=50, help="每个分类最大抓取数量 (默认: 50)")
    parser.add_argument("--out", default="fanqie-snapshots.json", help="输出/读取 JSON 文件路径")
    parser.add_argument("--upload-url", help="推送接口 URL (可选)")
    parser.add_argument("--key", help="推送接口鉴权密钥 (x-market-import-key)")
    parser.add_argument("--push-only", action="store_true", help="仅推送已存在的文件，不执行抓取")
    args = parser.parse_args()

    # 内置的分类列表，避免依赖外部 JSON 文件
    categories = [
        { "group": "male_new", "name": "西方奇幻", "rankKey": "rank/1_1_1141" },
        { "group": "male_new", "name": "东方仙侠", "rankKey": "rank/1_1_1140" },
        { "group": "male_new", "name": "科幻末世", "rankKey": "rank/1_1_8" },
        { "group": "male_new", "name": "都市日常", "rankKey": "rank/1_1_261" },
        { "group": "male_new", "name": "都市修真", "rankKey": "rank/1_1_124" },
        { "group": "male_new", "name": "都市高武", "rankKey": "rank/1_1_1014" },
        { "group": "male_new", "name": "历史古代", "rankKey": "rank/1_1_273" },
        { "group": "male_new", "name": "战神赘婿", "rankKey": "rank/1_1_27" },
        { "group": "male_new", "name": "都市种田", "rankKey": "rank/1_1_263" },
        { "group": "male_new", "name": "传统玄幻", "rankKey": "rank/1_1_258" },
        { "group": "male_new", "name": "历史脑洞", "rankKey": "rank/1_1_272" },
        { "group": "male_new", "name": "悬疑脑洞", "rankKey": "rank/1_1_539" },
        { "group": "male_new", "name": "都市脑洞", "rankKey": "rank/1_1_262" },
        { "group": "male_new", "name": "玄幻脑洞", "rankKey": "rank/1_1_257" },
        { "group": "male_new", "name": "悬疑灵异", "rankKey": "rank/1_1_751" },
        { "group": "male_new", "name": "抗战谍战", "rankKey": "rank/1_1_504" },
        { "group": "male_new", "name": "游戏体育", "rankKey": "rank/1_1_746" },
        { "group": "male_new", "name": "动漫衍生", "rankKey": "rank/1_1_718" },
        { "group": "male_new", "name": "男频衍生", "rankKey": "rank/1_1_1016" },
        { "group": "female_new", "name": "古风世情", "rankKey": "rank/0_1_1139" },
        { "group": "female_new", "name": "科幻末世", "rankKey": "rank/0_1_8" },
        { "group": "female_new", "name": "游戏体育", "rankKey": "rank/0_1_746" },
        { "group": "female_new", "name": "女频衍生", "rankKey": "rank/0_1_1015" },
        { "group": "female_new", "name": "玄幻言情", "rankKey": "rank/0_1_248" },
        { "group": "female_new", "name": "种田", "rankKey": "rank/0_1_23" },
        { "group": "female_new", "name": "年代", "rankKey": "rank/0_1_79" },
        { "group": "female_new", "name": "现言脑洞", "rankKey": "rank/0_1_267" },
        { "group": "female_new", "name": "宫斗宅斗", "rankKey": "rank/0_1_246" },
        { "group": "female_new", "name": "悬疑脑洞", "rankKey": "rank/0_1_539" },
        { "group": "female_new", "name": "古言脑洞", "rankKey": "rank/0_1_253" },
        { "group": "female_new", "name": "快穿", "rankKey": "rank/0_1_24" },
        { "group": "female_new", "name": "青春甜宠", "rankKey": "rank/0_1_749" },
        { "group": "female_new", "name": "星光璀璨", "rankKey": "rank/0_1_745" },
        { "group": "female_new", "name": "女频悬疑", "rankKey": "rank/0_1_747" },
        { "group": "female_new", "name": "职场婚恋", "rankKey": "rank/0_1_750" },
        { "group": "female_new", "name": "豪门总裁", "rankKey": "rank/0_1_748" },
        { "group": "female_new", "name": "民国言情", "rankKey": "rank/0_1_1017" }
    ]

    date_str = datetime.datetime.now().strftime("%Y-%m-%d")
    
    if args.push_only:
        if not args.upload_url:
            print("❌ 错误: --push-only 必须配合 --upload-url 使用")
            sys.exit(1)
            
        print(f"模式: 仅推送已存在的数据 ({args.out})")
        try:
            with open(args.out, "r", encoding="utf-8") as f:
                payload = json.load(f)
                
            # 简单的格式校验
            if "snapshots" not in payload:
                print(f"❌ 错误: 读取到的 {args.out} 数据格式不正确 (缺失 snapshots 字段)")
                sys.exit(1)
                
            print(f"✅ 成功读取到数据文件，共包含 {len(payload.get('snapshots', []))} 个分类")
        except FileNotFoundError:
            print(f"❌ 错误: 找不到文件 {args.out}。请先执行抓取命令，或指定正确的 --out 路径")
            sys.exit(1)
        except json.JSONDecodeError:
            print(f"❌ 错误: {args.out} 不是合法的 JSON 格式")
            sys.exit(1)
        except Exception as e:
            print(f"❌ 错误: 读取文件失败 {e}")
            sys.exit(1)
            
    else:
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
                
                # 使用配置的最大抓取数量
                if args.max and args.max > 0:
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
            print(f"✅ 已携带 x-market-import-key 认证头")
            
        try:
            print(f"⏳ 正在构建请求并发送...")
            start_time = datetime.datetime.now()
            # 注意：如果本地服务特别慢或者需要导入的数据特别大，可以适当放大 timeout，这里放大到 120 秒
            res = requests.post(args.upload_url, headers=push_headers, json={"payload": payload}, timeout=120)
            end_time = datetime.datetime.now()
            cost_secs = (end_time - start_time).total_seconds()
            print(f"✅ 推送请求完成！耗时: {cost_secs:.2f} 秒")
            print(f"响应状态码: HTTP {res.status_code}")
            try:
                print("响应内容: " + json.dumps(res.json(), indent=2, ensure_ascii=False))
            except:
                print("响应内容(原始): " + res.text[:2000])
        except requests.exceptions.Timeout:
            print("❌ 推送超时！(等待了 120 秒没有响应)")
            print("可能原因：")
            print("1. 服务端导入数据过多，处理过慢。可以检查服务端日志看看是不是还在处理。")
            print("2. 网络连通性问题。")
        except requests.exceptions.ConnectionError:
            print("❌ 连接被拒绝！")
            print(f"请检查服务 {args.upload_url} 是否已启动并且可以通过该地址访问。")
            if "127.0.0.1" in args.upload_url and "https://" in args.upload_url:
                print("⚠️ 提示：你好像在本地使用了 https://127.0.0.1，如果是本地测试，通常应该是 http://127.0.0.1")
        except Exception as e:
            print(f"❌ 推送发生未知异常: {e}")

if __name__ == "__main__":
    main()