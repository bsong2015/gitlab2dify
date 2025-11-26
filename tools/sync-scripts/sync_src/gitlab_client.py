import requests
import json
import base64
import re
from typing import List, Dict, Optional, Tuple
from urllib.parse import quote


class GitLabAPIClient:
    """
    GitLab API客户端，用于获取仓库文件、提交差异等信息
    """
    def __init__(self, host: str, private_token: str, timeout: int = 60, verify_ssl: bool = True, max_retries: int = 3, retry_interval: int = 2, page_size: int = 100):
        self.host = host.rstrip('/')
        self.private_token = private_token
        self.timeout = timeout
        self.verify_ssl = verify_ssl
        self.max_retries = max_retries
        self.retry_interval = retry_interval
        self.page_size = page_size
        self.session = requests.Session()
        self.session.headers.update({
            'PRIVATE-TOKEN': self.private_token
        })

    def get_all_files(self, project_id: int, branch: str = 'main') -> List[Dict]:
        """
        获取指定分支下的所有文件
        """
        # 确保分支名正确处理，避免URL编码问题
        import urllib.parse
        encoded_branch = urllib.parse.quote(branch, safe='')
        
        url = f"{self.host}/api/v4/projects/{project_id}/repository/tree"
        params = {
            'recursive': True,
            'ref': encoded_branch,
            'per_page': self.page_size
        }
        
        all_files = []
        page = 1
        
        while True:
            params['page'] = page
            response = self._make_request('GET', url, params=params)
            
            if not response:
                break
                
            # 检查内容类型后再解析JSON
            content_type = response.headers.get('content-type', '')
            if 'application/json' not in content_type:
                # 如果不是JSON响应，提供更多诊断信息
                print(f"错误: 获取文件列表时返回非JSON响应")
                print(f"状态码: {response.status_code}")
                print(f"内容类型: {content_type}")
                print(f"响应预览: {response.text[:500]}...")
                raise Exception(f"API返回非JSON响应，无法解析文件列表")
                
            files = response.json()
            if not files:
                break
                
            all_files.extend(files)
            page += 1
            
        return all_files

    def get_file_content(self, project_id: int, file_path: str, ref: str = 'main') -> str:
        """
        获取指定文件的内容
        """
        # 对文件路径和分支/引用进行URL编码
        encoded_path = quote(file_path, safe='')
        encoded_ref = quote(ref, safe='')
        url = f"{self.host}/api/v4/projects/{project_id}/repository/files/{encoded_path}"
        params = {'ref': encoded_ref}
        
        response = self._make_request('GET', url, params=params)
        
        # 检查内容类型后再解析JSON
        content_type = response.headers.get('content-type', '')
        if 'application/json' not in content_type:
            # 如果不是JSON响应，提供更多诊断信息
            print(f"错误: 获取文件内容时返回非JSON响应")
            print(f"状态码: {response.status_code}")
            print(f"内容类型: {content_type}")
            print(f"请求URL: {url}")
            print(f"响应预览: {response.text[:500]}...")
            raise Exception(f"API返回非JSON响应，无法解析文件内容")
        
        data = response.json()
        
        # GitLab API返回的内容是Base64编码的，需要解码
        encoded_content = data['content']
        decoded_content = base64.b64decode(encoded_content).decode('utf-8')
        
        return decoded_content

    def get_commit_diff(self, project_id: int, commit_sha: str) -> List[Dict]:
        """
        获取指定提交的文件差异
        """
        url = f"{self.host}/api/v4/projects/{project_id}/repository/commits/{commit_sha}/diff"
        response = self._make_request('GET', url)
        return response.json()

    def filter_files_by_extension(self, files: List[Dict], extensions: List[str]) -> List[Dict]:
        """
        根据文件扩展名和路径过滤文件，只返回Docusaurus管理的文档内容（docs/ 和 i18n/ 下的文件）
        """
        filtered_files = []
        for file in files:
            if file.get('type') == 'blob':  # 只处理文件，不处理目录
                file_path = file.get('path', '')
                
                # 检查文件路径是否在Docusaurus管理的目录下
                is_docusaurus_docs = file_path.startswith('docs/') or \
                                   ('i18n/' in file_path and 'docusaurus-plugin-content-docs-' in file_path)
                
                if is_docusaurus_docs:
                    for ext in extensions:
                        if file_path.endswith(ext):
                            filtered_files.append(file)
                            break
        return filtered_files

    def _make_request(self, method: str, url: str, **kwargs) -> requests.Response:
        """
        执行HTTP请求的通用方法，包含重试逻辑
        """
        for attempt in range(self.max_retries):  # 最多重试指定次数
            try:
                response = self.session.request(
                    method=method,
                    url=url,
                    timeout=self.timeout,
                    verify=self.verify_ssl,
                    **kwargs
                )
                
                # 检查响应状态码
                if response.status_code == 401:
                    raise Exception(f"GitLab API认证失败 (401): 请检查您的private_token是否正确")
                elif response.status_code == 404:
                    raise Exception(f"GitLab API资源未找到 (404): {url}")
                elif response.status_code == 403:
                    raise Exception(f"GitLab API访问被拒绝 (403): 请检查您的权限")
                
                response.raise_for_status()
                
                # 检查响应内容类型和内容
                content_type = response.headers.get('content-type', '')
                if 'application/json' not in content_type and len(response.content) > 0:
                    # 如果不是JSON响应，但有内容，输出完整的响应内容以供诊断
                    # 尝试检测内容编码并正确解码
                    try:
                        # 检查响应头中的编码信息
                        if 'charset=' in content_type:
                            charset = content_type.split('charset=')[1].split(';')[0].strip()
                            response_text = response.content.decode(charset)
                        else:
                            # 尝试检测编码 - 首先尝试导入chardet
                            try:
                                import chardet
                                detected = chardet.detect(response.content)
                                if detected['confidence'] > 0.7:  # 置信度大于70%
                                    response_text = response.content.decode(detected['encoding'])
                                else:
                                    # 默认使用UTF-8，如果失败则使用gbk
                                    try:
                                        response_text = response.content.decode('utf-8')
                                    except UnicodeDecodeError:
                                        response_text = response.content.decode('gbk', errors='replace')
                            except ImportError:
                                # 如果chardet未安装，使用简单的方法
                                try:
                                    response_text = response.content.decode('utf-8')
                                except UnicodeDecodeError:
                                    try:
                                        response_text = response.content.decode('gbk', errors='replace')
                                    except UnicodeDecodeError:
                                        response_text = response.content.decode('utf-8', errors='replace')
                    except Exception:
                        # 如果解码失败，使用默认解码并替换错误字符
                        response_text = response.content.decode('utf-8', errors='replace')
                    
                    print(f"警告: API返回非JSON响应")
                    print(f"响应状态码: {response.status_code}")
                    print(f"内容类型: {content_type}")
                    print(f"响应URL: {url}")
                    print(f"响应内容长度: {len(response.content)} 字节")
                    print(f"完整响应内容:\n{response_text}")
                    if response.status_code >= 400:
                        raise Exception(f"API请求失败: {response.status_code}")
                
                return response
            except requests.exceptions.RequestException as e:
                if attempt == self.max_retries - 1:  # 最后一次尝试失败
                    raise e
                print(f"请求失败，正在重试... ({attempt + 1}/{self.max_retries}): {e}")
                import time
                time.sleep(self.retry_interval)  # 等待指定时间后重试

        raise Exception("请求失败，已达到最大重试次数")

    def extract_metadata_from_path(self, file_path: str) -> Tuple[str, Dict[str, str]]:
        """
        从文件路径中提取文档名称和元数据信息
        返回: (规范化文档名称, 元数据字典)
        """
        metadata = {}
        
        path_parts = file_path.split('/')
        
        # 提取产品和语言信息，不提取版本信息
        product = None
        language = None
        
        # 检查是否是docs/下的路径 - 默认为中文（不包含版本）
        if file_path.startswith('docs/'):
            # 从 docs/ 后的部分提取产品名
            docs_part = file_path[len('docs/'):]
            if '/' in docs_part:
                product = docs_part.split('/')[0]  # 例如 'ciam' 或 'eiam'
            else:
                product = docs_part  # 如果路径直接是 docs/filename.md
            
            # docs下的文档默认是中文
            language = 'zh-CN'  # 默认为中文
        
        # 检查是否是i18n/下的路径
        elif file_path.startswith('i18n/'):
            # 处理 i18n/{language}/docusaurus-plugin-content-docs-{product}/... 的结构
            path_parts = file_path.split('/')
            if len(path_parts) >= 3 and path_parts[1]:  # 提取语言代码
                language = path_parts[1]
                
                # 查找docusaurus-plugin-content-docs-开头的部分来提取产品名
                for part in path_parts[2:]:  # 从第三个部分开始查找
                    if part.startswith('docusaurus-plugin-content-docs-'):
                        product = part.replace('docusaurus-plugin-content-docs-', '')
                        break
        
        # 确保所有文档都有product和language元数据
        if product:
            metadata['product'] = product
        else:
            metadata['product'] = 'unknown'
            
        if language:
            metadata['language'] = language
        else:
            metadata['language'] = 'zh-CN'  # 默认语言为中文
        
        # 创建规范化的文档名称，去除不需要的路径层级（包括版本信息）
        normalized_name = self._normalize_file_path(file_path, metadata)
        
        return normalized_name, metadata

    def _normalize_file_path(self, file_path: str, metadata: Dict[str, str]) -> str:
        """
        标准化文件路径，去除不需要的路径层级（包括版本信息）
        """
        original_path = file_path
        
        # 从元数据中获取产品和语言信息
        product = metadata.get('product', 'unknown')
        language = metadata.get('language', 'zh-CN')
        
        # 处理 docs/{product}/... 的路径 - 添加语言信息
        if file_path.startswith('docs/'):
            # 去除 'docs/' 前缀
            docs_relative_path = file_path[len('docs/'):]
            # 构建新路径：{product}/{language}/{rest_of_path}
            file_path = f"{product}/{language}/{docs_relative_path}"
        
        # 处理 i18n/... 的路径 - 确保包含完整层级
        elif file_path.startswith('i18n/'):
            # 处理 i18n/{language}/docusaurus-plugin-content-docs-{product}/... 结构
            path_parts = file_path.split('/')
            
            # 查找docusaurus-plugin-content-docs-开头的部分
            plugin_part_idx = -1
            for i, part in enumerate(path_parts):
                if part.startswith('docusaurus-plugin-content-docs-'):
                    plugin_part_idx = i
                    break
            
            if plugin_part_idx != -1:
                # 查找版本标识后的实际文档路径
                actual_doc_start = -1
                for i in range(plugin_part_idx + 1, len(path_parts)):
                    # 检测版本标识
                    if path_parts[i] in ['current', 'v1', 'v2', 'v3', 'v4', 'v5', 'v6', 'v7', 'v8', 'v9', 'v10', 'latest']:
                        actual_doc_start = i + 1
                        break
                
                if actual_doc_start != -1 and actual_doc_start < len(path_parts):
                    # 从版本标识后的部分开始构建路径
                    doc_path = '/'.join(path_parts[actual_doc_start:])
                    # 路径格式：{product}/{language}/{doc_path}
                    file_path = f"{product}/{language}/{doc_path}"
                else:
                    # 如果没有找到版本标识，使用剩余部分
                    remaining_parts = path_parts[plugin_part_idx + 1:]
                    if remaining_parts:
                        doc_path = '/'.join(remaining_parts)
                        file_path = f"{product}/{language}/{doc_path}"
                    else:
                        # 只使用文件名
                        file_path = f"{product}/{language}/{path_parts[-1]}"
        
        # 清理双重斜杠和其他问题
        file_path = file_path.replace('//', '/')
        
        return file_path