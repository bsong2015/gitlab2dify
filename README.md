# GitLab到Dify知识库同步方案

## 概述

本项目提供了两种将GitLab中的文档同步到Dify知识库的方案：

1. **GitLab CI/CD触发Dify工作流**：通过GitLab的CI/CD流程触发Dify内置的工作流来实现同步
2. **直接在CI/CD脚本中触发同步**：通过Python脚本直接与GitLab和Dify API交互实现同步

## 方案一：GitLab CI/CD触发Dify工作流

此方案使用Dify内置的工作流来处理同步任务，提供了4个工作流适配不同场景：

### 1. GitLab知识库全量同步
- **文件**: `GitLab知识库全量同步.yml`
- **功能**: 将指定分支下的所有文档同步到Dify知识库
- **适用场景**: 首次同步或需要完全重建知识库时

### 2. GitLab知识库全量同步(含metadata)
- **文件**: `GitLab知识库全量同步(含metadata).yml`
- **功能**: 支持解析Markdown文件中的YAML Front Matter元数据并同步到Dify
- **适用场景**: 需要保留文档元数据的全量同步

### 3. GitLab知识库增量同步
- **文件**: `GitLab知识库增量同步.yml`
- **功能**: 仅同步有变更的文件（新增、修改、删除）
- **适用场景**: 日常增量更新，提高同步效率

### 4. GitLab知识库增量同步(含metadata)
- **文件**: `GitLab知识库增量同步(含metadata).yml`
- **功能**: 支持元数据解析的增量同步
- **适用场景**: 需要保留元数据的增量更新

## 方案二：直接在CI/CD脚本中触发同步

此方案通过Python脚本直接调用GitLab和Dify的API完成同步，包含以下组件：

### 核心脚本
- **`tools/sync-scripts/gitlab_dify_sync.py`**: 主同步脚本，支持全量和增量同步模式

### 同步模块
- **`tools/sync-src/gitlab_client.py`**: GitLab API客户端
- **`tools/sync-src/dify_client.py`**: Dify API客户端
- **`tools/sync-src/full_sync.py`**: 全量同步处理器
- **`tools/sync-src/incremental_sync.py`**: 增量同步处理器

### 配置文件
- **`tools/sync-scripts/sync_config.yaml`**: 同步配置文件，包含GitLab和Dify的连接信息、同步规则等

### CI/CD配置
- **`.gitlab-ci.yml`**: GitLab CI/CD配置文件，定义了同步任务的触发规则和执行流程

## 配置说明

### 环境变量设置
在GitLab项目中设置以下CI/CD环境变量：
- `GITLAB_PRIVATE_TOKEN`: GitLab私有令牌
- `DIFY_API_KEY`: Dify API密钥
- `DIFY_KNOWLEDGE_BASE_ID`: Dify知识库ID

### 支持的文件格式
- `.md` (Markdown)
- `.markdown` (Markdown)

## 使用方法

### 方案一：使用Dify工作流
1. 在Dify中导入对应的YAML工作流文件
2. 配置工作流中的环境变量
3. 通过GitLab触发相应的Webhook或手动运行工作流

### 方案二：使用Python脚本
1. 配置`sync_config.yaml`文件
2. 在GitLab CI/CD中运行同步脚本
3. 支持通过命令行参数指定同步模式（全量或增量）

## 特性对比

| 特性 | 方案一（Dify工作流） | 方案二（Python脚本） |
|------|---------------------|---------------------|
| 实现复杂度 | 中等 | 较高 |
| 配置灵活性 | 较高 | 高 |
| 元数据支持 | 支持 | 支持 |
| 增量同步 | 支持 | 支持 |
| 错误处理 | 内置 | 自定义 |
| 维护性 | 依赖Dify平台 | 独立维护 |

## 注意事项

1. 确保GitLab私有令牌具有读取仓库内容的权限
2. 确保Dify API密钥具有操作知识库的权限
3. 敏感信息通过CI/CD环境变量注入，不提交到代码仓库
4. 根据实际需要选择合适的同步方案和工作流