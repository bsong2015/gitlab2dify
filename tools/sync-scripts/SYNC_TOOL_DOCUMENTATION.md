# GitLab到Dify知识库同步工具使用说明

## 概述

本工具用于将GitLab仓库中的Markdown文档同步到Dify知识库中，支持全量同步和增量同步两种模式。配置文件中的敏感信息通过CI/CD环境变量注入，确保安全性。文档发布人员可手动控制同步模式（全量/增量）。

## 文件结构

```
docs-center-project/
├── src/                         # Docusaurus项目源代码
│   ├── components/              # React组件
│   ├── css/                     # 样式文件
│   └── pages/                   # 页面文件
├── tools/
│   └── sync-scripts/            # 同步脚本工具目录
│       ├── gitlab_dify_sync.py  # 主同步脚本
│       ├── sync_config.yaml     # 配置文件（含敏感信息占位符）
│       ├── requirements.txt     # 依赖文件
│       ├── sync_src/            # 同步脚本源代码
│       │   ├── gitlab_client.py # GitLab API客户端
│       │   ├── dify_client.py   # Dify API客户端
│       │   ├── full_sync.py     # 全量同步处理器
│       │   └── incremental_sync.py # 增量同步处理器
│       └── SYNC_TOOL_DOCUMENTATION.md # 本使用说明
├── .gitlab-ci.yml               # CI/CD配置文件
└── trigger_dify.py              # (原方案，已弃用)
```

## 配置文件说明

配置文件 `sync_config.yaml` 包含以下部分，敏感信息使用占位符：

```yaml
gitlab:
  # GitLab实例URL
  host: "http://10.99.0.202:8000/"
  # GitLab私有令牌 (CI/CD中通过环境变量设置)
  private_token: "GITLAB_TOKEN_PLACEHOLDER"
  # 允许同步的文件扩展名
  allowed_file_extensions:
    - ".md"
    - ".markdown"

dify:
  # Dify主机地址
  host: "http://10.99.0.202"
  # Dify API密钥 (CI/CD中通过环境变量设置)
  api_key: "DIFY_API_KEY_PLACEHOLDER"
  # 知识库ID (CI/CD中通过环境变量设置)
  knowledge_base_id: "DIFY_KB_ID_PLACEHOLDER"
  # 文档索引技术 high_quality 或 economy
  indexing_technique: "high_quality"
  # 文档处理规则
  process_rule:
    mode: "automatic"
    rules:
      pre_processing_rules:
        - id: "remove_extra_spaces"
          enabled: true
        - id: "remove_urls_emails"
          enabled: false
      segmentation:
        separator: "##"
        max_tokens: 4000

# 同步设置
sync:
  # 是否启用元数据解析
  enable_metadata: true
  # 是否启用增量同步模式
  enable_incremental: true
  # 全量同步时是否清理已删除的文件（从GitLab中删除但在Dify中仍存在的文件）
  cleanup_deleted: false
  # GitLab API分页大小
  page_size: 100
  # 请求超时时间（秒）
  timeout: 60
  # 重试次数
  max_retries: 3
  # 重试间隔（秒）
  retry_interval: 10
  # SSL验证 - 如果使用自签名证书，设置为 false
  verify_ssl: false
```

## 使用方法

### 1. 命令行使用

```bash
# 全量同步
python gitlab_dify_sync.py --mode full --project-id 123 --branch main --config sync_config.yaml

# 增量同步
python gitlab_dify_sync.py --mode incremental --project-id 123 --commit-sha abc123def --config sync_config.yaml
```

参数说明：
- `--mode`: 同步模式，`full`（全量）或 `incremental`（增量）
- `--project-id`: GitLab项目ID
- `--branch`: GitLab分支名（仅全量同步时使用）
- `--commit-sha`: Git提交SHA（仅增量同步时使用）
- `--config`: 配置文件路径

### 2. CI/CD环境变量设置

