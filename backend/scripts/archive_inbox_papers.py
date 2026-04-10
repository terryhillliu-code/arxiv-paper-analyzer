#!/usr/bin/env python3
"""
Inbox 论文归档脚本

扫描 Obsidian Vault 的 Inbox 目录，根据论文标签自动移动到对应主题目录。

用法:
    # 预览归档计划（不执行）
    python scripts/archive_inbox_papers.py --dry-run

    # 执行归档
    python scripts/archive_inbox_papers.py

    # 指定归档数量
    python scripts/archive_inbox_papers.py --limit 100
"""

import argparse
import logging
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)

# 默认配置
DEFAULT_VAULT_ROOT = Path("~/Documents/ZhiweiVault").expanduser()
DEFAULT_INBOX = DEFAULT_VAULT_ROOT / "Inbox"

# 排除目录
EXCLUDE_DIRS = {".obsidian", "attachments", "extracted", "backup", ".duplicate_archive_backup"}

# 标签 -> 目录映射
TAG_TO_DIR = {
    # AI 系统 - 大模型
    "大模型架构": "10-19_AI系统_AI-Systems/11_大模型架构_LLM-Architecture",
    "大模型基础架构": "10-19_AI系统_AI-Systems/11_大模型架构_LLM-Architecture",
    "LLM应用": "10-19_AI系统_AI-Systems/11_大模型架构_LLM-Architecture",

    # AI 系统 - 多模态
    "多模态智能体": "10-19_AI系统_AI-Systems/12_多模态智能体_Multimodal-Agent",
    "视觉语言模型": "10-19_AI系统_AI-Systems/12_多模态智能体_Multimodal-Agent",
    "文本到图像生成": "10-19_AI系统_AI-Systems/12_多模态智能体_Multimodal-Agent",
    "扩散模型": "10-19_AI系统_AI-Systems/12_多模态智能体_Multimodal-Agent",
    "离散扩散模型": "10-19_AI系统_AI-Systems/12_多模态智能体_Multimodal-Agent",
    "视频生成": "10-19_AI系统_AI-Systems/12_多模态智能体_Multimodal-Agent",
    "图像生成": "10-19_AI系统_AI-Systems/12_多模态智能体_Multimodal-Agent",

    # AI 系统 - 训练
    "训练系统": "10-19_AI系统_AI-Systems/13_训练系统_Training-System",
    "非自回归生成": "10-19_AI系统_AI-Systems/13_训练系统_Training-System",

    # AI 系统 - 知识
    "RAG与知识系统": "10-19_AI系统_AI-Systems/14_RAG与知识系统_RAG-Knowledge",
    "知识图谱": "10-19_AI系统_AI-Systems/14_RAG与知识系统_RAG-Knowledge",

    # AI 系统 - 医学
    "医学AI": "10-19_AI系统_AI-Systems/15_医学AI_Medical-AI",

    # AI 系统 - CV
    "计算机视觉": "10-19_AI系统_AI-Systems/17_计算机视觉_Computer-Vision",
    "视觉导航": "10-19_AI系统_AI-Systems/17_计算机视觉_Computer-Vision",

    # AI 系统 - NLP
    "NLP与语言处理": "10-19_AI系统_AI-Systems/18_NLP与语言处理_NLP",
    "自然语言处理": "10-19_AI系统_AI-Systems/18_NLP与语言处理_NLP",
    "自然语言查询": "10-19_AI系统_AI-Systems/18_NLP与语言处理_NLP",
    "歧义消解": "10-19_AI系统_AI-Systems/18_NLP与语言处理_NLP",
    "文本生成": "10-19_AI系统_AI-Systems/18_NLP与语言处理_NLP",

    # AI 系统 - RL
    "强化学习": "10-19_AI系统_AI-Systems",

    # AI 系统 - 推荐
    "推荐系统": "10-19_AI系统_AI-Systems",

    # AI 系统 - 语音
    "语音处理": "10-19_AI系统_AI-Systems",

    # AI 系统 - 深度学习
    "深度学习": "10-19_AI系统_AI-Systems",

    # AI 系统 - 机器人
    "机器人": "10-19_AI系统_AI-Systems",
    "机器人导航": "10-19_AI系统_AI-Systems",
    "机器人进化": "10-19_AI系统_AI-Systems",
    "具身智能": "10-19_AI系统_AI-Systems",
    "室内机器人": "10-19_AI系统_AI-Systems",
    "生成式设计": "10-19_AI系统_AI-Systems",

    # AI 系统 - 自动驾驶
    "自动驾驶": "10-19_AI系统_AI-Systems",

    # AI 系统 - 安全
    "安全与隐私": "10-19_AI系统_AI-Systems",
    "AI安全": "10-19_AI系统_AI-Systems",

    # AI 系统 - 科学计算
    "科学计算": "10-19_AI系统_AI-Systems",

    # AI 系统 - 数据挖掘
    "数据挖掘": "10-19_AI系统_AI-Systems",

    # AI 系统 - 编码智能体
    "编码智能体": "10-19_AI系统_AI-Systems",
    "代码生成": "10-19_AI系统_AI-Systems",

    # AI 系统 - 基准测试
    "基准测试": "10-19_AI系统_AI-Systems",
    "低资源语言": "10-19_AI系统_AI-Systems",

    # AI 系统 - 人机交互
    "人机交互": "10-19_AI系统_AI-Systems",
    "目标漂移": "10-19_AI系统_AI-Systems",

    # AI 硬件
    "GPU硬件架构": "20-29_AI硬件_AI-Hardware/22_GPU与加速器",
    "AI集群": "20-29_AI硬件_AI-Hardware/21_AI芯片架构",
    "芯片设计": "20-29_AI硬件_AI-Hardware/21_AI芯片架构",

    # 基础设施
    "数据中心": "30-39_基础设施_Infra-Compute/32_数据中心",
    "网络架构": "30-39_基础设施_Infra-Compute",
    "存储系统": "30-39_基础设施_Infra-Compute",
    "计算平台": "30-39_基础设施_Infra-Compute/35_基础设施核心",

    # 网络互联
    "高速网络": "40-49_网络与互联_Networking/41_网络架构",
    "互联技术": "40-49_网络与互联_Networking/42_光互连技术",

    # 行业研究
    "行业报告": "50-59_行业研究_Industry/51_行业报告",
    "商业分析": "50-59_行业研究_Industry/53_市场分析",

    # 默认
    "学术论文": "90-99_系统与归档_System",
    "技术博客": "90-99_系统与归档_System",
}


