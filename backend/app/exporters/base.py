"""
导出器基类

定义导出器的通用接口和结果类型。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ExportResult:
    """导出结果"""

    success: bool
    format: str
    content: Optional[str] = None
    file_path: Optional[str] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class BaseExporter(ABC):
    """
    导出器基类

    所有导出器必须继承此类并实现 export_paper 和 export_papers 方法。
    """

    name: str = "base"
    """导出器名称"""

    file_extension: str = ".txt"
    """输出文件扩展名"""

    @abstractmethod
    def export_paper(self, paper: Dict[str, Any]) -> str:
        """
        导出单篇论文

        Args:
            paper: 论文数据字典，包含 title, authors, abstract 等字段

        Returns:
            导出格式的字符串内容
        """
        pass

    def export_papers(self, papers: List[Dict[str, Any]]) -> str:
        """
        导出多篇论文

        默认实现：遍历调用 export_paper 并用换行分隔。
        子类可以重写此方法以提供更优化的批量导出逻辑。

        Args:
            papers: 论文数据列表

        Returns:
            导出格式的字符串内容
        """
        entries = [self.export_paper(p) for p in papers]
        return "\n\n".join(entries)

    def export_to_file(
        self,
        papers: List[Dict[str, Any]],
        file_path: str
    ) -> ExportResult:
        """
        导出论文到文件

        Args:
            papers: 论文数据列表
            file_path: 目标文件路径

        Returns:
            ExportResult 对象
        """
        try:
            content = self.export_papers(papers)

            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)

            return ExportResult(
                success=True,
                format=self.name,
                content=content,
                file_path=file_path,
                metadata={"paper_count": len(papers)}
            )
        except Exception as e:
            return ExportResult(
                success=False,
                format=self.name,
                error=str(e)
            )

    def _get_field(self, paper: Dict[str, Any], field: str, default: Any = None) -> Any:
        """
        安全获取论文字段

        支持从 paper 对象或其属性获取值。

        Args:
            paper: 论文数据（字典或对象）
            field: 字段名
            default: 默认值

        Returns:
            字段值
        """
        if isinstance(paper, dict):
            return paper.get(field, default)
        else:
            return getattr(paper, field, default)