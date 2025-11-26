import re
from typing import Dict, List, Any, Optional
from .gitlab_client import GitLabAPIClient
from .dify_client import DifyAPIClient


class FullSyncProcessor:
    """
    全量同步处理器
    """
    def __init__(self, gitlab_client: GitLabAPIClient, dify_client: DifyAPIClient, config: Dict[str, Any]):
        self.gitlab_client = gitlab_client
        self.dify_client = dify_client
        self.config = config

    def sync(self, project_id: int, branch: str = 'main') -> Dict[str, Any]:
        """
        执行全量同步
        """
        print(f"开始全量同步，项目ID: {project_id}，分支: {branch}")
        
        # 预加载元数据字段映射以提高性能
        print("正在预加载元数据字段映射...")
        self.dify_client.preload_metadata_fields()
        
        # 获取所有允许的文件扩展名
        allowed_extensions = self.config['gitlab']['allowed_file_extensions']
        
        # 从GitLab获取所有文件
        print("正在从GitLab获取所有文件...")
        all_files = self.gitlab_client.get_all_files(project_id, branch)
        
        # 过滤出指定扩展名的文件
        all_markdown_files = self.gitlab_client.filter_files_by_extension(all_files, allowed_extensions)
        
        # 进一步过滤，只保留Docusaurus管理的文档（docs/ 和 i18n/ 下的文件）
        docusaurus_markdown_files = []
        for file_info in all_markdown_files:
            file_path = file_info['path']
            is_docusaurus_docs = (file_path.startswith('docs/') or 
                                ('i18n/' in file_path and 'docusaurus-plugin-content-docs-' in file_path))
            if is_docusaurus_docs:
                docusaurus_markdown_files.append(file_info)
        
        markdown_files = docusaurus_markdown_files
        print(f"找到 {len(markdown_files)} 个Docusaurus管理的Markdown文件")
        
        # 如果需要，可以先获取Dify中现有的文档列表
        # 这样可以识别出哪些文档在GitLab中已删除
        if self.config['sync'].get('cleanup_deleted', False):
            print("正在获取Dify中现有的文档列表...")
            existing_docs_result = self.dify_client.list_documents()
            # existing_docs中的键是文档的标准化名称（与创建文档时使用的名称相同）
            existing_docs = {doc['name']: doc['id'] for doc in existing_docs_result.get('data', [])}
        else:
            existing_docs = {}
        
        # 统计信息
        stats = {
            'total_files': len(markdown_files),
            'processed': 0,
            'success': 0,
            'failed': 0,
            'deleted': 0
        }
        
        # 处理每个文件
        for file_info in markdown_files:
            file_path = file_info['path']
            print(f"处理文件: {file_path}")
            
            try:
                # 获取文件内容
                file_content = self.gitlab_client.get_file_content(project_id, file_path, branch)
                
                # 从路径中提取文档名称和元数据
                normalized_file_path, path_metadata = self.gitlab_client.extract_metadata_from_path(file_path)
                
                # 解析文档中的Front Matter元数据（如果启用）
                content, front_matter_metadata = self._parse_front_matter(file_content) if self.config['sync']['enable_metadata'] else (file_content, None)
                
                # 合并元数据：路径元数据为基础，Front Matter中的元数据优先
                final_metadata = path_metadata.copy()
                if front_matter_metadata:
                    final_metadata.update(front_matter_metadata)
                
                # 确保元数据中不包含版本信息
                if 'version' in final_metadata:
                    del final_metadata['version']
                
                # 检查Dify中是否已存在同名文档
                if normalized_file_path in existing_docs:
                    # 文档已存在，使用更新方法而不是删除再创建
                    old_doc_id = existing_docs[normalized_file_path]
                    result = self.dify_client.update_document(old_doc_id, normalized_file_path, content, final_metadata)
                    print(f"  - 已更新文档: {result.get('document', {}).get('id', 'Unknown ID')}, 路径: {normalized_file_path}")
                    # 从existing_docs中移除已处理的文档
                    del existing_docs[normalized_file_path]
                    stats['success'] += 1
                    stats['processed'] += 1
                    continue  # 跳过创建新文档的步骤
                
                # 创建新文档
                result = self.dify_client.create_document(normalized_file_path, content, final_metadata)
                print(f"  - 成功创建文档: {result.get('document', {}).get('id', 'Unknown ID')}, 路径: {normalized_file_path}")
                
                stats['success'] += 1
            except Exception as e:
                print(f"  - 处理文件 {file_path} 时出错: {str(e)}")
                stats['failed'] += 1
            
            stats['processed'] += 1
        
        # 如果配置了清理删除的文件，则删除Dify中存在但GitLab中不存在的文档
        if self.config['sync'].get('cleanup_deleted', False):
            for file_path, doc_id in existing_docs.items():
                try:
                    self.dify_client.delete_document(doc_id)
                    print(f"  - 清理已删除的文档: {file_path} (ID: {doc_id})")
                    stats['deleted'] += 1
                except Exception as e:
                    print(f"  - 删除文档 {file_path} (ID: {doc_id}) 时出错: {str(e)}")
        
        print(f"全量同步完成！成功: {stats['success']}, 失败: {stats['failed']}, 删除: {stats['deleted']}, 总计: {stats['total_files']}")
        return stats

    def _parse_front_matter(self, content: str) -> tuple[str, Optional[Dict]]:
        """
        解析YAML Front Matter元数据
        """
        # 匹配YAML Front Matter的正则表达式
        front_matter_pattern = r'^---\s*\n(.*?)\n---\s*\n'
        match = re.match(front_matter_pattern, content, re.DOTALL)
        
        if match:
            yaml_string = match.group(1)
            # 简单解析YAML格式的元数据
            metadata = {}
            for line in yaml_string.strip().split('\n'):
                if ':' in line:
                    key, value = line.split(':', 1)
                    key = key.strip()
                    value = value.strip().strip('"\'')  # 去除引号
                    metadata[key] = value
            
            # 提取Front Matter后的纯内容
            clean_content = content[len(match.group(0)):].strip()
            
            return clean_content, metadata if metadata else None
        
        # 如果没有Front Matter，返回原内容和空元数据
        return content, None
