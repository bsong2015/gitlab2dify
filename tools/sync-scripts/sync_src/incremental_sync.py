import re
from typing import Dict, List, Any, Optional
from .gitlab_client import GitLabAPIClient
from .dify_client import DifyAPIClient

class IncrementalSyncProcessor:
    """
    增量同步处理器
    """
    def __init__(self, gitlab_client: GitLabAPIClient, dify_client: DifyAPIClient, config: Dict[str, Any]):
        self.gitlab_client = gitlab_client
        self.dify_client = dify_client
        self.config = config

    def sync(self, project_id: int, commit_sha: str) -> Dict[str, Any]:
        """
        执行增量同步
        """
        print(f"开始增量同步，项目ID: {project_id}，提交SHA: {commit_sha}")
        
        # 预加载元数据字段映射以提高性能
        print("正在预加载元数据字段映射...")
        self.dify_client.preload_metadata_fields()
        
        # 获取提交差异
        print("正在获取提交差异...")
        diffs = self.gitlab_client.get_commit_diff(project_id, commit_sha)
        
        # 获取允许的文件扩展名
        allowed_extensions = self.config['gitlab']['allowed_file_extensions']
        
        # 分类处理的文件
        added_files = []
        modified_files = []
        deleted_files = []
        
        for file_diff in diffs:
            # 检查文件扩展名和路径是否匹配
            def is_valid_docusaurus_file(path):
                is_valid_ext = any(path.endswith(ext) for ext in allowed_extensions)
                is_docusaurus_docs = (path.startswith('docs/') or 
                                    ('i18n/' in path and 'docusaurus-plugin-content-docs-' in path))
                return is_valid_ext and is_docusaurus_docs
            
            if file_diff.get('deleted_file'):
                if is_valid_docusaurus_file(file_diff['old_path']):
                    deleted_files.append(file_diff['old_path'])
            elif file_diff.get('new_file'):
                if is_valid_docusaurus_file(file_diff['new_path']):
                    added_files.append(file_diff['new_path'])
            elif file_diff.get('renamed_file'):
                if is_valid_docusaurus_file(file_diff['old_path']):
                    deleted_files.append(file_diff['old_path'])
                if is_valid_docusaurus_file(file_diff['new_path']):
                    added_files.append(file_diff['new_path'])
            else:  # 修改的文件
                if is_valid_docusaurus_file(file_diff['new_path']):
                    modified_files.append(file_diff['new_path'])
        
        print(f"新增文件: {len(added_files)}, 修改文件: {len(modified_files)}, 删除文件: {len(deleted_files)}")
        
        # 统计信息
        stats = {
            'added': {'total': len(added_files), 'success': 0, 'failed': 0},
            'modified': {'total': len(modified_files), 'success': 0, 'failed': 0},
            'deleted': {'total': len(deleted_files), 'success': 0, 'failed': 0},
        }
        
        # 处理新增文件
        for file_path in added_files:
            print(f"处理新增文件: {file_path}")
            success = self._handle_added_file(project_id, file_path, commit_sha)
            if success:
                stats['added']['success'] += 1
            else:
                stats['added']['failed'] += 1
        
        # 处理修改文件
        for file_path in modified_files:
            print(f"处理修改文件: {file_path}")
            success = self._handle_modified_file(project_id, file_path, commit_sha)
            if success:
                stats['modified']['success'] += 1
            else:
                stats['modified']['failed'] += 1
        
        # 处理删除文件
        for file_path in deleted_files:
            print(f"处理删除文件: {file_path}")
            success = self._handle_deleted_file(file_path)
            if success:
                stats['deleted']['success'] += 1
            else:
                stats['deleted']['failed'] += 1
        
        print("增量同步完成！")
        print(f"新增 - 成功: {stats['added']['success']}, 失败: {stats['added']['failed']}")
        print(f"修改 - 成功: {stats['modified']['success']}, 失败: {stats['modified']['failed']}")
        print(f"删除 - 成功: {stats['deleted']['success']}, 失败: {stats['deleted']['failed']}")
        
        return stats

    def _handle_added_file(self, project_id: int, file_path: str, ref: str) -> bool:
        """
        处理新增文件
        """
        try:
            # 获取文件内容
            file_content = self.gitlab_client.get_file_content(project_id, file_path, ref)
            
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
            
            # 创建或更新Dify文档
            result = self.dify_client.create_document(normalized_file_path, content, final_metadata)
            print(f"  - 成功创建文档: {result.get('document', {}).get('id', 'Unknown ID')}, 路径: {normalized_file_path}")
            
            return True
        except Exception as e:
            print(f"  - 创建文件 {file_path} 时出错: {str(e)}")
            return False

    def _handle_modified_file(self, project_id: int, file_path: str, ref: str) -> bool:
        """
        处理修改文件
        """
        try:
            # 获取文件内容
            file_content = self.gitlab_client.get_file_content(project_id, file_path, ref)
            
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
            
            # 在Dify中查找现有文档 - 使用标准化路径
            existing_doc = self.dify_client.get_document_by_name(normalized_file_path)
            
            if existing_doc:
                # 如果存在现有文档，则更新它
                doc_id = existing_doc.get('id')
                if doc_id:
                    result = self.dify_client.update_document(doc_id, normalized_file_path, content, final_metadata)
                    print(f"  - 成功更新文档: {result.get('document', {}).get('id', 'Unknown ID')}，文件路径: {normalized_file_path}")
                else:
                    # 文档ID不存在，这不应该发生，但为了安全起见创建新文档
                    result = self.dify_client.create_document(normalized_file_path, content, final_metadata)
                    print(f"  - 创建新文档（原有文档ID丢失）: {result.get('document', {}).get('id', 'Unknown ID')}，文件路径: {normalized_file_path}")
            else:
                # 文档不存在，创建新文档
                result = self.dify_client.create_document(normalized_file_path, content, final_metadata)
                print(f"  - 创建新文档: {result.get('document', {}).get('id', 'Unknown ID')}，文件路径: {normalized_file_path}")
            
            return True
        except Exception as e:
            print(f"  - 更新文件 {file_path} 时出错: {str(e)}")
            return False

    def _handle_deleted_file(self, file_path: str) -> bool:
        """
        处理删除文件
        """
        try:
            # 在Dify中搜索文档，需要使用与创建文档时相同的路径格式
            # 先获取标准化路径
            normalized_file_path, path_metadata = self.gitlab_client.extract_metadata_from_path(file_path)
            
            # 在Dify中搜索文档
            search_result = self.dify_client.search_documents(keyword=normalized_file_path)
            
            # 从搜索结果中查找匹配的文档
            document_id = None
            if 'data' in search_result and isinstance(search_result['data'], list):
                for doc in search_result['data']:
                    if doc.get('name') == normalized_file_path:
                        document_id = doc.get('id')
                        break
            
            if document_id:
                # 删除文档
                delete_result = self.dify_client.delete_document(document_id)
                print(f"  - 成功删除文档: {document_id}，文件路径: {normalized_file_path}")
                return True
            else:
                print(f"  - 在Dify中未找到文档: {normalized_file_path}，跳过")
                return True  # 即使没找到也算成功，因为目标是确保文档不存在
            
        except Exception as e:
            print(f"  - 删除文件 {file_path} 时出错: {str(e)}")
            return False

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
