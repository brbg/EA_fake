"""核心数据类：Project（项目）与 SimpleModel（模型）。"""
import uuid
import datetime


class Project:
    """项目类"""
    def __init__(self, name, description='', owner_id='', industry='software', visibility='private'):
        self.id = str(uuid.uuid4())[:8]
        self.name = name
        self.description = description
        self.owner_id = owner_id
        self.created_at = datetime.datetime.now().isoformat()
        self.updated_at = datetime.datetime.now().isoformat()
        self.status = 'active'
        self.visibility = visibility
        self.industry = industry
        self.members = []
        self.permissions = {}
        self.packages = []
        self.roles = []
        self.model_id = None
        self.settings = {
            'global_style': 'default',
            'font_family': 'Arial',
            'font_size': 12,
            'color_scheme': 'blue',
            'templates': [],
            'permissions_preset': 'default',
            'industry_template': industry,
            'integrations': {}
        }
        self.health_check = {
            'score': 100,
            'issues': [],
            'suggestions': []
        }

    def add_member(self, user_id, role='viewer'):
        """添加成员"""
        if user_id not in [m['user_id'] for m in self.members]:
            self.members.append({
                'user_id': user_id,
                'role': role,
                'joined_at': datetime.datetime.now().isoformat()
            })
            self.permissions[user_id] = role
            self.updated_at = datetime.datetime.now().isoformat()

    def remove_member(self, user_id):
        """移除成员"""
        self.members = [m for m in self.members if m['user_id'] != user_id]
        if user_id in self.permissions:
            del self.permissions[user_id]
        self.updated_at = datetime.datetime.now().isoformat()

    def update_permission(self, user_id, role):
        """更新权限"""
        self.permissions[user_id] = role
        for m in self.members:
            if m['user_id'] == user_id:
                m['role'] = role
        self.updated_at = datetime.datetime.now().isoformat()

    def add_package(self, name, description='', parent_id=None):
        """添加包"""
        package = {
            'id': str(uuid.uuid4())[:8],
            'name': name,
            'description': description,
            'parent_id': parent_id,
            'order_num': len(self.packages),
            'created_at': datetime.datetime.now().isoformat(),
            'updated_at': datetime.datetime.now().isoformat()
        }
        self.packages.append(package)
        self.updated_at = datetime.datetime.now().isoformat()
        return package

    def add_role(self, role_name, description='', permissions=None):
        """添加角色"""
        if permissions is None:
            permissions = {
                'read': True,
                'write': False,
                'edit': False,
                'delete': False,
                'validate': False,
                'export': False
            }
        role = {
            'id': str(uuid.uuid4())[:8],
            'name': role_name,
            'description': description,
            'permission_template': permissions,
            'created_at': datetime.datetime.now().isoformat(),
            'updated_at': datetime.datetime.now().isoformat()
        }
        self.roles.append(role)
        self.updated_at = datetime.datetime.now().isoformat()
        return role

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'owner_id': self.owner_id,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'status': self.status,
            'visibility': self.visibility,
            'industry': self.industry,
            'members': self.members,
            'permissions': self.permissions,
            'packages': self.packages,
            'roles': self.roles,
            'model_id': self.model_id,
            'settings': self.settings,
            'health_check': self.health_check
        }

    @staticmethod
    def from_dict(data):
        project = Project(
            data.get('name', ''),
            data.get('description', ''),
            data.get('owner_id', ''),
            data.get('industry', 'software'),
            data.get('visibility', 'private')
        )
        project.id = data.get('id', project.id)
        project.created_at = data.get('created_at', project.created_at)
        project.updated_at = data.get('updated_at', project.updated_at)
        project.status = data.get('status', project.status)
        project.visibility = data.get('visibility', project.visibility)
        project.industry = data.get('industry', project.industry)
        project.members = data.get('members', [])
        project.permissions = data.get('permissions', {})
        project.packages = data.get('packages', [])
        project.roles = data.get('roles', [])
        project.model_id = data.get('model_id')
        project.settings = data.get('settings', project.settings)
        project.health_check = data.get('health_check', project.health_check)
        return project


