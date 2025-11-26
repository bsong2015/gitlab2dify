#!/usr/bin/env python3
"""
GitLab到Dify知识库同步脚本
支持全量同步和增量同步两种模式
"""

import sys
import os
import yaml
import argparse
from typing import Dict, Any

# 添加sync_src目录到Python路径
sys.path.append(os.path.join(os.path.dirname(__file__), 'sync_src'))

from sync_src.gitlab_client import GitLabAPIClient
from sync_src.dify_client import DifyAPIClient
from sync_src.full_sync import FullSyncProcessor
from sync_src.incremental_sync import IncrementalSyncProcessor


def load_config(config_path: str) -> Dict[str, Any]:
    """
    加载配置文件
    """
    with open(config_path, 'r', encoding='utf-8') as file:
        config = yaml.safe_load(file)
    return config


def main():
    parser = argparse.ArgumentParser(description='GitLab到Dify知识库同步工具')
    parser.add_argument('--config', type=str, default='sync_config.yaml', help='配置文件路径')
    parser.add_argument('--mode', type=str, choices=['full', 'incremental'], required=True, help='同步模式: full(全量) 或 incremental(增量)')
    parser.add_argument('--project-id', type=int, required=True, help='GitLab项目ID')
    parser.add_argument('--branch', type=str, default='main', help='GitLab分支名（全量同步时使用）')
    parser.add_argument('--commit-sha', type=str, help='Git提交SHA（增量同步时使用）')
    
    args = parser.parse_args()
    
    # 检查参数
    if args.mode == 'incremental' and not args.commit_sha:
        print("错误: 增量同步模式需要提供 --commit-sha 参数")
        sys.exit(1)
    
    if args.mode == 'full' and not args.branch:
        print("错误: 全量同步模式需要提供 --branch 参数")
        sys.exit(1)
    
    # 加载配置
    print(f"加载配置文件: {args.config}")
    config = load_config(args.config)
    
    # 验证配置
    required_keys = ['gitlab', 'dify', 'sync']
    for key in required_keys:
        if key not in config:
            print(f"错误: 配置文件中缺少 '{key}' 部分")
            sys.exit(1)
    
    # 检查必要的配置值
    if not config['gitlab'].get('private_token'):
        print("错误: 配置文件中 gitlab.private_token 未设置")
        sys.exit(1)
    
    if not config['dify'].get('api_key'):
        print("错误: 配置文件中 dify.api_key 未设置")
        sys.exit(1)
        
    if not config['dify'].get('knowledge_base_id'):
        print("错误: 配置文件中 dify.knowledge_base_id 未设置")
        sys.exit(1)
    
    # 获取SSL验证设置，默认为True
    verify_ssl = config['sync'].get('verify_ssl', True)
    print(f"SSL验证设置: {'启用' if verify_ssl else '禁用'}")
    
    # 创建GitLab和Dify客户端
    print("创建API客户端...")
    gitlab_client = GitLabAPIClient(
        host=config['gitlab']['host'],
        private_token=config['gitlab']['private_token'],
        timeout=config['sync']['timeout'],
        verify_ssl=verify_ssl,
        max_retries=config['sync']['max_retries'],
        retry_interval=config['sync']['retry_interval'],
        page_size=config['sync'].get('page_size', 100)  # 从sync配置中获取分页大小，如果不存在则默认为100
    )
    
    dify_client = DifyAPIClient(
        host=config['dify']['host'],
        api_key=config['dify']['api_key'],
        knowledge_base_id=config['dify']['knowledge_base_id'],
        timeout=config['sync']['timeout'],
        verify_ssl=verify_ssl,
        indexing_technique=config['dify']['indexing_technique'],
        process_rule=config['dify']['process_rule'],
        max_retries=config['sync']['max_retries'],
        retry_interval=config['sync']['retry_interval']
    )
    
    # 根据模式执行同步
    if args.mode == 'full':
        print(f"执行全量同步，项目ID: {args.project_id}，分支: {args.branch}")
        processor = FullSyncProcessor(gitlab_client, dify_client, config)
        result = processor.sync(args.project_id, args.branch)
    elif args.mode == 'incremental':
        print(f"执行增量同步，项目ID: {args.project_id}，提交SHA: {args.commit_sha}")
        processor = IncrementalSyncProcessor(gitlab_client, dify_client, config)
        result = processor.sync(args.project_id, args.commit_sha)
    
    print("同步任务完成！")
    return 0


if __name__ == "__main__":
    main()