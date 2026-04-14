# fanqielaqu

在本地（能访问番茄的电脑）抓取番茄排行榜，输出 UTF-8 JSON（顶层包含 date 与 snapshots），并生成质量报告；可选自动 POST 上传到你的后台接口。

## 0. 前置要求

- Node.js 22+（建议）

## 1. 一键导出（本地抓取）

```bash
npm run fanqie:export -- --out fanqie-snapshots.json
```

生成：
- fanqie-snapshots.json
- fanqie-snapshots.report.json

可选：限制每分类最多抓取数量（不传则不固定截断，按实际抓到输出）

```bash
npm run fanqie:export -- --max 30 --out fanqie-snapshots.json
```

## 2. 抓取并自动 POST 到服务端

使用 `fanqie:push` 脚本，抓取完成后自动通过 POST 接口推送给服务端。

```bash
# 本地测试
npm run fanqie:push -- \
  --upload-url "http://127.0.0.1:3000/api/admin/seed-bank/import-today/push" \
  --key "你的密钥" \
  --max 10

# 线上推送
npm run fanqie:push -- \
  --upload-url "https://你的域名/api/admin/seed-bank/import-today/push" \
  --key "你的密钥"
```

这会自动发送如下格式的请求体（Content-Type: application/json），并在 header 携带 `x-market-import-key: 你的密钥`：

```json
{
  "payload": {
    "date": "2026-04-14",
    "snapshots": [...]
  }
}
```

## 3. 输出格式

```json
{
  "date": "YYYY-MM-DD",
  "snapshots": [
    {
      "rankKey": "rank/x_x_x",
      "group": "male_new|female_new",
      "name": "分类名",
      "books": [
        {
          "platformId": "番茄 bookId（稳定）",
          "rank": 1,
          "isNew": true,
          "title": "书名",
          "author": "作者",
          "category": "分类名",
          "intro": "简介",
          "coverUrl": "https://...fqnovelpic...image?...",
          "wordCount": 123456
        }
      ]
    }
  ]
}
```

