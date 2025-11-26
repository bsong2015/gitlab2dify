import requests
from typing import Dict, Optional

class DifyAPIClient:
    """
    Dify API客户端，用于管理知识库文档
    """
    def __init__(self, host: str, api_key: str, knowledge_base_id: str, timeout: int = 60, verify_ssl: bool = True, indexing_technique: str = "high_quality", process_rule: Dict = None, max_retries: int = 3, retry_interval: int = 2):
        self.host = host.rstrip('/')
        self.api_key = api_key
        self.knowledge_base_id = knowledge_base_id
        self.timeout = timeout
        self.verify_ssl = verify_ssl
        self.indexing_technique = indexing_technique
        self.process_rule = process_rule or {
            "mode": "automatic",
            "rules": {
                "pre_processing_rules": [
                    {"id": "remove_extra_spaces", "enabled": True},
                    {"id": "remove_urls_emails", "enabled": False}
                ],
                "segmentation": {
                    "separator": "\n",
                    "max_tokens": 800
                }
            }
        }
        self.max_retries = max_retries
        self.retry_interval = retry_interval
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        })
        # 缓存元数据字段映射，避免重复请求
        self._metadata_field_map = None

    def create_document(self, name: str, text: str, metadata: Optional[Dict] = None) -> Dict:
        """
        创建新文档
        """
        url = f"{self.host}/v1/datasets/{self.knowledge_base_id}/document/create_by_text"
        
        payload = {
            "name": name,
            "text": text,
            "indexing_technique": self.indexing_technique,
            "process_rule": self.process_rule
        }

        response = self._make_request('POST', url, json=payload)
        result = response.json()
        
        # 如果提供了元数据，获取文档ID并更新元数据
        if metadata and result.get('document', {}).get('id'):
            document_id = result['document']['id']
            try:
                self.update_document_metadata(document_id, metadata)
                # 尝试更新返回结果中的元数据信息
                if 'document' in result:
                    if 'metadata' not in result['document']:
                        result['document']['metadata'] = {}
                    result['document']['metadata'].update(metadata)
            except Exception as e:
                print(f"更新文档元数据时出错: {e}")

        return result

    def update_document(self, document_id: str, name: str, text: str, metadata: Optional[Dict] = None) -> Dict:
        """
        更新文档内容和元数据
        根据YAML文件中的逻辑，使用PUT方法更新文档
        """
        url = f"{self.host}/v1/datasets/{self.knowledge_base_id}/documents/{document_id}/update-by-text"
        
        payload = {
            "name": name,
            "text": text,
            "indexing_technique": self.indexing_technique,
            "process_rule": self.process_rule
        }

        try:
            # 使用PUT方法更新文档
            response = self._make_request('POST', url, json=payload)
            result = response.json()
        except Exception as e:
            print(f"更新文档API失败: {str(e)}，回退到删除再创建方法")
            # 如果更新API失败，回退到删除再创建的方式
            self.delete_document(document_id)
            result = self.create_document(name, text, metadata)
            return result

        # 如果提供了元数据，更新文档元数据
        if metadata:
            try:
                self.update_document_metadata(document_id, metadata)
                # 尝试更新返回结果中的元数据信息
                if 'document' in result:
                    if 'metadata' not in result['document']:
                        result['document']['metadata'] = {}
                    result['document']['metadata'].update(metadata)
            except Exception as e:
                print(f"更新文档元数据时出错: {e}")

        return result

    def delete_document(self, document_id: str) -> Dict:
        """
        删除文档
        """
        url = f"{self.host}/v1/datasets/{self.knowledge_base_id}/documents/{document_id}"
        response = self._make_request('DELETE', url)
        return response.json()

    def search_documents(self, keyword: str = None) -> Dict:
        """
        搜索文档
        """
        url = f"{self.host}/v1/datasets/{self.knowledge_base_id}/documents"
        params = {}
        if keyword:
            params['keyword'] = keyword
        response = self._make_request('GET', url, params=params)
        return response.json()

    def list_documents(self) -> Dict:
        """
        获取知识库中的所有文档列表
        """
        url = f"{self.host}/v1/datasets/{self.knowledge_base_id}/documents"
        response = self._make_request('GET', url)
        return response.json()

    def get_document_by_name(self, name: str) -> Optional[Dict]:
        """
        根据名称查找文档
        """
        search_result = self.search_documents(keyword=name)
        if 'data' in search_result and isinstance(search_result['data'], list):
            for doc in search_result['data']:
                if doc.get('name') == name:
                    return doc
        return None

    def get_metadata_fields(self) -> Dict:
        """
        获取知识库元数据字段，使用缓存避免重复请求
        """
        if self._metadata_field_map is not None:
            # 如果已有缓存，直接返回缓存的字段映射
            return {"doc_metadata": [{"name": k, "id": v} for k, v in self._metadata_field_map.items()]}
        
        url = f"{self.host}/v1/datasets/{self.knowledge_base_id}/metadata"
        response = self._make_request('GET', url)
        result = response.json()
        
        # 解析并缓存字段映射
        if result and isinstance(result.get('doc_metadata'), list):
            self._metadata_field_map = {}
            for field in result['doc_metadata']:
                field_name = field.get('name')
                field_id = field.get('id')
                if field_name and field_id:
                    self._metadata_field_map[field_name] = field_id
        else:
            # 如果无法获取字段映射，初始化为空字典
            self._metadata_field_map = {}
        
        return result

    def update_document_metadata(self, document_id: str, metadata: Dict) -> Dict:
        """
        更新文档元数据
        """
        url = f"{self.host}/v1/datasets/{self.knowledge_base_id}/documents/metadata"
        
        # 获取字段ID映射（使用缓存）
        try:
            fields_response = self.get_metadata_fields()
            if self._metadata_field_map is not None:
                field_id_map = self._metadata_field_map
            else:
                # 如果缓存为空，从响应中临时获取
                field_id_map = {}
                if fields_response and isinstance(fields_response.get('doc_metadata'), list):
                    for field in fields_response['doc_metadata']:
                        field_name = field.get('name')
                        field_id = field.get('id')
                        if field_name and field_id:
                            field_id_map[field_name] = field_id
        except Exception as e:
            print(f"获取元数据字段失败: {e}")
            return {"message": "failed_to_get_metadata_fields"}

        # 构建元数据列表 - 只包含知识库中已定义的字段
        metadata_list = []
        for name, value in metadata.items():
            if name in field_id_map:
                # 只有当字段在知识库中已定义时才添加
                metadata_list.append({
                    "id": field_id_map[name],
                    "name": name,
                    "value": str(value)
                })
            else:
                # 如果字段未在知识库中定义，则跳过（不添加自定义字段）
                print(f"跳过未定义的元数据字段: {name}")
        
        if not metadata_list:
            print(f"没有有效的元数据字段可更新到文档 {document_id}")
            return {"message": "no_metadata_to_update"}

        # 构建最终的请求载荷
        payload = {
            "operation_data": [
                {
                    "document_id": document_id,
                    "metadata_list": metadata_list
                }
            ]
        }

        response = self._make_request('POST', url, json=payload)
        return response.json()

    def preload_metadata_fields(self):
        """
        预加载元数据字段映射，避免在处理每个文档时重复请求
        """
        try:
            # 调用一次get_metadata_fields来填充缓存
            self.get_metadata_fields()
            print("元数据字段映射已预加载")
        except Exception as e:
            print(f"预加载元数据字段映射失败: {e}")

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
                    raise Exception(f"Dify API认证失败 (401): 请检查您的api_key是否正确")
                elif response.status_code == 404:
                    raise Exception(f"Dify API资源未找到 (404): {url}")
                elif response.status_code == 403:
                    raise Exception(f"Dify API访问被拒绝 (403): 请检查您的权限")
                
                response.raise_for_status()
                
                # 检查响应内容类型
                content_type = response.headers.get('content-type', '')
                if 'application/json' not in content_type and len(response.content) > 0:
                    # 如果不是JSON响应，输出完整的响应内容以供诊断
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
                    
                    print(f"Dify API警告: 返回非JSON响应")
                    print(f"响应状态码: {response.status_code}")
                    print(f"内容类型: {content_type}")
                    print(f"响应URL: {url}")
                    print(f"响应内容长度: {len(response.content)} 字节")
                    print(f"完整响应内容:\n{response_text}")
                
                return response
            except requests.exceptions.RequestException as e:
                if attempt == self.max_retries - 1:  # 最后一次尝试失败
                    raise e
                print(f"Dify API请求失败，正在重试... ({attempt + 1}/{self.max_retries}): {e}")
                import time
                time.sleep(self.retry_interval)  # 等待指定时间后重试

        raise Exception("Dify API请求失败，已达到最大重试次数")