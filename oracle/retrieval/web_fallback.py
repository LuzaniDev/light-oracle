from typing import List, Dict, Optional
import urllib.parse
import json
import urllib.request
import urllib.error
import ssl


class WebFallback:
    def __init__(self, max_results: int = 5):
        self.max_results = max_results
        self._ctx = ssl.create_default_context()
        self._ctx.check_hostname = False
        self._ctx.verify_mode = ssl.CERT_NONE

    def search(self, query: str) -> List[Dict]:
        try:
            return self._search_duckduckgo(query)
        except Exception:
            try:
                return self._search_searx(query)
            except Exception:
                return []

    def _search_duckduckgo(self, query: str) -> List[Dict]:
        encoded = urllib.parse.quote(query)
        url = f"https://lite.duckduckgo.com/lite/?q={encoded}"
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        resp = urllib.request.urlopen(req, timeout=10, context=self._ctx)
        html = resp.read().decode("utf-8", errors="replace")

        results = []
        import re
        links = re.findall(r'<a[^>]*href="([^"]+)"[^>]*class="result-link"[^>]*>(.*?)</a>', html, re.DOTALL)
        snippets = re.findall(r'<td[^>]*class="result-snippet"[^>]*>(.*?)</td>', html, re.DOTALL)

        for i, (href, title) in enumerate(links[:self.max_results]):
            title_clean = re.sub(r'<[^>]+>', '', title).strip()
            snippet = ""
            if i < len(snippets):
                snippet = re.sub(r'<[^>]+>', '', snippets[i]).strip()
            results.append({
                "title": title_clean or query,
                "url": href,
                "snippet": snippet,
                "source": "duckduckgo",
            })
        return results

    def _search_searx(self, query: str) -> List[Dict]:
        instances = [
            "https://searx.be",
            "https://search.sapti.me",
            "https://searx.ninja",
        ]
        for instance in instances:
            try:
                encoded = urllib.parse.quote(query)
                url = f"{instance}/search?q={encoded}&format=json"
                req = urllib.request.Request(url, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                })
                resp = urllib.request.urlopen(req, timeout=10, context=self._ctx)
                data = json.loads(resp.read().decode("utf-8"))
                results = []
                for r in data.get("results", [])[:self.max_results]:
                    results.append({
                        "title": r.get("title", query),
                        "url": r.get("url", ""),
                        "snippet": r.get("content", ""),
                        "source": instance,
                    })
                if results:
                    return results
            except Exception:
                continue
        return []

    def fetch_page_text(self, url: str, max_chars: int = 3000) -> str:
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })
            resp = urllib.request.urlopen(req, timeout=10, context=self._ctx)
            html = resp.read().decode("utf-8", errors="replace")
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
                tag.decompose()
            text = soup.get_text(separator="\n", strip=True)
            return text[:max_chars]
        except Exception:
            return ""

    def search_and_fetch(self, query: str) -> List[Dict]:
        results = self.search(query)
        for r in results:
            page_text = self.fetch_page_text(r["url"])
            if page_text:
                r["content"] = page_text
        return results
