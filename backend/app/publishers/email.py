"""
邮件发布器

通过 SMTP 发送邮件。
"""

import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict, List, Optional

from .base import BasePublisher, PublishResult

logger = logging.getLogger(__name__)


class EmailPublisher(BasePublisher):
    """邮件发布器"""

    name = "email"
    requires_auth = True

    def _validate_config(self) -> None:
        """验证配置"""
        required = ["smtp_host", "smtp_port", "sender", "recipients"]
        missing = [key for key in required if key not in self.config]
        if missing:
            raise ValueError(f"缺少必需配置: {', '.join(missing)}")

        # 验证端口
        port = self.config.get("smtp_port")
        if not isinstance(port, int) or port <= 0:
            raise ValueError("smtp_port 必须是正整数")

        # 验证收件人
        recipients = self.config.get("recipients", [])
        if not isinstance(recipients, list) or len(recipients) == 0:
            raise ValueError("recipients 必须是非空列表")

    async def publish(
        self,
        content: str,
        title: Optional[str] = None,
        papers: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> PublishResult:
        """
        发送邮件

        Args:
            content: 邮件正文（纯文本）
            title: 邮件主题
            papers: 相关论文列表
            **kwargs: 额外参数
                - html_content: HTML 格式正文
                - cc: 抄送列表
                - attachments: 附件路径列表

        Returns:
            PublishResult 对象
        """
        try:
            import aiosmtplib

            # 构建邮件
            msg = MIMEMultipart("alternative")
            msg["Subject"] = title or "ArXiv 论文推送"
            msg["From"] = self.config["sender"]
            msg["To"] = ", ".join(self.config["recipients"])

            # 抄送
            if kwargs.get("cc"):
                msg["Cc"] = ", ".join(kwargs["cc"])

            # 纯文本正文
            msg.attach(MIMEText(content, "plain", "utf-8"))

            # HTML 正文（可选）
            html_content = kwargs.get("html_content")
            if html_content:
                msg.attach(MIMEText(html_content, "html", "utf-8"))

            # 发送
            recipients = self.config["recipients"] + (kwargs.get("cc") or [])

            await aiosmtplib.send(
                msg,
                hostname=self.config["smtp_host"],
                port=self.config["smtp_port"],
                username=self.config.get("smtp_user"),
                password=self.config.get("smtp_password"),
                sender=self.config["sender"],
                recipients=recipients,
                use_tls=self.config.get("use_tls", True),
            )

            logger.info(f"邮件发送成功: {self.config['recipients']}")
            return PublishResult(
                success=True,
                platform=self.name,
                metadata={"recipients": self.config["recipients"]}
            )

        except ImportError:
            logger.error("aiosmtplib 未安装，请运行: pip install aiosmtplib")
            return PublishResult(
                success=False,
                platform=self.name,
                error="缺少依赖: aiosmtplib"
            )
        except Exception as e:
            logger.error(f"邮件发送失败: {e}")
            return PublishResult(
                success=False,
                platform=self.name,
                error=str(e)
            )

    async def test_connection(self) -> bool:
        """
        测试 SMTP 连接

        Returns:
            True 如果连接成功
        """
        try:
            import aiosmtplib

            await aiosmtplib.SMTP(
                hostname=self.config["smtp_host"],
                port=self.config["smtp_port"],
                use_tls=self.config.get("use_tls", True),
            ).connect()

            return True
        except ImportError:
            logger.warning("aiosmtplib 未安装")
            return False
        except Exception as e:
            logger.warning(f"SMTP 连接测试失败: {e}")
            return False

    def build_html_content(
        self,
        title: str,
        content: str,
        papers: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """
        构建 HTML 邮件内容

        Args:
            title: 标题
            content: 正文
            papers: 论文列表

        Returns:
            HTML 字符串
        """
        html_parts = [
            "<!DOCTYPE html>",
            "<html>",
            "<head>",
            '<meta charset="utf-8">',
            "<style>",
            "body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; max-width: 800px; margin: 0 auto; padding: 20px; }",
            "h1 { color: #1a1a1a; border-bottom: 2px solid #e0e0e0; padding-bottom: 10px; }",
            "h2 { color: #2c3e50; margin-top: 30px; }",
            ".paper { background: #f9f9f9; border-left: 4px solid #3498db; padding: 15px; margin: 15px 0; }",
            ".paper-title { font-weight: bold; color: #2980b9; }",
            ".paper-meta { font-size: 0.9em; color: #666; }",
            "a { color: #3498db; text-decoration: none; }",
            "a:hover { text-decoration: underline; }",
            "</style>",
            "</head>",
            "<body>",
            f"<h1>{title}</h1>",
            f"<div>{content}</div>",
        ]

        # 论文列表
        if papers:
            html_parts.append("<h2>相关论文</h2>")
            for paper in papers:
                paper_title = paper.get("title", "未知标题")
                paper_url = paper.get("arxiv_url", "")
                authors = ", ".join(paper.get("authors", [])[:3])
                if len(paper.get("authors", [])) > 3:
                    authors += " 等"
                summary = paper.get("summary", "")[:200]

                html_parts.append('<div class="paper">')
                if paper_url:
                    html_parts.append(f'<div class="paper-title"><a href="{paper_url}">{paper_title}</a></div>')
                else:
                    html_parts.append(f'<div class="paper-title">{paper_title}</div>')
                html_parts.append(f'<div class="paper-meta">{authors}</div>')
                if summary:
                    html_parts.append(f'<p>{summary}...</p>')
                html_parts.append("</div>")

        html_parts.extend(["</body>", "</html>"])
        return "\n".join(html_parts)