def parse_frontmatter(content: str) -> Dict[str, any]:
    """解析 Markdown 文件的 YAML frontmatter

    Args:
        content: 文件内容

    Returns:
        frontmatter 字典
    """
    if not content.startswith("---"):
        return {}

    fm_end = content.find("---", 3)
    if fm_end == -1:
        return {}

    frontmatter_text = content[3:fm_end].strip()
    frontmatter = {}
    current_key = None
    current_list = []

    for line in frontmatter_text.split('\n'):
        line = line.rstrip()

        # 跳过注释和空行
        if line.strip().startswith('#') or not line.strip():
            continue

        # 列表项
        if line.startswith('  - ') and current_key:
            current_list.append(line[4:].strip())
            continue

        # 保存上一个列表
        if current_key and current_list:
            frontmatter[current_key] = current_list
            current_list = []

        # 键值对
        if ':' in line:
            key, value = line.split(':', 1)
            current_key = key.strip()
            value = value.strip()

            # 处理行内列表
            if value.startswith('[') and value.endswith(']'):
                items = value[1:-1].split(',')
                frontmatter[current_key] = [i.strip().strip('"').strip("'") for i in items if i.strip()]
                current_key = None
            elif value:
                frontmatter[current_key] = value.strip('"').strip("'")
                current_key = None

    # 保存最后一个列表
    if current_key and current_list:
        frontmatter[current_key] = current_list

    return frontmatter


def get_target_dir(tags: List[str], vault_root: Path) -> Optional[Path]:
    """根据标签获取目标目录

    Args:
        tags: 论文标签列表
        vault_root: Vault 根目录

    Returns:
        目标目录路径，如果没有匹配则返回 None
    """
    if not tags:
        return None

    for tag in tags:
        if tag in TAG_TO_DIR:
            target = vault_root / TAG_TO_DIR[tag]
            return target

    return None


def archive_paper(md_path: Path, vault_root: Path, dry_run: bool = True) -> Tuple[bool, str]:
    """归档单篇论文

    Args:
        md_path: Markdown 文件路径
        vault_root: Vault 根目录
        dry_run: 是否为预览模式

    Returns:
        (成功, 目标路径或错误信息)
    """
    try:
        # 读取文件
        with open(md_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # 解析 frontmatter
        fm = parse_frontmatter(content)
        if not fm:
            return False, "无法解析 frontmatter"

        tags = fm.get('tags', [])
        arxiv_id = fm.get('arxiv_id', '')

        # 获取目标目录
        target_dir = get_target_dir(tags, vault_root)
        if not target_dir:
            return False, f"无匹配目录，tags: {tags}"

        # 目标路径
        target_path = target_dir / md_path.name

        if dry_run:
            return True, f"将移动到: {target_path}"

        # 创建目标目录
        target_dir.mkdir(parents=True, exist_ok=True)

        # 移动文件
        shutil.move(str(md_path), str(target_path))

        return True, str(target_path)

    except Exception as e:
        return False, str(e)


def main():
    parser = argparse.ArgumentParser(description="Inbox 论文归档脚本")
    parser.add_argument("--dry-run", action="store_true", help="预览模式，不实际移动文件")
    parser.add_argument("--limit", type=int, default=None, help="限制处理数量")
    parser.add_argument("--vault", type=str, default=None, help="Vault 根目录")
    args = parser.parse_args()

    vault_root = Path(args.vault) if args.vault else DEFAULT_VAULT_ROOT
    inbox = vault_root / "Inbox"

    if not inbox.exists():
        logger.error(f"Inbox 目录不存在: {inbox}")
        return

    # 扫描 PAPER_*.md 文件
    paper_files = list(inbox.glob("PAPER_*.md"))
    logger.info(f"发现 {len(paper_files)} 个论文文件")

    if args.limit:
        paper_files = paper_files[:args.limit]
        logger.info(f"限制处理: {len(paper_files)} 个")

    # 统计
    stats = {
        "total": len(paper_files),
        "archived": 0,
        "skipped": 0,
        "failed": 0,
    }

    for md_path in paper_files:
        success, result = archive_paper(md_path, vault_root, dry_run=args.dry_run)

        if success:
            stats["archived"] += 1
            logger.info(f"✓ {md_path.name} → {result}")
        else:
            stats["failed"] += 1
            logger.warning(f"✗ {md_path.name}: {result}")

    # 输出统计
    print("\n" + "=" * 60)
    print(f"归档统计 ({'预览' if args.dry_run else '执行'}):")
    print(f"  总数: {stats['total']}")
    print(f"  成功: {stats['archived']}")
    print(f"  失败: {stats['failed']}")
    print("=" * 60)


if __name__ == "__main__":
    main()