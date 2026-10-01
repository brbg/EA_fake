"""生成代码的结构自检（纯标准库，不调 LLM、不抛异常）。

从 tests/test_ruoyi_gen.py 逐字搬到生产侧：原来这两个检查器只活在测试里，
测试实际是「测自己的副本」——生产代码改了它不会红。搬到这里后，
测试改为 import 本模块，就变成了对生产实现的回归锁。

注意：`declared |= {'BusinessType'}` 这类若依专有知识是刻意保留的，
不要「清洁化」，否则会改变既有测试的通过阈值。
"""

import re
from html.parser import HTMLParser

JAVA_LANG = {
    'String', 'Long', 'Integer', 'Boolean', 'Double', 'Float', 'Object', 'Override', 'Exception',
    'Byte', 'Short', 'Character', 'Void', 'Math', 'System', 'RuntimeException',
}


def java_lint(src):
    """剥掉注释与字符串字面量后，检查用到的每个类型是否可解析（漏 import 是最大的编译杀手）。"""
    body = re.sub(r'/\*.*?\*/', '', src, flags=re.S)
    body = re.sub(r'//[^\n]*', '', body)
    body = re.sub(r'"(?:\\.|[^"\\])*"', '""', body)
    body = re.sub(r"'(?:\\.|[^'\\])*'", "''", body)

    imported = set()
    for m in re.finditer(r'^import\s+([\w.]+);', src, re.M):
        imported.add(m.group(1).rsplit('.', 1)[-1])
    declared = set(re.findall(r'\b(?:class|interface|enum)\s+([A-Z]\w*)', body))
    declared |= {'BusinessType'}   # 枚举常量用法 BusinessType.INSERT —— 已在 import 里

    # 排除静态成员/枚举常量访问（ToStringStyle.MULTI_LINE_STYLE、BusinessType.INSERT）
    used = set(re.findall(r'(?<![.\w])([A-Z][A-Za-z0-9_]*)\b', body))
    unresolved = sorted(t for t in used if t not in imported and t not in JAVA_LANG and t not in declared)

    problems = []
    if unresolved:
        problems.append(f'缺 import：{unresolved}')
    if src.count('{') != src.count('}'):
        problems.append(f"花括号不配对（{src.count('{')} vs {src.count('}')}）")
    if src.count('(') != src.count(')'):
        problems.append('圆括号不配对')
    if src.count('"') % 2:
        problems.append('双引号不配对')
    return problems


class _TagBalancer(HTMLParser):
    """Vue 模板的标签配平检查（自闭合标签与 HTML 空元素不参与配对）。"""

    VOID = {'br', 'hr', 'img', 'input', 'meta', 'link', 'area', 'base', 'col', 'embed', 'source', 'track', 'wbr'}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.errors = []

    def handle_starttag(self, tag, attrs):
        if tag in self.VOID:
            return
        self.stack.append((tag, self.getpos()))

    def handle_startendtag(self, tag, attrs):
        pass   # <el-table-column ... /> 自闭合，无需配对

    def handle_endtag(self, tag):
        if tag in self.VOID:
            return
        if not self.stack:
            self.errors.append(f'多余的 </{tag}> @{self.getpos()}')
            return
        top, _pos = self.stack.pop()
        if top != tag:
            self.errors.append(f'</{tag}> 与 <{top}> 不匹配 @{self.getpos()}')


def vue_lint(src):
    """检查模板与脚本的内部引用是否自洽（ref 名、字典变量、组件名）。"""
    problems = []
    script = src[src.index('<script'):]

    # ref="xRef" 与 proxy.$refs["xRef"] / proxy.resetForm("xRef") 必须一致
    template_refs = set(re.findall(r'\bref="(\w+)"', src))
    used_refs = set(re.findall(r'\$refs\["(\w+)"\]', script)) | set(re.findall(r'resetForm\("(\w+)"\)', script))
    missing = used_refs - template_refs
    if missing:
        problems.append(f'脚本引用了模板里不存在的 ref：{sorted(missing)}')

    # 模板里 `dict in X` 的 X 必须来自 useDict 解构
    dict_vars = set(re.findall(r'\bdict in (\w+)', src))
    m = re.search(r'const\s*\{([^}]*)\}\s*=\s*useDict\(([^)]*)\)', script)
    declared_dicts = set()
    if m:
        declared_dicts = {x.strip() for x in m.group(1).split(',') if x.strip()}
    unknown = dict_vars - declared_dicts
    if unknown:
        problems.append(f'模板用了未声明的字典变量：{sorted(unknown)}')

    # 模板标签必须正确嵌套（栈式配平，比计数可靠）
    template = src[:src.index('<script')]
    b = _TagBalancer()
    b.feed(template)
    b.close()
    problems += b.errors
    if b.stack:
        problems.append(f'未闭合的标签：{[t for t, _ in b.stack]}')

    # script setup 的 name 属性（tags-view/keep-alive 依赖）
    if not re.search(r'<script setup name="[A-Z]\w*"', src):
        problems.append('script setup 缺少 name 属性')
    return problems


def lint_generated_files(files):
    """对生成产物做结构自检。

    只收集、永不抛异常——调用方在纯函数之外的路由层，产物问题不该让整个生成失败。
    返回 (problems, checked_count)：problems 每条都带文件路径前缀（多文件场景要能定位）。
    """
    problems = []
    checked = 0
    for f in files or []:
        if not isinstance(f, dict):
            continue
        path = str(f.get('path') or f.get('name') or '<未知文件>')
        src = f.get('content')
        if not isinstance(src, str):
            continue
        lang = str(f.get('language') or '').strip().lower()
        try:
            if lang == 'java' or path.endswith('.java'):
                found = java_lint(src)
            elif lang == 'vue' or path.endswith('.vue'):
                found = vue_lint(src)
            else:
                continue   # xml / js / ts / sql / md 暂无检查器
            checked += 1
        except Exception as e:   # noqa: BLE001
            # 自检器本身出错也要如实报出来，不能静默当成「没问题」
            problems.append(f'{path}: 自检未完成（{type(e).__name__}: {e}）')
            continue
        problems.extend(f'{path}: {p}' for p in found)
    return problems, checked
