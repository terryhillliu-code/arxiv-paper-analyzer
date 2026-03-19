"""
CLI 主入口

使用 Typer 实现命令行工具。
"""

import asyncio
import json
import sys
from typing import List, Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

app = typer.Typer(
    name="arxiv-cli",
    help="ArXiv Paper Analyzer - 论文管理命令行工具",
    add_completion=False,
)

console = Console()


def run_async(coro):
    """运行异步函数"""
    return asyncio.run(coro)


@app.command()
def search(
    query: str = typer.Argument(None, help="搜索关键词"),
    categories: List[str] = typer.Option(None, "-c", "--category", help="分类过滤"),
    tags: List[str] = typer.Option(None, "-t", "--tag", help="标签过滤"),
    date_from: str = typer.Option(None, "--from", help="起始日期 (YYYY-MM-DD)"),
    date_to: str = typer.Option(None, "--to", help="结束日期 (YYYY-MM-DD)"),
    sort: str = typer.Option("newest", "-s", "--sort", help="排序方式: newest/popularity"),
    limit: int = typer.Option(20, "-n", "--limit", help="返回数量"),
    output: str = typer.Option(None, "-o", "--output", help="输出文件 (JSON)"),
):
    """搜索论文"""
    from .commands import search_papers

    arguments = {
        "query": query,
        "categories": categories,
        "tags": tags,
        "date_from": date_from,
        "date_to": date_to,
        "sort_by": sort,
        "limit": limit,
    }

    result = run_async(search_papers(arguments))

    if result["success"]:
        papers = result["data"]["papers"]
        _display_papers_table(papers)

        if output:
            _save_to_file(result["data"], output)
            console.print(f"\n[green]已保存到 {output}[/green]")
    else:
        console.print(f"[red]搜索失败: {result['error']}[/red]")
        raise typer.Exit(1)


@app.command()
def get(
    paper_id: int = typer.Argument(..., help="论文 ID"),
    include_analysis: bool = typer.Option(False, "--analysis", help="包含分析结果"),
    output: str = typer.Option(None, "-o", "--output", help="输出文件 (JSON)"),
):
    """获取论文详情"""
    from .commands import get_paper

    arguments = {
        "paper_id": paper_id,
        "include_analysis": include_analysis,
    }

    result = run_async(get_paper(arguments))

    if result["success"]:
        paper = result["data"]
        _display_paper_detail(paper)

        if output:
            _save_to_file(paper, output)
            console.print(f"\n[green]已保存到 {output}[/green]")
    else:
        console.print(f"[red]获取失败: {result['error']}[/red]")
        raise typer.Exit(1)


@app.command()
def trending(
    days: int = typer.Option(7, "-d", "--days", help="最近几天"),
    limit: int = typer.Option(20, "-n", "--limit", help="每天返回数量"),
    analyze: bool = typer.Option(False, "--analyze", help="包含分析结果"),
    output: str = typer.Option(None, "-o", "--output", help="输出文件 (JSON)"),
):
    """获取热门论文"""
    from .commands import get_trending

    arguments = {
        "days": days,
        "limit_per_day": limit,
        "include_analysis": analyze,
    }

    result = run_async(get_trending(arguments))

    if result["success"]:
        days_data = result["data"]["days"]

        for day in days_data:
            console.print(f"\n[bold cyan]📅 {day['date']}[/bold cyan] ({day['total_that_day']} 篇)")
            _display_papers_table(day["papers"], show_date=False)

        if output:
            _save_to_file(result["data"], output)
            console.print(f"\n[green]已保存到 {output}[/green]")
    else:
        console.print(f"[red]获取失败: {result['error']}[/red]")
        raise typer.Exit(1)


@app.command()
def analyze(
    paper_id: int = typer.Argument(..., help="论文 ID"),
    force: bool = typer.Option(False, "-f", "--force", help="强制重新分析"),
):
    """深度分析论文"""
    from .commands import analyze_paper

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("正在分析论文...", total=None)

        arguments = {
            "paper_id": paper_id,
            "force": force,
        }

        result = run_async(analyze_paper(arguments))

    if result["success"]:
        paper = result["data"]
        _display_analysis_result(paper)
    else:
        console.print(f"[red]分析失败: {result['error']}[/red]")
        raise typer.Exit(1)


@app.command()
def summary(
    paper_id: int = typer.Argument(..., help="论文 ID"),
    style: str = typer.Option("brief", "-s", "--style", help="摘要风格: brief/detailed"),
):
    """生成 AI 摘要"""
    from .commands import generate_summary

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("正在生成摘要...", total=None)

        arguments = {
            "paper_id": paper_id,
            "style": style,
        }

        result = run_async(generate_summary(arguments))

    if result["success"]:
        paper = result["data"]
        console.print(Panel(
            paper.get("ai_summary", "无摘要"),
            title=f"[bold]{paper.get('title', '未知标题')}[/bold]",
            border_style="green",
        ))
    else:
        console.print(f"[red]生成失败: {result['error']}[/red]")
        raise typer.Exit(1)