class SimpleModel:
    """简化版ArchiMate模型"""
    def __init__(self, name, desc=''):
        self.name = name
        self.description = desc
        self.owner_id = ''
        self.elements = []
        self.relationships = []
        self.archimate_elements = []
        self.archimate_connections = []
        self.er_entities = []
        self.er_relations = []
        self.views = []
        self.version = '1.0.0'
        self.history = []

    def add_element(self, elem_type, name, desc='', x=100, y=100):
        elem = {
            'uuid': str(uuid.uuid4()),
            'type': elem_type,
            'name': name,
            'description': desc,
            'x': x,
            'y': y,
            'width': 120,
            'height': 70,
            'properties': {}
        }
        self.elements.append(elem)
        return elem

    def add_relationship(self, rel_type, source, target, name=''):
        rel = {
            'uuid': str(uuid.uuid4()),
            'type': rel_type,
            'source': source,
            'target': target,
            'name': name
        }
        self.relationships.append(rel)
        return rel

    def add_view(self, name, desc=''):
        view = {
            'uuid': str(uuid.uuid4()),
            'name': name,
            'description': desc,
            'nodes': [],
            'connections': []
        }
        self.views.append(view)
        return view

    def get_element(self, uuid):
        return next((e for e in self.elements if e['uuid'] == uuid), None)

    def get_relationship(self, uuid):
        return next((r for r in self.relationships if r['uuid'] == uuid), None)

    def get_view(self, uuid):
        return next((v for v in self.views if v['uuid'] == uuid), None)

    def delete_element(self, uuid):
        self.elements = [e for e in self.elements if e['uuid'] != uuid]
        self.relationships = [r for r in self.relationships if r['source'] != uuid and r['target'] != uuid]

    def delete_relationship(self, uuid):
        self.relationships = [r for r in self.relationships if r['uuid'] != uuid]

    def delete_view(self, uuid):
        self.views = [v for v in self.views if v['uuid'] != uuid]

    def save_version(self, comment=''):
        """保存版本"""
        version_entry = {
            'version': self.version,
            'timestamp': datetime.datetime.now().isoformat(),
            'comment': comment,
            'snapshot': {
                'elements': self.elements.copy(),
                'relationships': self.relationships.copy(),
                'views': self.views.copy()
            }
        }
        self.history.append(version_entry)

        # 更新版本号
        parts = self.version.split('.')
        parts[-1] = str(int(parts[-1]) + 1)
        self.version = '.'.join(parts)

    def restore_version(self, version_index):
        """恢复版本"""
        if version_index >= 0 and version_index < len(self.history):
            snapshot = self.history[version_index]['snapshot']
            self.elements = snapshot['elements'].copy()
            self.relationships = snapshot['relationships'].copy()
            self.views = snapshot['views'].copy()
            self.version = self.history[version_index]['version']
            return True
        return False

    def to_dict(self):
        return {
            'name': self.name,
            'description': self.description,
            'owner_id': self.owner_id,
            'elements': self.elements,
            'relationships': self.relationships,
            'archimate_elements': self.archimate_elements,
            'archimate_connections': self.archimate_connections,
            'er_entities': self.er_entities,
            'er_relations': self.er_relations,
            'views': self.views,
            'version': self.version,
            'history': self.history
        }

    @staticmethod
    def from_dict(data):
        model = SimpleModel(data.get('name', ''), data.get('description', ''))
        model.owner_id = data.get('owner_id', '')
        model.elements = data.get('elements', [])
        model.relationships = data.get('relationships', [])
        model.archimate_elements = data.get('archimate_elements', [])
        model.archimate_connections = data.get('archimate_connections', [])
        model.er_entities = data.get('er_entities', [])
        model.er_relations = data.get('er_relations', [])
        model.views = data.get('views', [])
        model.version = data.get('version', '1.0.0')
        model.history = data.get('history', [])
        return model


class Requirement:
    """需求类"""
    def __init__(self, project_id, name, description='', req_type='functional'):
        self.id = str(uuid.uuid4())[:8]
        self.project_id = project_id
        self.parent_id = None
        self.name = name
        self.description = description
        self.type = req_type
        self.priority = 'medium'
        self.difficulty = 'medium'
        self.status = 'draft'
        self.version = '1.0.0'
        self.user_id = ''
        self.assignee_id = ''
        self.plan_start_time = None
        self.plan_end_time = None
        self.actual_start_time = None
        self.actual_end_time = None
        self.created_at = datetime.datetime.now().isoformat()
        self.updated_at = datetime.datetime.now().isoformat()
        self.children = []
        self.trace_relations = []

    def add_child(self, child_req):
        """添加子需求"""
        self.children.append(child_req)
        child_req.parent_id = self.id

    def add_trace_relation(self, target_type, target_id, relation_type='implements'):
        """添加追溯关系"""
        relation = {
            'id': str(uuid.uuid4())[:8],
            'source_type': 'requirement',
            'source_id': self.id,
            'target_type': target_type,
            'target_id': target_id,
            'relation_type': relation_type,
            'created_at': datetime.datetime.now().isoformat()
        }
        self.trace_relations.append(relation)
        return relation

    def to_dict(self):
        return {
            'id': self.id,
            'project_id': self.project_id,
            'parent_id': self.parent_id,
            'name': self.name,
            'description': self.description,
            'type': self.type,
            'priority': self.priority,
            'difficulty': self.difficulty,
            'status': self.status,
            'version': self.version,
            'user_id': self.user_id,
            'assignee_id': self.assignee_id,
            'plan_start_time': self.plan_start_time,
            'plan_end_time': self.plan_end_time,
            'actual_start_time': self.actual_start_time,
            'actual_end_time': self.actual_end_time,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'children': [c.to_dict() for c in self.children],
            'trace_relations': self.trace_relations
        }


