"""
分析防护层模块。

提供多层安全检查，防止：
1. Tier 通胀
2. 数据捏造
3. Prompt-输入不匹配
4. 其他质量问题

使用方法：
    from app.services.guardrails import AnalysisGuardrail

    guard = AnalysisGuardrail()

    # 分析前检查
    check_result = guard.pre_analysis_check(quick_mode, content, abstract)
    if not check_result.valid:
        logger.warning(check_result.message)

    # 分析后验证
    post_check = guard.post_analysis_validate(analysis_json, quick_mode)
"""

import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class CheckResult:
    """检查结果"""
    valid: bool
    message: str
    warnings: List[str] = None

    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []


class AnalysisGuardrail:
    """分析防护层

    提供多层安全检查：
    1. 内容长度检查
    2. Prompt-输入匹配检查
    3. Tier 分布监控
    4. 数据质量验证
    """

    # 配置常量
    QUICK_MODE_MAX_CONTENT_LENGTH = 5000  # 快速模式最大内容长度
    TIER_A_ALERT_THRESHOLD = 0.20  # Tier A 预警阈值
    MIN_ABSTRACT_LENGTH = 100  # 最小摘要长度

    # 公式符号（用于检测捏造）
    FORMULA_PATTERNS = [
        r'\$[^$]+\$',  # 行内公式 $...$
        r'\\\[.*?\\\]',  # 独立公式 \[...\]
        r'\\begin{equation}',  # LaTeX 公式环境
        r'\\\\sum', r'\\\\int', r'\\\\frac',  # LaTeX 命令
    ]

    def pre_analysis_check(
        self,
        quick_mode: bool,
        content: str,
        abstract: str,
        title: str = "",
    ) -> CheckResult:
        """分析前检查

        Args:
            quick_mode: 是否快速模式
            content: 待分析内容
            abstract: 摘要（备用）
            title: 论文标题

        Returns:
            CheckResult: 检查结果
        """
        warnings = []

        # 1. 内容长度检查
        if quick_mode:
            if len(content) > self.QUICK_MODE_MAX_CONTENT_LENGTH:
                warnings.append(
                    f"快速模式内容过长 ({len(content)} > {self.QUICK_MODE_MAX_CONTENT_LENGTH})，"
                    f"建议截断或检查是否误用全文"
                )
                # 自动截断
                content = content[:self.QUICK_MODE_MAX_CONTENT_LENGTH]

        # 2. 摘要有效性检查
        if quick_mode and len(abstract) < self.MIN_ABSTRACT_LENGTH:
            warnings.append(
                f"摘要过短 ({len(abstract)} < {self.MIN_ABSTRACT_LENGTH})，"
                f"可能影响分析质量"
            )

        # 3. Prompt-输入匹配检查
        if quick_mode:
            # 快速模式不应有公式符号
            for pattern in self.FORMULA_PATTERNS:
                if re.search(pattern, content):
                    warnings.append(
                        f"快速模式内容包含公式符号 ({pattern})，"
                        f"可能是全文而非摘要"
                    )
                    break

        # 4. 内容来源验证
        if quick_mode and content == abstract:
            logger.info("✅ 快速模式内容来源正确（摘要）")
        elif quick_mode and content != abstract and len(content) > len(abstract):
            warnings.append(
                f"快速模式内容 != 摘要，长度差异 {len(content) - len(abstract)}"
            )

        return CheckResult(
            valid=len(warnings) == 0,
            message=f"分析前检查完成，发现 {len(warnings)} 个警告",
            warnings=warnings,
        )

    def post_analysis_validate(
        self,
        analysis_json: Dict[str, Any],
        quick_mode: bool,
        content_used: str = "",
    ) -> CheckResult:
        """分析后验证

        Args:
            analysis_json: 分析结果 JSON
            quick_mode: 是否快速模式
            content_used: 实际使用的内容

        Returns:
            CheckResult: 验证结果
        """
        warnings = []

        # 1. Tier 合理性检查
        tier = analysis_json.get("tier", "B")
        if tier == "A":
            # Tier A 需要额外验证
            key_contributions = analysis_json.get("key_contributions", [])
            if len(key_contributions) < 2:
                warnings.append(
                    "Tier A 论文应有至少 2 条主要贡献，当前只有 "
                    f"{len(key_contributions)} 条"
                )

            # 检查是否有 SOTA 声明
            one_line_summary = analysis_json.get("one_line_summary", "")
            metrics = analysis_json.get("metrics", [])
            if not metrics and "提升" not in one_line_summary and "突破" not in one_line_summary:
                warnings.append(
                    "Tier A 论文通常有性能突破或指标提升，但未检测到相关内容"
                )

        # 2. 快速模式不应有复杂 outline
        if quick_mode:
            outline = analysis_json.get("outline", [])
            if outline and len(outline) > 3:
                # 检查 outline 是否有深度嵌套（可能是捏造）
                max_depth = self._get_outline_depth(outline)
                if max_depth > 2:
                    warnings.append(
                        f"快速模式 outline 深度 {max_depth} > 2，"
                        f"可能是捏造（摘要不应有完整大纲）"
                    )

            # 快速模式不应有公式
            outline_str = str(analysis_json.get("outline", ""))
            for pattern in self.FORMULA_PATTERNS:
                if re.search(pattern, outline_str):
                    warnings.append(
                        f"快速模式结果包含公式符号 ({pattern})，"
                        f"明显是捏造（摘要不应有公式）"
                    )
                    break

        # 3. 必要字段检查
        required_fields = ["tier", "tags", "one_line_summary"]
        missing = [f for f in required_fields if not analysis_json.get(f)]
        if missing:
            warnings.append(f"缺少必要字段: {missing}")

        # 4. 标签数量检查
        tags = analysis_json.get("tags", [])
        if len(tags) > 5:
            warnings.append(f"标签数量 {len(tags)} > 5，可能过多")
        elif len(tags) < 2:
            warnings.append(f"标签数量 {len(tags)} < 2，可能不足")

        return CheckResult(
            valid=len(warnings) == 0,
            message=f"分析后验证完成，发现 {len(warnings)} 个警告",
            warnings=warnings,
        )

    def tier_distribution_check(
        self,
        tier_counts: Dict[str, int],
        total: int,
    ) -> CheckResult:
        """Tier 分布检查

        Args:
            tier_counts: {"A": count, "B": count, "C": count}
            total: 总数

        Returns:
            CheckResult: 检查结果
        """
        warnings = []

        if total == 0:
            return CheckResult(valid=True, message="暂无数据")

        # 计算 A 类占比
        a_count = tier_counts.get("A", 0)
        a_pct = a_count / total

        if a_pct > self.TIER_A_ALERT_THRESHOLD:
            warnings.append(
                f"Tier A 占比 {a_pct:.1%} > {self.TIER_A_ALERT_THRESHOLD:.1%} 预警阈值，"
                f"需要检查 Tier 评估标准是否过于宽松"
            )

        # 检查 B/C 分布
        b_count = tier_counts.get("B", 0)
        c_count = tier_counts.get("C", 0)

        if b_count + c_count == 0:
            warnings.append("没有 B/C 类论文，分布异常")

        # 期望分布: A=15%, B=35%, C=50%
        expected = {"A": 0.15, "B": 0.35, "C": 0.50}

        for tier in ["A", "B", "C"]:
            actual_pct = tier_counts.get(tier, 0) / total
            diff = abs(actual_pct - expected[tier])
            if diff > 0.10:  # 偏差超过 10%
                warnings.append(
                    f"Tier {tier} 偏差 {diff:.1%}，期望 {expected[tier]:.1%}，"
                    f"实际 {actual_pct:.1%}"
                )

        return CheckResult(
            valid=len(warnings) == 0,
            message=f"Tier 分布检查完成，发现 {len(warnings)} 个警告",
            warnings=warnings,
        )

    def detect_fabrication(
        self,
        analysis_json: Dict[str, Any],
        quick_mode: bool,
    ) -> CheckResult:
        """检测数据捏造

        Args:
            analysis_json: 分析结果
            quick_mode: 是否快速模式

        Returns:
            CheckResult: 检测结果
        """
        warnings = []
        fabrications = []

        if not quick_mode:
            return CheckResult(valid=True, message="完整模式不检测捏造")

        # 1. 检测公式捏造
        outline_str = str(analysis_json.get("outline", ""))
        key_contributions_str = str(analysis_json.get("key_contributions", ""))

        for pattern in self.FORMULA_PATTERNS:
            if re.search(pattern, outline_str):
                fabrications.append(f"outline 包含公式: {pattern}")
            if re.search(pattern, key_contributions_str):
                fabrications.append(f"key_contributions 包含公式: {pattern}")

        # 2. 检测虚假实验数据
        # 快速模式不应有具体数值（如 "准确率提升 5.2%"）
        number_patterns = [
            r'提升\s+\d+\.?\d*%',  # "提升 5.2%"
            r'准确率\s+\d+\.?\d*%',  # "准确率 95.3%"
            r'F1\s+\d+\.?\d*',  # "F1 0.89"
        ]

        for pattern in number_patterns:
            if re.search(pattern, one_line_summary := analysis_json.get("one_line_summary", "")):
                fabrications.append(f"一句话总结包含虚假数据: {pattern}")

        # 3. 检测虚假章节引用
        outline = analysis_json.get("outline", [])
        if outline:
            for item in outline:
                title = item.get("title", "")
                # 检查是否有编号章节（如 "1. 引言"）
                if re.match(r'^\d+\.\s+', title):
                    fabrications.append(f"outline 包含虚假章节编号: {title}")

        if fabrications:
            warnings = fabrications

        return CheckResult(
            valid=len(fabrications) == 0,
            message=f"捏造检测完成，发现 {len(fabrications)} 个疑似捏造",
            warnings=warnings,
        )

    def _get_outline_depth(self, outline: List[Dict], depth: int = 0) -> int:
        """计算 outline 最大深度"""
        if not outline:
            return depth

        max_depth = depth
        for item in outline:
            children = item.get("children", [])
            if children:
                child_depth = self._get_outline_depth(children, depth + 1)
                max_depth = max(max_depth, child_depth)

        return max_depth


# 全局实例
analysis_guardrail = AnalysisGuardrail()