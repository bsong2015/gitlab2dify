# CICD 同步工具

此目录包含用于将GitLab仓库中的文档同步到Dify知识库的工具。

## 工具目录结构

- `tools/sync-scripts/` - 同步脚本主目录
  - `gitlab_dify_sync.py` - 主同步脚本
  - `sync_config.yaml` - 配置文件
  - `requirements.txt` - Python依赖
  - `sync_src/` - 同步脚本源代码
  - `SYNC_TOOL_DOCUMENTATION.md` - 详细使用说明

## 功能

- **全量同步**：同步指定分支下的所有文档，可选择清理已删除的文档
- **增量同步**：仅同步有变更的文档（新增、修改、删除）
- **文档管理**：支持文档的创建、更新和删除操作
- **元数据支持**：支持解析YAML Front Matter
- **配置化**：通过配置文件管理所有参数

## 使用

详细使用说明请参见 `SYNC_TOOL_DOCUMENTATION.md`。

## CI/CD 集成

`.gitlab-ci.yml` 文件已被更新为直接调用这些同步工具。