class TestCase:
    """测试用例类"""
    def __init__(self, project_id, name, description='', level='normal'):
        self.id = str(uuid.uuid4())[:8]
        self.project_id = project_id
        self.req_id = None
        self.use_case_id = None
        self.name = name
        self.description = description
        self.scene = ''
        self.level = level
        self.status = 'draft'
        self.version = '1.0.0'
        self.assignee_id = ''
        self.created_at = datetime.datetime.now().isoformat()
        self.updated_at = datetime.datetime.now().isoformat()
        self.steps = []
        self.trace_relations = []

    def add_step(self, step_num, content, expected_result):
        """添加测试步骤"""
        step = {
            'id': str(uuid.uuid4())[:8],
            'step_num': step_num,
            'content': content,
            'expected_result': expected_result,
            'created_at': datetime.datetime.now().isoformat()
        }
        self.steps.append(step)
        return step

    def add_trace_relation(self, target_type, target_id, relation_type='tests'):
        """添加追溯关系"""
        relation = {
            'id': str(uuid.uuid4())[:8],
            'source_type': 'testcase',
            'source_id': self.id,
            'target_type': target_type,
            'target_id': target_id,
            'relation_type': relation_type,
            'created_at': datetime.datetime.now().isoformat()
        }
        self.trace_relations.append(relation)
        return relation

    def to_dict(self):
        return {
            'id': self.id,
            'project_id': self.project_id,
            'req_id': self.req_id,
            'use_case_id': self.use_case_id,
            'name': self.name,
            'description': self.description,
            'scene': self.scene,
            'level': self.level,
            'status': self.status,
            'version': self.version,
            'assignee_id': self.assignee_id,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'steps': self.steps,
            'trace_relations': self.trace_relations
        }


class Defect:
    """缺陷类"""
    def __init__(self, project_id, name, description='', level='medium'):
        self.id = str(uuid.uuid4())[:8]
        self.project_id = project_id
        self.case_id = None
        self.req_id = None
        self.element_id = None
        self.name = name
        self.description = description
        self.reproduce_step = ''
        self.actual_result = ''
        self.expected_result = ''
        self.level = level
        self.status = 'new'
        self.assignee_id = ''
        self.created_at = datetime.datetime.now().isoformat()
        self.updated_at = datetime.datetime.now().isoformat()

    def to_dict(self):
        return {
            'id': self.id,
            'project_id': self.project_id,
            'case_id': self.case_id,
            'req_id': self.req_id,
            'element_id': self.element_id,
            'name': self.name,
            'description': self.description,
            'reproduce_step': self.reproduce_step,
            'actual_result': self.actual_result,
            'expected_result': self.expected_result,
            'level': self.level,
            'status': self.status,
            'assignee_id': self.assignee_id,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }


class Task:
    """任务类"""
    def __init__(self, project_id, name, description='', task_type='development'):
        self.id = str(uuid.uuid4())[:8]
        self.project_id = project_id
        self.parent_id = None
        self.req_id = None
        self.element_id = None
        self.name = name
        self.description = description
        self.type = task_type
        self.priority = 'medium'
        self.status = 'pending'
        self.progress = 0
        self.work_hours = 0
        self.assignee_id = ''
        self.plan_start_time = None
        self.plan_end_time = None
        self.actual_start_time = None
        self.actual_end_time = None
        self.created_at = datetime.datetime.now().isoformat()
        self.updated_at = datetime.datetime.now().isoformat()
        self.children = []
        self.dependencies = []

    def add_child(self, child_task):
        """添加子任务"""
        self.children.append(child_task)
        child_task.parent_id = self.id

    def add_dependency(self, pre_task_id, dependency_type='finish_to_start'):
        """添加依赖关系"""
        dependency = {
            'id': str(uuid.uuid4())[:8],
            'task_id': self.id,
            'pre_task_id': pre_task_id,
            'dependency_type': dependency_type,
            'created_at': datetime.datetime.now().isoformat()
        }
        self.dependencies.append(dependency)
        return dependency

    def to_dict(self):
        return {
            'id': self.id,
            'project_id': self.project_id,
            'parent_id': self.parent_id,
            'req_id': self.req_id,
            'element_id': self.element_id,
            'name': self.name,
            'description': self.description,
            'type': self.type,
            'priority': self.priority,
            'status': self.status,
            'progress': self.progress,
            'work_hours': self.work_hours,
            'assignee_id': self.assignee_id,
            'plan_start_time': self.plan_start_time,
            'plan_end_time': self.plan_end_time,
            'actual_start_time': self.actual_start_time,
            'actual_end_time': self.actual_end_time,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'children': [c.to_dict() for c in self.children],
            'dependencies': self.dependencies
        }
