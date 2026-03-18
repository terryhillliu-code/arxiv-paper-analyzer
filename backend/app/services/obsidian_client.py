"""Obsidian 导出客户端。

调用 zhiwei-obsidian 服务进行 Markdown 生成和附件管理。
"""

import httpx
from typing import Any, Dict, List, Optional


class ObsidianClient:
    """Obsidian 导出服务客户端。"""

    def __init__(self, base_url: str = "http://127.0.0.1:8766"):
        """初始化客户端。

        Args:
            base_url: zhiwei-obsidian 服务地址
        """
        self.base_url = base_url
        self.timeout = 30.0

    def is_available(self) -> bool:
        """检查服务是否可用。"""
        try:
            response = httpx.get(f"{self.base_url}/health", timeout=5.0)
            return response.status_code == 200
        except Exception:
            return False

    def classify(self, title: str, content: str = "") -> Dict[str, Any]:
        """对文档进行 JD 分类。

        Args:
            title: 文档标题
            content: 文档内容

        Returns:
            分类结果
        """
        try:
            response = httpx.post(
                f"{self.base_url}/classify",
                json={"title": title, "content": content},
                timeout=10.0
            )
            response.raise_for_status()
            return response.json()
        except Exception:
            return {"jd_code": "10-19", "jd_dir": "", "category": "AI 系统"}

    def sanitize_filename(self, title: str) -> Dict[str, str]:
        """清理文件名。

        Args:
            title: 原始标题

        Returns:
            {safe_name, suggested_filename}
        """
        try:
            response = httpx.get(
                f"{self.base_url}/naming/sanitize",
                params={"title": title},
                timeout=10.0
            )
            response.raise_for_status()
            return response.json()
        except Exception:
            import re
            safe = re.sub(r'[<>:"/\\|?*]', '', title)
            safe = re.sub(r'\s+', '_', safe)[:100]
            return {"safe_name": safe, "suggested_filename": f"{safe}.md"}

    def export_paper(
        self,
        paper_data: Dict[str, Any] = None,
        analysis_json: Dict[str, Any] = None,
        report: str = "",
        pdf_path: Optional[str] = None,
        # 也支持关键字参数
        title: str = None,
        source_url: str = "",
        date: str = "",
        tags: List[str] = None,
        tier: str = "B",
        overall_rating: str = "B",
        authors: List[str] = None,
        institutions: List[str] = None,
        one_line_summary: str = "",
        knowledge_links: List[str] = None,
        action_items: List[str] = None,
    ) -> Dict[str, str]:
        """导出论文到 Obsidian。

        支持两种调用方式：
        1. export_paper(paper_data, analysis_json, report, pdf_path)
        2. export_paper(title=..., source_url=..., ...)

        Returns:
            包含 md_path 和 pdf_path 的字典
        """
        # 方式1：使用字典参数
        if paper_data is not None:
            payload = {
                "type": "paper",
                "metadata": {
                    "title": paper_data.get("title", ""),
                    "source_url": paper_data.get("arxiv_url", ""),
                    "date": paper_data.get("publish_date", ""),
                    "tags": analysis_json.get("tags", []) if analysis_json else [],
                    "tier": analysis_json.get("tier", "B") if analysis_json else "B",
                    "methodology": analysis_json.get("methodology", "") if analysis_json else "",
                    "related": analysis_json.get("knowledge_links", []) if analysis_json else [],
                    "institutions": paper_data.get("institutions", []),
                    "overall_rating": analysis_json.get("overall_rating", "B") if analysis_json else "B",
                    "authors": paper_data.get("authors", []),
                    "one_line_summary": analysis_json.get("one_line_summary", "") if analysis_json else "",
                    "action_items": analysis_json.get("action_items", []) if analysis_json else [],
                },
                "content": {
                    "report": report,
                },
            }
        # 方式2：使用关键字参数
        else:
            payload = {
                "type": "paper",
                "metadata": {
                    "title": title or "",
                    "source_url": source_url,
                    "date": date,
                    "tags": tags or [],
                    "tier": tier,
                    "overall_rating": overall_rating,
                    "authors": authors or [],
                    "institutions": institutions or [],
                    "one_line_summary": one_line_summary,
                    "knowledge_links": knowledge_links or [],
                    "action_items": action_items or [],
                },
                "content": {
                    "report": report,
                },
            }

        if pdf_path:
            payload["attachment_path"] = pdf_path

        try:
            response = httpx.post(
                f"{self.base_url}/export/obsidian",
                json=payload,
                timeout=self.timeout
            )
            response.raise_for_status()
            result = response.json()

            if result.get("success"):
                return {
                    "md_path": result.get("md_path", ""),
                    "pdf_path": result.get("attachment_path"),
                    "success": True,
                }
            else:
                return {"error": result.get("error", "导出失败"), "success": False}

        except httpx.HTTPError as e:
            return {"error": f"HTTP 错误: {str(e)}", "success": False}
        except Exception as e:
            return {"error": f"导出异常: {str(e)}", "success": False}

    def export_report(
        self,
        title: str,
        summary: str,
        source: str = "",
        pages: int = 0,
        doc_type: str = "行业研报",
        attachment_path: Optional[str] = None,
    ) -> Dict[str, str]:
        """导出研报到 Obsidian。

        Args:
            title: 报告标题
            summary: 摘要内容
            source: 来源
            pages: 页数
            doc_type: 文档类型
            attachment_path: 附件路径

        Returns:
            包含 md_path 的字典
        """
        payload = {
            "type": "report",
            "metadata": {
                "title": title,
                "source": source,
                "pages": pages,
                "doc_type": doc_type,
            },
            "content": {
                "summary": summary,
            },
        }

        if attachment_path:
            payload["attachment_path"] = attachment_path

        try:
            response = httpx.post(
                f"{self.base_url}/export/obsidian",
                json=payload,
                timeout=self.timeout
            )
            response.raise_for_status()
            result = response.json()

            if result.get("success"):
                return {
                    "md_path": result.get("md_path", ""),
                    "jd_dir": result.get("jd_dir", ""),
                    "success": True,
                }
            else:
                return {"error": result.get("error", "导出失败"), "success": False}

        except Exception as e:
            return {"error": f"导出异常: {str(e)}", "success": False}

    def export_note(
        self,
        title: str,
        content: str,
        source: str = "",
        tags: List[str] = None,
    ) -> Dict[str, str]:
        """导出通用笔记到 Obsidian。

        Args:
            title: 标题
            content: 内容
            source: 来源
            tags: 标签列表

        Returns:
            包含 md_path 的字典
        """
        payload = {
            "type": "note",
            "metadata": {
                "title": title,
                "source": source,
                "tags": tags or [],
            },
            "content": {"text": content},
        }

        try:
            response = httpx.post(
                f"{self.base_url}/export/obsidian",
                json=payload,
                timeout=self.timeout
            )
            response.raise_for_status()
            result = response.json()

            if result.get("success"):
                return {
                    "md_path": result.get("md_path", ""),
                    "jd_dir": result.get("jd_dir", ""),
                    "success": True,
                }
            else:
                return {"error": result.get("error", "导出失败"), "success": False}

        except Exception as e:
            return {"error": f"导出异常: {str(e)}", "success": False}


# 全局客户端实例
obsidian_client = ObsidianClient()