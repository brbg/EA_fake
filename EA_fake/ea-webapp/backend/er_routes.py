"""数据建模与 ER 模块（Blueprint）：ER 视图管理、AI 生成/优化、DDL、导入导出。

按「拆巨石」计划从 app.py 抽出，共享状态从 core.py 导入。
"""
import uuid
import datetime
import db
from flask import Blueprint, request, jsonify
from models import SimpleModel
from prompts import ER_SYSTEM_PROMPT
from core import (
    er_views_cache, data_dictionary_cache, AIService, ai_service_config, sessions_cache,
    load_model_from_cache, _require_user_id, _model_owned_by, _ai_parse_json_response,
)

er_bp = Blueprint('er', __name__)


class ERView:
    """ER实体关系图视图"""
    def __init__(self, project_id, name, description='', package_id=None):
        self.id = str(uuid.uuid4())[:8]
        self.project_id = project_id
        self.name = name
        self.description = description
        self.package_id = package_id
        self.entities = []
        self.relationships = []
        self.indexes = []
        self.created_at = datetime.datetime.now().isoformat()
        self.updated_at = datetime.datetime.now().isoformat()
        self.user_id = ''
        self.config = {}
    
    def add_entity(self, name, description='', table_name=None, is_weak_entity=False, x=100, y=100):
        """添加实体"""
        entity = {
            'id': str(uuid.uuid4())[:8],
            'name': name,
            'description': description,
            'table_name': table_name or name.lower().replace(' ', '_'),
            'is_weak_entity': is_weak_entity,
            'attributes': [],
            'x': x,
            'y': y,
            'width': 180,
            'height': 120,
            'created_at': datetime.datetime.now().isoformat()
        }
        self.entities.append(entity)
        return entity
    
    def add_attribute(self, entity_id, name, description='', data_type='string', length=255, 
                      is_primary_key=False, is_foreign_key=False, is_unique=False, 
                      is_nullable=True, default_value=None):
        """添加属性"""
        entity = next((e for e in self.entities if e['id'] == entity_id), None)
        if not entity:
            return None
        
        attribute = {
            'id': str(uuid.uuid4())[:8],
            'name': name,
            'description': description,
            'column_name': name.lower().replace(' ', '_'),
            'data_type': data_type,
            'length': length,
            'precision': None,
            'scale': None,
            'is_primary_key': is_primary_key,
            'is_foreign_key': is_foreign_key,
            'is_unique': is_unique,
            'is_nullable': is_nullable,
            'default_value': default_value,
            'created_at': datetime.datetime.now().isoformat()
        }
        entity['attributes'].append(attribute)
        return attribute
    
    def add_relationship(self, source_entity_id, target_entity_id, relationship_type='many_to_one',
                         source_cardinality='*', target_cardinality='1', is_identifying=False):
        """添加关系"""
        relationship = {
            'id': str(uuid.uuid4())[:8],
            'type': relationship_type,
            'source_entity_id': source_entity_id,
            'target_entity_id': target_entity_id,
            'source_cardinality': source_cardinality,
            'target_cardinality': target_cardinality,
            'is_identifying': is_identifying,
            'cascade_rule': {'delete': 'NO ACTION', 'update': 'CASCADE'},
            'description': '',
            'created_at': datetime.datetime.now().isoformat()
        }
        self.relationships.append(relationship)
        return relationship
    
    def add_index(self, entity_id, index_name, columns, index_type='btree', is_unique=False):
        """添加索引"""
        index = {
            'id': str(uuid.uuid4())[:8],
            'entity_id': entity_id,
            'name': index_name,
            'type': index_type,
            'columns': columns,
            'is_unique': is_unique,
            'is_primary_key': False,
            'description': '',
            'created_at': datetime.datetime.now().isoformat()
        }
        self.indexes.append(index)
        return index
    
    def to_dict(self):
        return {
            'id': self.id,
            'project_id': self.project_id,
            'name': self.name,
            'description': self.description,
            'package_id': self.package_id,
            'entities': self.entities,
            'relationships': self.relationships,
            'indexes': self.indexes,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'user_id': self.user_id,
            'config': self.config
        }