@app.command()
def export(
    paper_ids: List[int] = typer.Argument(..., help="论文 ID 列表"),
    format: str = typer.Option("bibtex", "-f", "--format", help="导出格式: bibtex/obsidian"),
    output: str = typer.Option(None, "-o", "--output", help="输出文件"),
    folder: str = typer.Option("Inbox", "--folder", help="Obsidian 目标文件夹"),
):
    """导出论文"""
    from .commands import export_papers

    arguments = {
        "paper_ids": paper_ids,
        "format": format,
        "output_file": output,
        "folder": folder,
    }

    result = run_async(export_papers(arguments))

    if result["success"]:
        data = result["data"]

        if format == "bibtex":
            console.print(Panel(
                data.get("content", ""),
                title=f"BibTeX ({data.get('paper_count', 0)} 篇)",
                border_style="blue",
            ))
            if output:
                console.print(f"\n[green]已保存到 {output}[/green]")
        else:
            console.print(f"[green]已导出 {data.get('paper_count', 0)} 篇论文到 Obsidian[/green]")
    else:
        console.print(f"[red]导出失败: {result['error']}[/red]")
        raise typer.Exit(1)


@app.command()
def publish(
    paper_ids: List[int] = typer.Argument(..., help="论文 ID 列表"),
    platform: str = typer.Option(..., "-p", "--platform", help="发布平台: feishu/email/webhook"),
    config: str = typer.Option(None, "-c", "--config", help="配置文件路径"),
):
    """发布论文到平台"""
    from .commands import publish_papers

    arguments = {
        "paper_ids": paper_ids,
        "platform": platform,
        "config_file": config,
    }

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task(f"正在发布到 {platform}...", total=None)

        result = run_async(publish_papers(arguments))

    if result["success"]:
        console.print(f"[green]发布成功: {result['data'].get('message', 'OK')}[/green]")
    else:
        console.print(f"[red]发布失败: {result['error']}[/red]")
        raise typer.Exit(1)


@app.command("list-platforms")
def list_platforms():
    """列出可用的发布平台"""
    from app.publishers import PublisherRegistry

    platforms = PublisherRegistry.list_available()

    table = Table(title="可用发布平台")
    table.add_column("平台", style="cyan")
    table.add_column("描述")

    for p in platforms:
        table.add_row(p, f"发布到 {p}")

    console.print(table)


def _display_papers_table(papers: List[dict], show_date: bool = True):
    """显示论文列表表格"""
    if not papers:
        console.print("[yellow]无结果[/yellow]")
        return

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("ID", style="dim", width=6)
    table.add_column("标题", width=50)
    table.add_column("arXiv ID", width=12)
    if show_date:
        table.add_column("日期", width=10)
    table.add_column("评分", width=6)

    for p in papers:
        row = [
            str(p.get("id", "")),
            p.get("title", "")[:47] + "..." if len(p.get("title", "")) > 50 else p.get("title", ""),
            p.get("arxiv_id", "-"),
        ]
        if show_date:
            date_str = p.get("publish_date", "-")
            row.append(date_str[:10] if date_str else "-")
        row.append(str(p.get("tier", "-")))
        table.add_row(*row)

    console.print(table)


def _display_paper_detail(paper: dict):
    """显示论文详情"""
    console.print(Panel(
        f"[bold]{paper.get('title', '未知标题')}[/bold]\n\n"
        f"arXiv: {paper.get('arxiv_id', '-')}\n"
        f"日期: {paper.get('publish_date', '-')}\n"
        f"分类: {', '.join(paper.get('categories', []))}\n"
        f"作者: {', '.join(paper.get('authors', [])[:5])}\n"
        f"评分: {paper.get('tier', '-')}",
        border_style="blue",
    ))

    if paper.get("summary"):
        console.print(Panel(
            paper["summary"][:500] + "..." if len(paper.get("summary", "")) > 500 else paper["summary"],
            title="摘要",
            border_style="green",
        ))

    if paper.get("key_contributions"):
        console.print(Panel(
            "\n".join(f"• {c}" for c in paper["key_contributions"]),
            title="主要贡献",
            border_style="yellow",
        ))


def _display_analysis_result(paper: dict):
    """显示分析结果"""
    console.print(Panel(
        f"[bold]{paper.get('title', '未知标题')}[/bold]\n\n"
        f"一句话总结: {paper.get('one_line_summary', '-')}\n"
        f"总体评分: {paper.get('overall_rating', '-')}/10",
        title="分析结果",
        border_style="green",
    ))

    if paper.get("key_contributions"):
        console.print(Panel(
            "\n".join(f"• {c}" for c in paper["key_contributions"]),
            title="主要贡献",
            border_style="yellow",
        ))

    if paper.get("methodology"):
        console.print(Panel(
            paper["methodology"],
            title="方法论",
            border_style="cyan",
        ))

    if paper.get("action_items"):
        console.print(Panel(
            "\n".join(f"• {a}" for a in paper["action_items"]),
            title="行动建议",
            border_style="magenta",
        ))


def _save_to_file(data: dict, path: str):
    """保存数据到文件"""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    app()