在GitLab项目中设置以下CI/CD环境变量（Settings > CI/CD > Variables）：

- `GITLAB_PRIVATE_TOKEN`: GitLab私有令牌
- `DIFY_API_KEY`: Dify API密钥
- `DIFY_KNOWLEDGE_BASE_ID`: Dify知识库ID

## CI/CD配置

优化后的 `.gitlab-ci.yml` 文件配置如下，支持文档发布人员手动控制同步模式：

```yaml
stages:
  - sync_to_dify

sync_to_dify:
  stage: sync_to_dify
  image: python:3.9-slim
  
  tags:
    - test

  # 支持手动触发或分支推送触发
  rules:
    - if: '$CI_PIPELINE_SOURCE == "web"'        # 手动触发
    - if: '$CI_COMMIT_BRANCH == "main"'         # main 分支推送自动触发增量同步

  before_script:
    - echo "正在安装 Python 依赖 (使用清华镜像源)..."
    - pip install -i https://pypi.tuna.tsinghua.edu.cn/simple requests pyyaml
    # 替换配置文件中的占位符
    - sed -i "s|GITLAB_TOKEN_PLACEHOLDER|$GITLAB_PRIVATE_TOKEN|g" tools/sync-scripts/sync_config.yaml
    - sed -i "s|DIFY_API_KEY_PLACEHOLDER|$DIFY_API_KEY|g" tools/sync-scripts/sync_config.yaml
    - sed -i "s|DIFY_KB_ID_PLACEHOLDER|$DIFY_KNOWLEDGE_BASE_ID|g" tools/sync-scripts/sync_config.yaml

  script:
    - echo "开始执行 GitLab 到 Dify 知识库同步..."
    - cd tools/sync-scripts
    # 根据 CI_SYNC_MODE 变量决定同步模式
    - |
      if [ "$CI_SYNC_MODE" = "full" ]; then
        echo "执行全量同步"
        python gitlab_dify_sync.py --mode full --project-id $CI_PROJECT_ID --branch main --config sync_config.yaml
      else
        echo "执行增量同步"
        python gitlab_dify_sync.py --mode incremental --project-id $CI_PROJECT_ID --commit-sha $CI_COMMIT_SHA --config sync_config.yaml
      fi
```

## 文档发布人员操作流程

### 日常增量同步（自动触发）
1. 文档作者在 `main` 分支提交文档更新
2. CI 自动执行增量同步

### 手动触发同步（全量或增量）
1. 文档作者需要全量或增量同步时：
   - 进入 GitLab 项目页面
   - 点击 CI/CD > Pipelines
   - 点击 "Run pipeline" 按钮
   - 在变量中设置（可选）：
     - `CI_SYNC_MODE=full` (执行全量同步)
     - 或 `CI_SYNC_MODE=incremental` (执行增量同步) - 默认值
   - 点击 "Run pipeline" 开始同步

## 依赖安装

运行脚本前需要安装以下依赖：

```bash
pip install requests pyyaml
```

## 功能特性

1. **全量同步**：同步指定分支下的所有符合条件的文件
2. **增量同步**：仅同步有变更的文件（新增、修改、删除）
3. **元数据支持**：支持解析Markdown文件中的YAML Front Matter元数据
4. **错误处理**：包含重试机制和错误日志
5. **配置化**：通过配置文件管理所有参数
6. **安全性**：敏感信息通过CI/CD环境变量注入，不提交到代码仓库
7. **用户控制**：文档发布人员可手动选择同步模式

## 注意事项

1. 确保GitLab私有令牌具有足够的权限读取仓库内容
2. 确保Dify API密钥具有操作知识库的权限
3. 在CI/CD环境中，敏感信息应通过环境变量传递，不要提交到代码仓库
4. 根据实际需要调整配置文件中的参数
5. 文档发布人员可通过手动触发CI/CD来控制同步模式（全量/增量）
6. 配置文件中的占位符会在CI/CD执行时被环境变量的值替换