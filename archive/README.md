# Archive

存档的 FastAPI + 爬虫模块，供后续复用。

| 文件 | 说明 |
|---|---|
| `main.py` | FastAPI 后端，含所有 REST API |
| `database.py` | SQLite 异步 CRUD 层 |
| `demo_data.py` | FastAPI 版演示数据（30 条） |
| `scrapers/boss.py` | Boss直聘 Playwright 爬虫 |
| `scrapers/shixiseng.py` | 实习僧 Playwright 爬虫 |
| `scrapers/stealth.py` | 反检测工具（随机 UA/视口/鼠标轨迹） |

## 恢复方法

```bash
# 恢复爬虫模块
cp archive/scrapers/* scrapers/
pip install playwright patchright
playwright install chromium

# 恢复 FastAPI 后端
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```
