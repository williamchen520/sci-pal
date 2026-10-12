"""
Protocols.io API Client: 实验方法在线搜索
V1.0 - 混合检索系统扩展模块

对接 protocols.io 公开 REST API v3，实时搜索 25k+ 结构化实验协议。
不需要下载数据、不需要建库，直接通过 API 实时检索。

跟本地搜索和 NCBI 在线搜索结果格式统一，方便 hybrid_retriever 合并去重。

认证方式: Bearer Token（需要在 protocols.io 注册账号后获取）
  1. 注册 https://www.protocols.io
  2. 在 Settings → API 中创建 Client Access Token
  3. 设置环境变量: export SCIPAL_PROTOCOLS_IO_TOKEN=your_token_here

环境变量:
  SCIPAL_PROTOCOLS_IO_TOKEN  - protocols.io API access token（必填，否则不启用）
  SCIPAL_PROTOCOLS_IO_ENABLED - "true"/"false"，是否启用（默认有token就启用）
"""

import time
import hashlib
import json
import os
from pathlib import Path
from typing import Dict, List, Optional

import requests


# ============================================================
# Protocols.io API 配置
# ============================================================
PROTOCOLS_IO_BASE = "https://www.protocols.io/api/v3"

# 速率限制（protocols.io 未明确限制，保守设为 0.5 秒/请求）
RATE_LIMIT_SECONDS = 0.5

# 重试配置
MAX_RETRIES = 3
RETRY_DELAY = 5

# 缓存目录
CACHE_DIR = Path("data/protocols_io_cache")

# 单次搜索最大结果数
MAX_RESULTS_PER_SEARCH = 50


class ProtocolsIOResult:
    """
    统一格式的 protocols.io 搜索结果。
    跟论文结果格式兼容，方便混合检索合并。
    """

    def __init__(
        self,
        protocol_id: int,
        title: str,
        authors: str = "",
        description: str = "",
        doi: str = "",
        uri: str = "",
        url: str = "",
        number_of_steps: int = 0,
        published_on: Optional[int] = None,
        created_on: Optional[int] = None,
        creator_name: str = "",
        creator_username: str = "",
        source: str = "protocols_io",
        is_protocol: bool = True,
    ):
        self.protocol_id = protocol_id
        self.title = title
        self.authors = authors
        self.description = description
        self.doi = doi
        self.uri = uri
        self.url = url or f"https://www.protocols.io/view/{uri}"
        self.number_of_steps = number_of_steps
        self.published_on = published_on
        self.created_on = created_on
        self.creator_name = creator_name
        self.creator_username = creator_username
        self.source = source
        self.is_protocol = is_protocol

        # 兼容论文格式的 year 字段
        self.year = None
        if published_on and published_on > 0:
            try:
                self.year = time.gmtime(published_on).tm_year
            except Exception:
                pass

    def to_dict(self) -> Dict:
        """转为字典，方便 JSON 序列化和混合检索处理。"""
        return {
            "id": f"protocols_io_{self.protocol_id}",
            "protocol_id": self.protocol_id,
            "title": self.title,
            "authors": self.authors,
            "abstract": self.description,  # 兼容论文格式的 abstract 字段
            "description": self.description,
            "doi": self.doi,
            "uri": self.uri,
            "url": self.url,
            "number_of_steps": self.number_of_steps,
            "published_on": self.published_on,
            "created_on": self.created_on,
            "creator_name": self.creator_name,
            "creator_username": self.creator_username,
            "source": self.source,
            "is_protocol": self.is_protocol,
            "has_fulltext": True,  # protocols.io 的协议都是完整结构化的
            "in_local_db": False,
        }

    @classmethod
    def from_api_response(cls, item: Dict) -> "ProtocolsIOResult":
        """从 protocols.io API 响应解析为统一格式。"""
        # 作者列表
        authors_list = []
        for a in item.get("authors", []):
            name = a.get("name", "")
            if name:
                authors_list.append(name)
        creator = item.get("creator", {})
        if not authors_list and creator.get("name"):
            authors_list.append(creator["name"])

        # 时间戳转年份
        published_on = item.get("published_on")
        year = None
        if published_on and published_on > 0:
            try:
                year = time.gmtime(published_on).tm_year
            except Exception:
                pass

        return cls(
            protocol_id=item.get("id", 0),
            title=item.get("title", "").strip(),
            authors=", ".join(authors_list),
            description=item.get("description", "") or "",
            doi=item.get("doi", "") or "",
            uri=item.get("uri", "") or "",
            url=item.get("url", "") or f"https://www.protocols.io/view/{item.get('uri', '')}",
            number_of_steps=item.get("number_of_steps") or 0,
            published_on=published_on,
            created_on=item.get("created_on"),
            creator_name=creator.get("name", ""),
            creator_username=creator.get("username", ""),
        )


