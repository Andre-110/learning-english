#!/usr/bin/env python3
"""
🔍 日志检索工具 - 快速定位线上问题

使用方式：
    # 按用户检索
    python scripts/search_logs.py --user user123
    
    # 按对话检索
    python scripts/search_logs.py --conversation conv456
    
    # 按错误级别检索
    python scripts/search_logs.py --level ERROR
    
    # 按时间范围检索
    python scripts/search_logs.py --start "2024-02-01 10:00" --end "2024-02-01 11:00"
    
    # 按关键词检索
    python scripts/search_logs.py --keyword "ASR failed"
    
    # 生成错误报告
    python scripts/search_logs.py --error-report --hours 24
    
    # 导出问题报告（JSON）
    python scripts/search_logs.py --user user123 --export report.json
"""

import os
import sys
import json
import argparse
from datetime import datetime, timedelta

# 添加项目根目录到 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.utils.log_indexer import (
    get_log_indexer,
    search_logs,
    get_error_report,
    export_incident_report
)


def format_log_entry(entry, show_raw: bool = False):
    """格式化日志条目"""
    level_colors = {
        "ERROR": "\033[91m",    # 红色
        "WARNING": "\033[93m",  # 黄色
        "INFO": "\033[92m",     # 绿色
        "DEBUG": "\033[94m",    # 蓝色
    }
    reset = "\033[0m"
    
    color = level_colors.get(entry.level, "")
    
    # 截断长消息
    message = entry.message[:150] + "..." if len(entry.message) > 150 else entry.message
    
    line = f"{color}[{entry.timestamp.strftime('%H:%M:%S')}] [{entry.level:7}] [{entry.source:8}]{reset} {message}"
    
    if entry.user_id:
        line += f" (user: {entry.user_id})"
    if entry.conversation_id:
        line += f" (conv: {entry.conversation_id[:8]}...)"
    
    return line


def main():
    parser = argparse.ArgumentParser(description="日志检索工具")
    
    # 检索条件
    parser.add_argument("--user", "-u", help="用户ID")
    parser.add_argument("--conversation", "-c", help="对话ID")
    parser.add_argument("--round", "-r", type=int, help="轮次ID")
    parser.add_argument("--level", "-l", choices=["ERROR", "WARNING", "INFO", "DEBUG"], help="日志级别")
    parser.add_argument("--keyword", "-k", help="关键词")
    parser.add_argument("--start", "-s", help="开始时间 (YYYY-MM-DD HH:MM)")
    parser.add_argument("--end", "-e", help="结束时间 (YYYY-MM-DD HH:MM)")
    parser.add_argument("--hours", type=int, default=24, help="最近N小时 (默认24)")
    parser.add_argument("--limit", "-n", type=int, default=50, help="最大返回条数 (默认50)")
    
    # 来源
    parser.add_argument("--sources", nargs="+", choices=["app", "error", "server", "system", "metrics", "timeline"],
                       help="指定日志来源")
    
    # 报告
    parser.add_argument("--error-report", action="store_true", help="生成错误报告")
    parser.add_argument("--export", help="导出到JSON文件")
    
    # 显示选项
    parser.add_argument("--raw", action="store_true", help="显示原始数据")
    parser.add_argument("--json", action="store_true", help="JSON格式输出")
    
    args = parser.parse_args()
    
    # 解析时间
    start_time = None
    end_time = None
    
    if args.start:
        start_time = datetime.strptime(args.start, "%Y-%m-%d %H:%M")
    elif not args.error_report:
        start_time = datetime.now() - timedelta(hours=args.hours)
    
    if args.end:
        end_time = datetime.strptime(args.end, "%Y-%m-%d %H:%M")
    
    # 错误报告
    if args.error_report:
        report = get_error_report(hours=args.hours)
        
        if args.json or args.export:
            output = json.dumps(report, indent=2, ensure_ascii=False)
            if args.export:
                with open(args.export, 'w', encoding='utf-8') as f:
                    f.write(output)
                print(f"✅ 报告已导出到: {args.export}")
            else:
                print(output)
        else:
            print(f"\n{'='*60}")
            print(f"📊 错误报告 (最近 {args.hours} 小时)")
            print(f"{'='*60}")
            print(f"时间范围: {report['time_range']['start']} ~ {report['time_range']['end']}")
            print(f"总错误数: {report['total_errors']}")
            print()
            print("按类型统计:")
            for error_type, count in report['by_type'].items():
                print(f"  - {error_type}: {count}")
            print()
            
            if report['samples']:
                print("错误样本:")
                for error_type, samples in report['samples'].items():
                    print(f"\n  [{error_type}]")
                    for sample in samples[:3]:
                        print(f"    {sample['timestamp']}: {sample['message'][:80]}...")
        
        return
    
    # 导出问题报告
    if args.export and (args.user or args.conversation):
        report = export_incident_report(
            user_id=args.user,
            conversation_id=args.conversation,
            start_time=start_time,
            end_time=end_time
        )
        
        with open(args.export, 'w', encoding='utf-8') as f:
            json.dump(report, indent=2, ensure_ascii=False, fp=f)
        
        print(f"✅ 问题报告已导出到: {args.export}")
        print(f"   总日志数: {report['total_logs']}")
        print(f"   错误数: {report['log_levels']['ERROR']}")
        return
    
    # 普通检索
    logs = search_logs(
        user_id=args.user,
        conversation_id=args.conversation,
        round_id=args.round,
        level=args.level,
        start_time=start_time,
        end_time=end_time,
        keyword=args.keyword,
        sources=args.sources,
        limit=args.limit
    )
    
    if args.json:
        output = json.dumps([l.to_dict() for l in logs], indent=2, ensure_ascii=False)
        print(output)
        return
    
    # 格式化输出
    print(f"\n{'='*60}")
    print(f"🔍 检索结果 (共 {len(logs)} 条)")
    print(f"{'='*60}")
    
    if not logs:
        print("未找到匹配的日志")
        return
    
    for entry in logs:
        print(format_log_entry(entry, args.raw))
        if args.raw and entry.raw_data:
            print(f"    📋 Raw: {json.dumps(entry.raw_data, ensure_ascii=False)[:200]}...")
    
    print(f"\n{'='*60}")
    print(f"提示: 使用 --export report.json 可导出完整报告")


if __name__ == "__main__":
    main()
