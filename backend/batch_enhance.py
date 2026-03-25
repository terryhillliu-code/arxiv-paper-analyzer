#!/usr/bin/env python3
"""
批量补充文档内容 - 4并发处理
"""

import asyncio
import json
import sys
from pathlib import Path
from datetime import datetime

# 添加项目路径
sys.path.insert(0, '/Users/liufang/arxiv-paper-analyzer/backend')

from app.services.ai_service import ai_service

# 配置
CONCURRENCY = 6
BATCH_SIZE = 50  # 每批处理数量
CHECKPOINT_FILE = '/tmp/enhance_checkpoint.json'
LOG_FILE = '/tmp/enhance_log.txt'

def log(msg):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with open(LOG_FILE, 'a') as f:
        f.write(f"{timestamp} | {msg}\n")
    print(f"{timestamp} | {msg}")

async def enhance_file(file_info, semaphore):
    """增强单个文件"""
    async with semaphore:
        try:
            file_path = Path(file_info['path'])
            title = file_info['title']
            abstract = file_info.get('abstract', '')
            file_type = file_info['type']

            # 构建prompt
            if file_type == 'PAPER':
                prompt = f"""为以下学术论文生成简短分析（JSON格式）：

标题: {title}

{f"摘要: {abstract}" if abstract else ""}

请生成：
1. 一句话定位（论文核心贡献）
2. 价值评估（1-5星）

返回格式：
```json
{{
    "one_liner": "一句话定位...",
    "value": 4
}}
```"""
            else:
                prompt = f"""为以下报告生成简短分析（JSON格式）：

标题: {title}

{f"内容摘要: {abstract}" if abstract else ""}

请生成：
1. 核心观点（1句话）
2. 价值评估（1-5星）

返回格式：
```json
{{
    "core_insight": "核心观点...",
    "value": 4
}}
```"""

            # 调用AI
            response = ai_service._call_api(prompt, max_tokens=300)
            result = ai_service._parse_json(response)

            if not result:
                return {'status': 'failed', 'reason': 'JSON解析失败'}

            # 读取原文件
            content = file_path.read_text(encoding='utf-8')

            # 构建补充内容
            if file_type == 'PAPER':
                addition = f"\n\n## 一句话定位\n{result.get('one_liner', '暂无')}\n"
            else:
                addition = f"\n\n## 💡 核心观点\n> {result.get('core_insight', '暂无')}\n"

            # 插入到frontmatter之后
            if content.startswith('---'):
                # 找到frontmatter结束位置
                end = content.find('\n---\n', 4)
                if end != -1:
                    insert_pos = end + 5
                    new_content = content[:insert_pos] + addition + content[insert_pos:]
                else:
                    new_content = content + addition
            else:
                new_content = addition + content

            # 写入文件
            file_path.write_text(new_content, encoding='utf-8')

            return {'status': 'success'}

        except Exception as e:
            return {'status': 'failed', 'reason': str(e)}

async def process_batch(batch, semaphore, start_idx):
    """处理一批文件"""
    tasks = [enhance_file(f, semaphore) for f in batch]
    results = await asyncio.gather(*tasks)

    success = len([r for r in results if r['status'] == 'success'])
    failed = len(results) - success

    return {'success': success, 'failed': failed}

async def main():
    # 读取任务列表
    with open('/tmp/files_to_enhance.json', 'r') as f:
        files = json.load(f)

    total = len(files)
    log(f"开始处理 {total} 个文件，并发数: {CONCURRENCY}")

    # 检查是否有checkpoint
    checkpoint = 0
    if Path(CHECKPOINT_FILE).exists():
        with open(CHECKPOINT_FILE, 'r') as f:
            cp = json.load(f)
            checkpoint = cp.get('last_index', 0)
            log(f"从checkpoint恢复: {checkpoint}")

    # 创建信号量
    semaphore = asyncio.Semaphore(CONCURRENCY)

    # 处理
    processed = checkpoint
    success_total = 0
    failed_total = 0

    for i in range(checkpoint, total, BATCH_SIZE):
        batch = files[i:i+BATCH_SIZE]

        result = await process_batch(batch, semaphore, i)
        processed += len(batch)
        success_total += result['success']
        failed_total += result['failed']

        # 保存checkpoint
        with open(CHECKPOINT_FILE, 'w') as f:
            json.dump({'last_index': i + BATCH_SIZE}, f)

        # 进度报告
        pct = 100 * processed / total
        log(f"进度: {processed}/{total} ({pct:.1f}%) | 成功: {success_total} | 失败: {failed_total}")

        # 短暂休息，避免API限流
        await asyncio.sleep(0.5)

    log(f"完成! 总计: {processed}, 成功: {success_total}, 失败: {failed_total}")

if __name__ == '__main__':
    asyncio.run(main())