class ProtocolsIOClient:
    """
    protocols.io API 客户端。

    支持搜索公开协议、获取协议详情。
    内置缓存、限速、重试机制。

    Usage:
        client = ProtocolsIOClient(token="your_token")
        results = client.search("western blot", max_results=10)
        for r in results:
            print(r.title, r.url)
    """

    def __init__(
        self,
        token: Optional[str] = None,
        cache_dir: Optional[Path] = None,
        rate_limit: float = RATE_LIMIT_SECONDS,
        max_retries: int = MAX_RETRIES,
    ):
        self.token = token or os.environ.get("SCIPAL_PROTOCOLS_IO_TOKEN", "")
        self.cache_dir = cache_dir or CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.rate_limit = rate_limit
        self.max_retries = max_retries
        self._last_request_time = 0.0
        self._session = requests.Session()
        self._session.headers.update({
            "Accept": "application/json",
            "User-Agent": "Sci-Pal-ProtocolsIO-Client/1.0",
        })
        if self.token:
            self._session.headers.update({
                "Authorization": f"Bearer {self.token}",
            })

    @property
    def is_enabled(self) -> bool:
        """是否启用（有 token 且未被环境变量禁用）。"""
        if os.environ.get("SCIPAL_PROTOCOLS_IO_ENABLED", "").lower() == "false":
            return False
        return bool(self.token)

    def _rate_limit_wait(self):
        """限速等待。"""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.rate_limit:
            time.sleep(self.rate_limit - elapsed)
        self._last_request_time = time.time()

    def _cache_key(self, prefix: str, **kwargs) -> str:
        """生成缓存键。"""
        raw = f"{prefix}:{json.dumps(kwargs, sort_keys=True)}"
        return hashlib.md5(raw.encode()).hexdigest()

    def _cache_get(self, key: str) -> Optional[Dict]:
        """从缓存读取。"""
        cache_file = self.cache_dir / f"{key}.json"
        if cache_file.exists():
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # 缓存有效期 7 天
                if time.time() - data.get("_cached_at", 0) < 7 * 24 * 3600:
                    return data.get("payload")
            except Exception:
                pass
        return None

    def _cache_set(self, key: str, payload: Dict):
        """写入缓存。"""
        cache_file = self.cache_dir / f"{key}.json"
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump({"_cached_at": time.time(), "payload": payload}, f, ensure_ascii=False)
        except Exception:
            pass

    def _request(self, endpoint: str, params: Optional[Dict] = None) -> Optional[Dict]:
        """
        发送 API 请求，内置重试和限速。
        返回解析后的 JSON，失败返回 None。
        """
        if not self.is_enabled:
            print("  ⚠️  Protocols.io 未启用（缺少 token）")
            return None

        url = f"{PROTOCOLS_IO_BASE}/{endpoint.lstrip('/')}"

        for attempt in range(self.max_retries):
            try:
                self._rate_limit_wait()
                resp = self._session.get(url, params=params, timeout=30)
                resp.raise_for_status()
                data = resp.json()

                # protocols.io 用 status_code 表示状态，0=成功
                status_code = data.get("status_code", 0)
                if status_code != 0:
                    print(f"  ⚠️  Protocols.io API 错误 status_code={status_code}")
                    return None

                return data

            except requests.exceptions.HTTPError as e:
                if e.response is not None and e.response.status_code == 401:
                    print("  ❌ Protocols.io token 无效或已过期")
                    return None
                if e.response is not None and e.response.status_code == 429:
                    print(f"  ⏳ Protocols.io 限流，等待 {RETRY_DELAY}秒后重试...")
                    time.sleep(RETRY_DELAY)
                    continue
                print(f"  ⚠️  Protocols.io HTTP 错误: {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(RETRY_DELAY)
                    continue
                return None
            except requests.exceptions.RequestException as e:
                print(f"  ⚠️  Protocols.io 请求失败 (尝试 {attempt+1}/{self.max_retries}): {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(RETRY_DELAY)
                    continue
                return None
            except Exception as e:
                print(f"  ⚠️  Protocols.io 未知错误: {e}")
                return None

        return None

    def search(
        self,
        query: str,
        max_results: int = 10,
        order_field: str = "activity",
        order_dir: str = "desc",
    ) -> List[ProtocolsIOResult]:
        """
        搜索公开协议。

        Args:
            query: 搜索关键词
            max_results: 最大返回结果数（最多50）
            order_field: 排序字段 activity/date/name/id
            order_dir: 排序方向 asc/desc

        Returns:
            ProtocolsIOResult 列表
        """
        if not self.is_enabled:
            return []

        if not query or not query.strip():
            return []

        max_results = min(max_results, MAX_RESULTS_PER_SEARCH)
        query = query.strip()

        # 检查缓存
        cache_key = self._cache_key("search", q=query, n=max_results, of=order_field, od=order_dir)
        cached = self._cache_get(cache_key)
        if cached is not None:
            return [ProtocolsIOResult.from_api_response(item) for item in cached.get("items", [])]

        print(f"  🔍 Protocols.io 搜索: '{query}' (最多{max_results}条)")

        params = {
            "filter": "public",
            "key": query,
            "page_size": max_results,
            "page_id": 1,
            "order_field": order_field,
            "order_dir": order_dir,
        }

        data = self._request("/protocols", params=params)
        if not data:
            return []

        items = data.get("items", [])
        pagination = data.get("pagination", {})
        total = pagination.get("total_results", len(items))

        print(f"  ✅ Protocols.io 找到 {total} 条，返回 {len(items)} 条")

        # 写入缓存
        self._cache_set(cache_key, {"items": items})

        return [ProtocolsIOResult.from_api_response(item) for item in items]

    def get_protocol(self, protocol_id: int) -> Optional[Dict]:
        """
        获取协议详情（包含完整步骤、试剂等）。

        Args:
            protocol_id: 协议 ID

        Returns:
            协议详情字典，失败返回 None
        """
        if not self.is_enabled:
            return None

        cache_key = self._cache_key("detail", id=protocol_id)
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        print(f"  📄 Protocols.io 获取协议详情: id={protocol_id}")

        data = self._request(f"/protocols/{protocol_id}")
        if not data:
            return None

        self._cache_set(cache_key, data)
        return data

    def search_and_format(
        self,
        query: str,
        max_results: int = 10,
    ) -> List[Dict]:
        """
        搜索并返回字典列表（方便混合检索直接使用）。

        Args:
            query: 搜索关键词
            max_results: 最大返回数

        Returns:
            字典列表，每个字典包含统一格式的协议信息
        """
        results = self.search(query, max_results=max_results)
        return [r.to_dict() for r in results]


# ============================================================
# 便捷函数
# ============================================================
_default_client: Optional[ProtocolsIOClient] = None


def get_protocols_io_client() -> ProtocolsIOClient:
    """获取全局单例客户端。"""
    global _default_client
    if _default_client is None:
        _default_client = ProtocolsIOClient()
    return _default_client


def search_protocols_io(query: str, max_results: int = 10) -> List[Dict]:
    """
    便捷函数：搜索 protocols.io 公开协议。

    Args:
        query: 搜索关键词
        max_results: 最大返回数

    Returns:
        统一格式的字典列表
    """
    client = get_protocols_io_client()
    return client.search_and_format(query, max_results=max_results)


def is_protocols_io_available() -> bool:
    """检查 protocols.io 是否可用（已配置 token 且未禁用）。"""
    return get_protocols_io_client().is_enabled


# ============================================================
# 命令行测试
# ============================================================
if __name__ == "__main__":
    import sys

    # Windows 控制台编码修复
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    if len(sys.argv) < 2:
        print("用法: python protocols_io_client.py <搜索关键词> [最大结果数]")
        print("示例: python protocols_io_client.py 'western blot' 5")
        print()
        print("需要先设置环境变量:")
        print("  export SCIPAL_PROTOCOLS_IO_TOKEN=your_token_here")
        sys.exit(1)

    query = sys.argv[1]
    max_n = int(sys.argv[2]) if len(sys.argv) > 2 else 5

    client = ProtocolsIOClient()

    if not client.is_enabled:
        print("❌ Protocols.io 未启用，请设置 SCIPAL_PROTOCOLS_IO_TOKEN 环境变量")
        print("   获取 token: https://www.protocols.io → Settings → API")
        sys.exit(1)

    print(f"🔍 搜索: '{query}' (最多{max_n}条)")
    print("=" * 70)

    results = client.search(query, max_results=max_n)

    if not results:
        print("未找到结果")
    else:
        for i, r in enumerate(results, 1):
            print(f"\n[{i}] {r.title}")
            print(f"    作者: {r.authors or '未知'}")
            print(f"    步骤数: {r.number_of_steps}")
            print(f"    DOI: {r.doi or '无'}")
            print(f"    链接: {r.url}")
            if r.description:
                desc = r.description[:120] + "..." if len(r.description) > 120 else r.description
                print(f"    描述: {desc}")

    print("\n" + "=" * 70)
    print(f"共返回 {len(results)} 条结果")
