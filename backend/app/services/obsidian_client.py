"""Obsidian 导出客户端。

调用 zhiwei-obsidian 服务进行 Markdown 生成和附件管理。
"""

import httpx
from typing import Any, Dict, Optional


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

    def export_paper(
        self,
        paper_data: Dict[str, Any],
        analysis_json: Dict[str, Any],
        report: str,
        pdf_path: Optional[str] = None,
    ) -> Dict[str, str]:
        """导出论文到 Obsidian。

        Args:
            paper_data: 论文基础信息
            analysis_json: 分析结果
            report: 分析报告
            pdf_path: PDF 源文件路径（可选）

        Returns:
            包含 md_path 和 pdf_path 的字典
        """
        # 构建请求
        payload = {
            "type": "paper",
            "metadata": {
                "title": paper_data.get("title", ""),
                "source_url": paper_data.get("arxiv_url", ""),
                "date": paper_data.get("publish_date", ""),
                "tags": analysis_json.get("tags", []),
                "tier": analysis_json.get("tier", "B"),
                "methodology": analysis_json.get("methodology", ""),
                "related": analysis_json.get("knowledge_links", []),
                "institutions": paper_data.get("institutions", []),
                "overall_rating": analysis_json.get("overall_rating", "B"),
            },
            "content": {
                "report": report,
                "one_line_summary": analysis_json.get("one_line_summary", ""),
                "action_items": analysis_json.get("action_items", []),
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
                }
            else:
                return {"error": result.get("error", "导出失败")}

        except httpx.HTTPError as e:
            return {"error": f"HTTP 错误: {str(e)}"}
        except Exception as e:
            return {"error": f"导出异常: {str(e)}"}

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
                }
            else:
                return {"error": result.get("error", "导出失败")}

        except Exception as e:
            return {"error": f"导出异常: {str(e)}"}

    def classify(self, title: str, content: str = "") -> Dict[str, str]:
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


# 全局客户端实例
obsidian_client = ObsidianClient()