# ER视图缓存

# 数据字典缓存

# === AI数据建模功能 ===

def _ai_generate_er_data(requirements):
    """调用LLM从业务需求提取ER模型（实体/属性/关系）。AI未启用/失败返回None。"""
    if not ai_service_config.enabled:
        return None

    system_prompt = ER_SYSTEM_PROMPT
    messages = [
        {'role': 'system', 'content': system_prompt},
        {'role': 'user', 'content': requirements}
    ]
    result = AIService.chat_completion(messages, max_tokens=4096, temperature=0.3)
    if not isinstance(result, dict) or 'error' in result:
        return None
    try:
        content = result['choices'][0]['message']['content']
    except (KeyError, IndexError, TypeError):
        return None
    data = _ai_parse_json_response(content)
    if not isinstance(data, dict) or not isinstance(data.get('entities'), list):
        return None
    relationships = data.get('relationships')
    if not isinstance(relationships, list):
        relationships = []
    data['relationships'] = relationships
    return data


def _build_er_from_llm(view, data):
    """把LLM返回的ER结构化数据写入ERView（实体/属性/关系）。"""
    entities = data.get('entities', [])
    id_by_name = {}

    for i, ent in enumerate(entities):
        if not isinstance(ent, dict) or not ent.get('name'):
            continue
        entity = view.add_entity(
            ent['name'],
            ent.get('description', ''),
            x=100 + (i % 3) * 250,
            y=50 + (i // 3) * 180
        )
        id_by_name[ent['name']] = entity['id']

        for attr in (ent.get('attributes') or []):
            if not isinstance(attr, dict) or not attr.get('name'):
                continue
            view.add_attribute(
                entity['id'],
                attr['name'],
                attr.get('description', ''),
                data_type=attr.get('data_type', 'string'),
                length=attr.get('length', 255),
                is_primary_key=bool(attr.get('is_primary_key')),
                is_foreign_key=bool(attr.get('is_foreign_key')),
                is_nullable=attr.get('is_nullable', True)
            )

    for rel in data.get('relationships', []):
        if not isinstance(rel, dict):
            continue
        src = id_by_name.get(rel.get('source'))
        tgt = id_by_name.get(rel.get('target'))
        if not src or not tgt or src == tgt:
            continue
        view.add_relationship(
            src,
            tgt,
            relationship_type=rel.get('type', 'many_to_one'),
            source_cardinality=str(rel.get('source_cardinality') or '1'),
            target_cardinality=str(rel.get('target_cardinality') or '1')
        )

    return view


def ai_generate_er_model(view, requirements):
    """AI生成ER模型（优先LLM，失败/未启用时回退关键词解析）"""
    ai_data = _ai_generate_er_data(requirements)
    if ai_data is not None:
        return _build_er_from_llm(view, ai_data)

    # 从业务需求中提取实体
    entities_to_create = extract_entities_from_requirements(requirements)
    
    # 创建实体
    y_offset = 50
    for i, entity_info in enumerate(entities_to_create):
        entity = view.add_entity(
            entity_info['name'],
            entity_info['description'],
            x=100 + (i % 3) * 250,
            y=y_offset + (i // 3) * 180
        )
        
        # 为每个实体添加属性
        for attr in entity_info['attributes']:
            view.add_attribute(
                entity['id'],
                attr['name'],
                attr['description'],
                data_type=attr.get('data_type', 'string'),
                length=attr.get('length', 255),
                is_primary_key=attr.get('is_primary_key', False),
                is_nullable=attr.get('is_nullable', True)
            )
    
    # 添加关系
    add_relationships_between_entities(view, entities_to_create)
    
    return view

def extract_entities_from_requirements(requirements):
    """从业务需求中提取实体"""
    req_lower = requirements.lower()
    
    entities = []
    
    # 用户实体
    if any(keyword in req_lower for keyword in ['用户', '会员', 'customer', 'user']):
        entities.append({
            'name': '用户',
            'description': '系统用户信息',
            'attributes': [
                {'name': '用户ID', 'description': '用户唯一标识', 'data_type': 'integer', 'is_primary_key': True},
                {'name': '用户名', 'description': '登录用户名', 'data_type': 'string', 'length': 50, 'is_nullable': False},
                {'name': '密码', 'description': '加密后的密码', 'data_type': 'string', 'length': 255, 'is_nullable': False},
                {'name': '邮箱', 'description': '用户邮箱', 'data_type': 'string', 'length': 100},
                {'name': '手机号', 'description': '用户手机号', 'data_type': 'string', 'length': 20},
                {'name': '创建时间', 'description': '用户创建时间', 'data_type': 'datetime'}
            ]
        })
    
    # 订单实体
    if any(keyword in req_lower for keyword in ['订单', 'order', '交易']):
        entities.append({
            'name': '订单',
            'description': '订单信息',
            'attributes': [
                {'name': '订单ID', 'description': '订单唯一标识', 'data_type': 'integer', 'is_primary_key': True},
                {'name': '用户ID', 'description': '关联用户', 'data_type': 'integer', 'is_foreign_key': True},
                {'name': '订单编号', 'description': '订单编号', 'data_type': 'string', 'length': 50},
                {'name': '订单金额', 'description': '订单总金额', 'data_type': 'decimal', 'length': '10,2'},
                {'name': '订单状态', 'description': '订单状态', 'data_type': 'string', 'length': 20},
                {'name': '创建时间', 'description': '订单创建时间', 'data_type': 'datetime'}
            ]
        })
    
    # 产品实体
    if any(keyword in req_lower for keyword in ['产品', '商品', 'product', 'goods']):
        entities.append({
            'name': '产品',
            'description': '产品信息',
            'attributes': [
                {'name': '产品ID', 'description': '产品唯一标识', 'data_type': 'integer', 'is_primary_key': True},
                {'name': '产品名称', 'description': '产品名称', 'data_type': 'string', 'length': 100, 'is_nullable': False},
                {'name': '产品编码', 'description': '产品编码', 'data_type': 'string', 'length': 50},
                {'name': '价格', 'description': '产品价格', 'data_type': 'decimal', 'length': '10,2'},
                {'name': '库存数量', 'description': '库存数量', 'data_type': 'integer'},
                {'name': '创建时间', 'description': '创建时间', 'data_type': 'datetime'}
            ]
        })
    
    # 订单明细实体
    if '订单' in requirements and '产品' in requirements:
        entities.append({
            'name': '订单明细',
            'description': '订单明细信息',
            'attributes': [
                {'name': '明细ID', 'description': '明细唯一标识', 'data_type': 'integer', 'is_primary_key': True},
                {'name': '订单ID', 'description': '关联订单', 'data_type': 'integer', 'is_foreign_key': True},
                {'name': '产品ID', 'description': '关联产品', 'data_type': 'integer', 'is_foreign_key': True},
                {'name': '数量', 'description': '购买数量', 'data_type': 'integer'},
                {'name': '单价', 'description': '单价', 'data_type': 'decimal', 'length': '10,2'},
                {'name': '金额', 'description': '明细金额', 'data_type': 'decimal', 'length': '10,2'}
            ]
        })
    
    # 角色实体
    if any(keyword in req_lower for keyword in ['角色', '权限', 'role', 'permission']):
        entities.append({
            'name': '角色',
            'description': '角色信息',
            'attributes': [
                {'name': '角色ID', 'description': '角色唯一标识', 'data_type': 'integer', 'is_primary_key': True},
                {'name': '角色名称', 'description': '角色名称', 'data_type': 'string', 'length': 50, 'is_nullable': False},
                {'name': '角色描述', 'description': '角色描述', 'data_type': 'string', 'length': 200},
                {'name': '创建时间', 'description': '创建时间', 'data_type': 'datetime'}
            ]
        })
    
    return entities

def add_relationships_between_entities(view, entities):
    """添加实体间的关系"""
    # 查找实体
    user_entity = next((e for e in view.entities if e['name'] == '用户'), None)
    order_entity = next((e for e in view.entities if e['name'] == '订单'), None)
    product_entity = next((e for e in view.entities if e['name'] == '产品'), None)
    order_detail_entity = next((e for e in view.entities if e['name'] == '订单明细'), None)
    role_entity = next((e for e in view.entities if e['name'] == '角色'), None)
    
    # 用户 -> 订单 (一对多)
    if user_entity and order_entity:
        view.add_relationship(user_entity['id'], order_entity['id'], 'one_to_many', '1', '*')
    
    # 订单 -> 订单明细 (一对多)
    if order_entity and order_detail_entity:
        view.add_relationship(order_entity['id'], order_detail_entity['id'], 'one_to_many', '1', '*')
    
    # 产品 -> 订单明细 (一对多)
    if product_entity and order_detail_entity:
        view.add_relationship(product_entity['id'], order_detail_entity['id'], 'one_to_many', '1', '*')

def ai_optimize_er_model(view):
    """AI数据库设计优化"""
    issues = []
    suggestions = []
    
    # 检查范式
    normal_form_issues = check_normal_forms(view)
    issues.extend(normal_form_issues)
    
    # 检查索引
    index_issues = check_indexes(view)
    issues.extend(index_issues)
    
    # 检查数据类型
    data_type_issues = check_data_types(view)
    issues.extend(data_type_issues)
    
    # 检查命名规范
    naming_issues = check_naming_conventions(view)
    issues.extend(naming_issues)
    
    # 生成优化建议
    if len(issues) > 0:
        suggestions.append('根据以下问题进行优化：')
        for issue in issues[:3]:
            suggestions.append(f"• {issue['suggestion']}")
    
    return {
        'valid': len(issues) == 0,
        'total_entities': len(view.entities),
        'total_attributes': sum(len(e['attributes']) for e in view.entities),
        'total_relationships': len(view.relationships),
        'issues': issues,
        'suggestions': suggestions,
        'summary': f'优化分析完成：{len(issues)}个问题'
    }

def check_normal_forms(view):
    """检查数据库范式"""
    issues = []
    
    # 检查1NF：所有属性都是原子值
    for entity in view.entities:
        for attr in entity['attributes']:
            if attr['data_type'] in ['text', 'json'] and attr.get('is_primary_key', False):
                issues.append({
                    'type': '1nf_violation',
                    'severity': 'error',
                    'message': f"实体'{entity['name']}'的属性'{attr['name']}'使用TEXT/JSON类型作为主键，违反1NF",
                    'suggestion': '请使用原子类型（如INT、BIGINT）作为主键'
                })
    
    # 检查主键是否存在
    for entity in view.entities:
        has_pk = any(a.get('is_primary_key', False) for a in entity['attributes'])
        if not has_pk:
            issues.append({
                'type': 'no_primary_key',
                'severity': 'error',
                'message': f"实体'{entity['name']}'没有定义主键",
                'suggestion': '请为实体添加主键'
            })
    
    # 检查外键引用
    for rel in view.relationships:
        source_entity = next((e for e in view.entities if e['id'] == rel['source_entity_id']), None)
        target_entity = next((e for e in view.entities if e['id'] == rel['target_entity_id']), None)
        
        if source_entity and target_entity:
            # 检查目标实体是否有主键
            target_has_pk = any(a.get('is_primary_key', False) for a in target_entity['attributes'])
            if not target_has_pk:
                issues.append({
                    'type': 'fk_target_no_pk',
                    'severity': 'warning',
                    'message': f"关系中目标实体'{target_entity['name']}'没有主键",
                    'suggestion': '请先为目标实体定义主键'
                })
    
    return issues

def check_indexes(view):
    """检查索引"""
    issues = []
    
    for entity in view.entities:
        # 检查外键是否有索引
        fk_columns = [a for a in entity['attributes'] if a.get('is_foreign_key', False)]
        indexed_columns = set()
        
        for idx in view.indexes:
            if idx['entity_id'] == entity['id']:
                indexed_columns.update(idx['columns'])
        
        for fk in fk_columns:
            if fk['name'] not in indexed_columns:
                issues.append({
                    'type': 'missing_fk_index',
                    'severity': 'warning',
                    'message': f"实体'{entity['name']}'的外键'{fk['name']}'缺少索引",
                    'suggestion': '建议为外键创建索引以提高查询性能'
                })
    
    # 检查重复索引
    for entity in view.entities:
        entity_indexes = [idx for idx in view.indexes if idx['entity_id'] == entity['id']]
        for i, idx1 in enumerate(entity_indexes):
            for j, idx2 in enumerate(entity_indexes):
                if i < j and set(idx1['columns']) == set(idx2['columns']):
                    issues.append({
                        'type': 'duplicate_index',
                        'severity': 'warning',
                        'message': f"实体'{entity['name']}'存在重复索引: {idx1['name']} 和 {idx2['name']}",
                        'suggestion': '请删除重复的索引'
                    })
    
    return issues

def check_data_types(view):
    """检查数据类型"""
    issues = []
    
    for entity in view.entities:
        for attr in entity['attributes']:
            # 检查ID字段是否使用合适的类型
            if 'id' in attr['name'].lower() or 'ID' in attr['name']:
                if attr['data_type'] not in ['integer', 'bigint']:
                    issues.append({
                        'type': 'wrong_id_type',
                        'severity': 'warning',
                        'message': f"实体'{entity['name']}'的属性'{attr['name']}'使用了不合适的数据类型'{attr['data_type']}'",
                        'suggestion': '建议使用integer或bigint类型作为ID字段'
                    })
            
            # 检查金额字段是否使用decimal
            if any(keyword in attr['name'].lower() for keyword in ['金额', '价格', 'price', 'amount', 'cost']):
                if attr['data_type'] not in ['decimal']:
                    issues.append({
                        'type': 'wrong_amount_type',
                        'severity': 'warning',
                        'message': f"实体'{entity['name']}'的金额字段'{attr['name']}'使用了'{attr['data_type']}'类型",
                        'suggestion': '建议使用decimal类型存储金额以避免精度丢失'
                    })
            
            # 检查字符串长度是否合理
            if attr['data_type'] == 'string' and attr.get('length', 255) > 1000:
                issues.append({
                    'type': 'string_too_long',
                    'severity': 'warning',
                    'message': f"实体'{entity['name']}'的属性'{attr['name']}'字符串长度{attr['length']}过长",
                    'suggestion': '如果需要存储大量文本，建议使用text类型'
                })
    
    return issues

def check_naming_conventions(view):
    """检查命名规范"""
    issues = []
    
    for entity in view.entities:
        # 检查实体命名是否包含空格
        if ' ' in entity['name']:
            issues.append({
                'type': 'entity_name_space',
                'severity': 'warning',
                'message': f"实体'{entity['name']}'名称包含空格",
                'suggestion': '建议使用下划线或驼峰命名，避免空格'
            })
        
        for attr in entity['attributes']:
            # 检查属性命名
            if ' ' in attr['name']:
                issues.append({
                    'type': 'attr_name_space',
                    'severity': 'minor',
                    'message': f"实体'{entity['name']}'的属性'{attr['name']}'名称包含空格",
                    'suggestion': '建议使用下划线或驼峰命名'
                })
    
    return issues

def generate_ddl(view, db_type='mysql'):
    """生成DDL脚本"""
    ddl = []
    type_mapping = DATA_TYPE_MAPPING.get(db_type, DATA_TYPE_MAPPING['mysql'])
    
    # 添加注释
    ddl.append(f"-- ER模型: {view.name}")
    ddl.append(f"-- 生成时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    ddl.append(f"-- 目标数据库: {DATABASE_TYPES.get(db_type, {'name': db_type})['name']}")
    ddl.append("")
    
    # 生成表
    for entity in view.entities:
        table_name = entity['table_name']
        ddl.append(f"CREATE TABLE IF NOT EXISTS `{table_name}` (")
        
        columns = []
        pk_columns = []
        
        for attr in entity['attributes']:
            col_type = type_mapping.get(attr['data_type'], 'VARCHAR')
            col_name = attr['column_name']
            
            # 处理数据类型参数
            if col_type == 'VARCHAR' and attr.get('length'):
                col_spec = f"`{col_name}` {col_type}({attr['length']})"
            elif col_type in ['DECIMAL', 'NUMERIC'] and attr.get('length'):
                col_spec = f"`{col_name}` {col_type}({attr['length']})"
            else:
                col_spec = f"`{col_name}` {col_type}"
            
            # 添加约束
            if not attr.get('is_nullable', True):
                col_spec += ' NOT NULL'
            if attr.get('default_value'):
                col_spec += f" DEFAULT '{attr['default_value']}'"
            if attr.get('is_unique'):
                col_spec += ' UNIQUE'
            
            columns.append(f"    {col_spec}")
            
            if attr.get('is_primary_key'):
                pk_columns.append(col_name)
        
        ddl.extend(columns)
        
        # 添加主键
        if pk_columns:
            ddl.append(f"    PRIMARY KEY (`{pk_columns[0]}`)")
        
        ddl.append(") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;")
        ddl.append("")
    
    # 生成外键约束
    for rel in view.relationships:
        source_entity = next((e for e in view.entities if e['id'] == rel['source_entity_id']), None)
        target_entity = next((e for e in view.entities if e['id'] == rel['target_entity_id']), None)
        
        if source_entity and target_entity:
            # 找到外键字段
            fk_attr = next((a for a in source_entity['attributes'] if a.get('is_foreign_key')), None)
            target_pk = next((a for a in target_entity['attributes'] if a.get('is_primary_key')), None)
            
            if fk_attr and target_pk:
                ddl.append(f"ALTER TABLE `{source_entity['table_name']}`")
                ddl.append(f"ADD CONSTRAINT `fk_{source_entity['table_name']}_{target_entity['table_name']}`")
                ddl.append(f"FOREIGN KEY (`{fk_attr['column_name']}`)")
                ddl.append(f"REFERENCES `{target_entity['table_name']}`(`{target_pk['column_name']}`)")
                ddl.append(f"ON DELETE {rel['cascade_rule'].get('delete', 'NO ACTION')}")
                ddl.append(f"ON UPDATE {rel['cascade_rule'].get('update', 'CASCADE')};")
                ddl.append("")
    
    # 生成索引
    for idx in view.indexes:
        entity = next((e for e in view.entities if e['id'] == idx['entity_id']), None)
        if entity:
            unique_str = 'UNIQUE' if idx['is_unique'] else ''
            columns_str = ', '.join([f"`{c}`" for c in idx['columns']])
            ddl.append(f"CREATE {unique_str} INDEX `{idx['name']}` ON `{entity['table_name']}`({columns_str});")
    
    return '\n'.join(ddl)

def ai_generate_data_dictionary(project_id, view_id=None):
    """AI生成数据字典"""
    dictionary = {
        'project_id': project_id,
        'fields': [],
        'generated_at': datetime.datetime.now().isoformat()
    }
    
    # 如果指定了视图，从视图中提取字段
    if view_id and view_id in er_views_cache:
        view = er_views_cache[view_id]
        for entity in view.entities:
            for attr in entity['attributes']:
                field_info = {
                    'field_name': attr['column_name'],
                    'description': attr['description'] or f"{entity['name']}的{attr['name']}",
                    'data_type': attr['data_type'],
                    'length': attr.get('length'),
                    'precision': attr.get('precision'),
                    'scale': attr.get('scale'),
                    'default_value': attr.get('default_value'),
                    'is_primary_key': attr.get('is_primary_key', False),
                    'is_foreign_key': attr.get('is_foreign_key', False),
                    'is_unique': attr.get('is_unique', False),
                    'is_nullable': attr.get('is_nullable', True),
                    'entity_name': entity['name'],
                    'table_name': entity['table_name']
                }
                dictionary['fields'].append(field_info)
    
    return dictionary

# === ER建模API ===

@er_bp.route('/api/v1/project/<project_id>/er/view/create', methods=['POST'])
def create_er_view(project_id):
    """创建ER视图"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    data = request.json
    name = data.get('name', '未命名ER视图')
    description = data.get('description', '')
    package_id = data.get('package_id')
    
    view = ERView(project_id, name, description, package_id)
    view.user_id = sessions_cache[session_id]['user_id']
    
    er_views_cache[view.id] = view
    
    return jsonify({
        'message': 'ER视图创建成功',
        'view': view.to_dict()
    })

@er_bp.route('/api/v1/project/<project_id>/er/view/list', methods=['GET'])
def get_er_views(project_id):
    """获取ER视图列表"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    views = [v.to_dict() for v in er_views_cache.values() if v.project_id == project_id]
    
    return jsonify({'views': views})

@er_bp.route('/api/v1/er/view/<view_id>', methods=['GET'])
def get_er_view(view_id):
    """获取ER视图详情"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    if view_id not in er_views_cache:
        return jsonify({'error': '视图不存在'}), 404
    
    view = er_views_cache[view_id]
    
    return jsonify({'view': view.to_dict()})

@er_bp.route('/api/v1/er/view/<view_id>/save', methods=['PUT'])
def save_er_view(view_id):
    """保存ER模型"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    if view_id not in er_views_cache:
        return jsonify({'error': '视图不存在'}), 404
    
    view = er_views_cache[view_id]
    data = request.json
    
    if 'name' in data:
        view.name = data['name']
    if 'description' in data:
        view.description = data['description']
    if 'entities' in data:
        view.entities = data['entities']
    if 'relationships' in data:
        view.relationships = data['relationships']
    if 'indexes' in data:
        view.indexes = data['indexes']
    
    view.updated_at = datetime.datetime.now().isoformat()
    
    return jsonify({'message': 'ER模型保存成功', 'view': view.to_dict()})

@er_bp.route('/api/v1/er/view/<view_id>/ai/generate', methods=['POST'])
def ai_generate_er_model_api(view_id):
    """AI生成ER模型"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    if view_id not in er_views_cache:
        return jsonify({'error': '视图不存在'}), 404
    
    view = er_views_cache[view_id]
    data = request.json
    requirements = data.get('requirements', '')
    
    ai_generate_er_model(view, requirements)
    
    return jsonify({
        'message': 'AI ER模型生成成功',
        'view': view.to_dict(),
        'generated_entities': len(view.entities),
        'generated_relationships': len(view.relationships)
    })

@er_bp.route('/api/v1/er/view/<view_id>/ai/optimize', methods=['POST'])
def ai_optimize_er_model_api(view_id):
    """AI数据库设计优化"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    if view_id not in er_views_cache:
        return jsonify({'error': '视图不存在'}), 404
    
    view = er_views_cache[view_id]
    result = ai_optimize_er_model(view)
    
    return jsonify({
        'message': 'AI设计优化完成',
        'optimization': result
    })

@er_bp.route('/api/v1/er/view/<view_id>/ddl/generate', methods=['POST'])
def generate_ddl_api(view_id):
    """生成DDL脚本"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    if view_id not in er_views_cache:
        return jsonify({'error': '视图不存在'}), 404
    
    view = er_views_cache[view_id]
    data = request.json
    db_type = data.get('db_type', 'mysql')
    
    ddl = generate_ddl(view, db_type)
    
    return jsonify({
        'message': 'DDL脚本生成成功',
        'db_type': db_type,
        'ddl': ddl,
        'entity_count': len(view.entities)
    })

@er_bp.route('/api/v1/er/reverse/import', methods=['POST'])
def reverse_engineering_api():
    """数据库逆向工程"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    data = request.json
    db_type = data.get('db_type', 'mysql')
    connection_info = data.get('connection', {})
    tables = data.get('tables', [])
    
    # 模拟逆向工程结果
    project_id = data.get('project_id', 'default')
    view = ERView(project_id, f"逆向工程_{db_type}", "通过逆向工程生成")
    
    # 模拟导入的表
    sample_tables = [
        {
            'name': 'users',
            'columns': [
                {'name': 'id', 'type': 'integer', 'is_pk': True},
                {'name': 'username', 'type': 'string', 'length': 50},
                {'name': 'email', 'type': 'string', 'length': 100},
                {'name': 'created_at', 'type': 'datetime'}
            ]
        },
        {
            'name': 'orders',
            'columns': [
                {'name': 'id', 'type': 'integer', 'is_pk': True},
                {'name': 'user_id', 'type': 'integer', 'is_fk': True},
                {'name': 'amount', 'type': 'decimal', 'length': '10,2'},
                {'name': 'status', 'type': 'string', 'length': 20}
            ]
        }
    ]
    
    for i, table in enumerate(sample_tables):
        entity = view.add_entity(
            table['name'].replace('_', ' ').title(),
            f"{table['name']}表",
            table['name'],
            x=100 + i * 250,
            y=100
        )
        
        for col in table['columns']:
            view.add_attribute(
                entity['id'],
                col['name'].replace('_', ' ').title(),
                f"{col['name']}字段",
                data_type=col['type'],
                length=col.get('length', 255),
                is_primary_key=col.get('is_pk', False),
                is_foreign_key=col.get('is_fk', False)
            )
    
    # 添加关系
    if len(view.entities) >= 2:
        view.add_relationship(view.entities[0]['id'], view.entities[1]['id'], 'one_to_many')
    
    er_views_cache[view.id] = view
    
    return jsonify({
        'message': '逆向工程完成',
        'view': view.to_dict(),
        'imported_tables': len(sample_tables),
        'imported_columns': sum(len(t['columns']) for t in sample_tables)
    })

@er_bp.route('/api/v1/project/<project_id>/data/dictionary', methods=['GET', 'PUT'])
def manage_data_dictionary(project_id):
    """数据字典管理"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    if request.method == 'GET':
        # 获取数据字典
        if project_id in data_dictionary_cache:
            return jsonify({'dictionary': data_dictionary_cache[project_id]})
        return jsonify({'dictionary': {'project_id': project_id, 'fields': []}})
    
    elif request.method == 'PUT':
        # 保存数据字典
        data = request.json
        data_dictionary_cache[project_id] = data
        return jsonify({'message': '数据字典保存成功', 'dictionary': data})

@er_bp.route('/api/v1/project/<project_id>/data/dictionary/ai/generate', methods=['POST'])
def ai_generate_data_dictionary_api(project_id):
    """AI生成数据字典"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    data = request.json
    view_id = data.get('view_id')
    
    dictionary = ai_generate_data_dictionary(project_id, view_id)
    data_dictionary_cache[project_id] = dictionary
    
    return jsonify({
        'message': 'AI数据字典生成成功',
        'dictionary': dictionary,
        'field_count': len(dictionary['fields'])
    })

@er_bp.route('/api/v1/er/view/<view_id>/export', methods=['POST'])
def export_er_view(view_id):
    """导出ER视图"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    if view_id not in er_views_cache:
        return jsonify({'error': '视图不存在'}), 404
    
    view = er_views_cache[view_id]
    data = request.json
    export_format = data.get('format', 'json')
    
    export_data = {
        'view': view.to_dict(),
        'exported_at': datetime.datetime.now().isoformat(),
        'format': export_format
    }
    
    return jsonify({
        'message': 'ER视图导出成功',
        'export_data': export_data
    })

@er_bp.route('/api/v1/er/database/types', methods=['GET'])
def get_database_types():
    """获取支持的数据库类型"""
    session_id = request.headers.get('X-Session-Id')
    if session_id not in sessions_cache:
        return jsonify({'error': '未登录'}), 401
    
    types = []
    for key, value in DATABASE_TYPES.items():
        types.append({
            'id': key,
            'name': value['name'],
            'port': value['port']
        })
    
    return jsonify({'types': types})
