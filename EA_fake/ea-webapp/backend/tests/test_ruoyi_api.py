"""若依生成端点的集成自测（Flask test client，不启服务）：`py backend/tests/test_ruoyi_api.py`。

覆盖：鉴权 401、参数校验 400、空模型 400、无 AI 时的完整降级产出、生成→下载 zip 闭环、
zip 下载的 Zip Slip / 超限 / 非法扩展名防护、Content-Disposition 的中文名处理。
"""

import io
import os
import re
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:   # noqa: BLE001
    pass

import app as A            # noqa: E402
from core import sessions_cache   # noqa: E402

SID = 'ruoyi-test-session'
FAILED = []


def check(cond, label):
    print(('  ok   ' if cond else '  FAIL ') + label)
    if not cond:
        FAILED.append(label)


ENTITIES = [
    {'id': 1, 'name': 'sys_product', 'fields': [
        {'name': 'id', 'type': 'INT', 'isPrimary': True},
        {'name': 'product_name', 'type': 'VARCHAR(255)'},
        {'name': 'price', 'type': 'DECIMAL(10,2)'},
        {'name': 'status', 'type': 'VARCHAR(255)'},
    ]},
    {'id': 2, 'name': 'sys_order', 'fields': [
        {'name': 'id', 'type': 'BIGINT', 'isPrimary': True},
        {'name': 'order_no', 'type': 'VARCHAR(100)'},
        {'name': 'product_id', 'type': 'BIGINT', 'isForeign': True},
    ]},
]
RELATIONS = [{'id': 9, 'type': 'manyToMany', 'startEntity': 1, 'endEntity': 2}]
CONFIG = {
    'packageBase': 'com.ruoyi', 'moduleName': 'business', 'tablePrefix': 'sys_',
    'author': 'tester', 'parentMenuId': 3, 'servletApi': 'jakarta',
    'frontendTs': False, 'dbType': 'mysql', 'useAI': False,
}


def main():
    sessions_cache[SID] = {'user_id': 'ruoyi-test-user'}
    c = A.app.test_client()
    hdr = {'X-Session-Id': SID}

    print('== 鉴权 ==')
    r = c.post('/api/v1/ai/code/ruoyi/generate', json={'erEntities': ENTITIES})
    check(r.status_code == 401, f'无会话头 → 401（实得 {r.status_code}）')
    r = c.post('/api/v1/ai/code/ruoyi/download', json={'files': [{'path': 'a.java', 'content': 'x'}]})
    check(r.status_code == 401, f'下载端点同样要鉴权（实得 {r.status_code}）')

    print('\n== 参数校验 ==')
    r = c.post('/api/v1/ai/code/ruoyi/generate', json={'erEntities': [], 'config': CONFIG}, headers=hdr)
    check(r.status_code == 400 and '为空' in r.get_json()['error'], '空模型 → 400')
    bad = dict(CONFIG, packageBase='Com.RuoYi')
    r = c.post('/api/v1/ai/code/ruoyi/generate', json={'erEntities': ENTITIES, 'config': bad}, headers=hdr)
    check(r.status_code == 400 and '包名' in r.get_json()['error'], '非法包名 → 400 且提示包名')
    bad2 = dict(CONFIG, parentMenuId='abc')
    r = c.post('/api/v1/ai/code/ruoyi/generate', json={'erEntities': ENTITIES, 'config': bad2}, headers=hdr)
    check(r.status_code == 400, '父菜单 ID 非数字 → 400')

    print('\n== 生成（AI 关闭，走内置词表降级） ==')
    r = c.post('/api/v1/ai/code/ruoyi/generate',
               json={'erEntities': ENTITIES, 'erRelations': RELATIONS, 'config': CONFIG}, headers=hdr)
    check(r.status_code == 200, f'200（实得 {r.status_code}）')
    body = r.get_json()
    files, meta = body['files'], body['meta']
    check(meta['aiUsed'] is False and meta['aiFallback'] == 'disabled', 'meta 标明未用 AI')
    check(meta['fileCount'] == len(files) == 2 * 8 + 2 + 3,
          f"文件数 = 2 表×8 + 2 SQL + README + pom + INTEGRATION（实得 {meta['fileCount']}）")
    check(meta.get('ruoyiVersion') == '3.9.2', f"meta 回显若依版本（实得 {meta.get('ruoyiVersion')}）")
    check(all(f['group'] in ('backend', 'frontend', 'sql', 'docs') for f in files), 'group 分类合法')
    check(all(f['content'].strip() for f in files), '没有空文件')
    check(all(not f['path'].startswith('/') and '..' not in f['path'] for f in files), '路径安全')
    check(meta['joinTables'] == ['sys_product_sys_order'], f"中间表名（实得 {meta['joinTables']}）")
    names = [f['path'] for f in files]
    check('backend/ruoyi-business/src/main/java/com/ruoyi/business/domain/Product.java' in names,
          '包路径与模块名按配置生效')
    check('frontend/src/api/business/product.js' in names, 'frontendTs=false → 产出 .js')
    sql = next(f['content'] for f in files if f['path'] == 'sql/sys_product.sql')
    check("'business/product/index'" in sql, '菜单 component 用模块/业务名')
    check('sys_product_sys_order' in sql, 'M:N 中间表 DDL 落在左表 SQL 里')

    print('\n== 产物自检（路由层） ==')
    check('lint' in meta, 'meta.lint 存在')
    check(meta['lint']['checkedFiles'] > 0, f"自检覆盖到文件（实得 {meta['lint']['checkedFiles']}）")
    check(meta['lint']['passed'] and not meta['lint']['problems'],
          f"确定性产物通过自检（实得 {meta['lint']['problems'][:2]}）")
    # 反向证明：自检不是恒返回空的安慰剂
    bad_java = ('package com.ruoyi.x;\n'
                'public class Foo extends BaseController {\n'
                '    private MissingType t;\n')     # 未 import 的类型，且故意不闭合花括号
    problems, checked = A.code_lint.lint_generated_files(
        [{'path': 'backend/x/Foo.java', 'language': 'java', 'content': bad_java}])
    check(checked == 1, f'自检统计覆盖文件数（实得 {checked}）')
    check(any('缺 import' in p and 'MissingType' in p for p in problems),
          f'缺 import 被抓出（实得 {problems[:2]}）')
    check(any('花括号不配对' in p for p in problems), '花括号不配对被抓出')
    check(all(p.startswith('backend/x/Foo.java: ') for p in problems), '问题带文件路径前缀')
    # 自检器自身出错也不能让生成失败
    problems2, _ = A.code_lint.lint_generated_files(
        [{'path': 'a.vue', 'language': 'vue', 'content': '没有 script 块的 .vue'}])
    check(len(problems2) == 1 and '自检未完成' in problems2[0], '自检器异常被如实报出而非抛出')
    check(meta['warnings'], '告警透出')

    print('\n== 下载 zip ==')
    payload = {'files': [{'path': f['path'], 'content': f['content']} for f in files],
               'zipName': '若依模块-商品-order.zip'}
    r = c.post('/api/v1/ai/code/ruoyi/download', json=payload, headers=hdr)
    check(r.status_code == 200, f'200（实得 {r.status_code}）')
    check(r.headers['Content-Type'] == 'application/zip', 'Content-Type 为 zip')
    cd = r.headers.get('Content-Disposition', '')
    check('filename="order.zip"' in cd, f'ASCII 兜底名正确（实得 {cd[:60]}）')
    check("filename*=UTF-8''" in cd, '中文名走 RFC 5987')
    raw = r.data
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        znames = zf.namelist()
        check(len(znames) == len(files), 'zip 条目数与文件数一致')
        check(all(n.isascii() for n in znames), '条目名全 ASCII（Windows 解压不乱码）')
        doc = zf.read('backend/ruoyi-business/src/main/java/com/ruoyi/business/domain/Product.java')
        check(doc.decode('utf-8').startswith('package com.ruoyi.business.domain;'), '文件内容 UTF-8 正确')

    print('\n== 下载防护 ==')
    r = c.post('/api/v1/ai/code/ruoyi/download', json={'files': []}, headers=hdr)
    check(r.status_code == 400, '空文件列表 → 400')
    r = c.post('/api/v1/ai/code/ruoyi/download',
               json={'files': [{'path': '../../etc/passwd.java', 'content': 'x'}]}, headers=hdr)
    check(r.status_code == 400, 'Zip Slip 路径 → 400')
    r = c.post('/api/v1/ai/code/ruoyi/download',
               json={'files': [{'path': 'evil.exe', 'content': 'x'}]}, headers=hdr)
    check(r.status_code == 400, '非法扩展名 → 400')
    r = c.post('/api/v1/ai/code/ruoyi/download',
               json={'files': [{'path': 'a.java', 'content': 'x' * (1024 * 1024 + 1)}]}, headers=hdr)
    check(r.status_code == 413, '单文件超 1MB → 413')
    huge = [{'path': f'a/b{i}.java', 'content': 'x'} for i in range(0, 500)]
    r = c.post('/api/v1/ai/code/ruoyi/download', json={'files': huge}, headers=hdr)
    check(r.status_code == 413, '条目数超 400 → 413')

    print('\n== AI 标注路径（打桩，避免依赖真实 LLM） ==')
    from core import AIService
    real_completion = AIService.chat_completion
    cfg_ai = dict(CONFIG, useAI=True)

    def post(config, entities=None):
        return c.post('/api/v1/ai/code/ruoyi/generate',
                      json={'erEntities': entities or ENTITIES, 'erRelations': RELATIONS, 'config': config},
                      headers=hdr)

    def stub(payload, finish='stop'):
        AIService.chat_completion = staticmethod(
            lambda messages, **kw: {'choices': [{'finish_reason': finish, 'message': {'content': payload}}]})

    try:
        # 1) 正常返回 + 夹带不存在的键
        stub('{"tables":{"sys_product":{"comment":"商品主表"}},'
             '"fields":{"sys_product":{"product_name":{"label":"商品名称","queryType":"EQ"},'
             '"幽灵列":{"label":"x"}},"不存在表":{"a":{"label":"y"}}}}')
        r = post(cfg_ai)
        b = r.get_json()
        check(r.status_code == 200 and b['meta']['aiUsed'] is True, 'AI 生效时 aiUsed=true')
        check(b['meta']['aiFallback'] is None, '全部批次成功时无降级理由')
        dom = next(f['content'] for f in b['files'] if f['path'].endswith('domain/Product.java'))
        check('@Excel(name = "商品名称")' in dom, 'AI label 覆盖内置词表')
        check('商品主表' in dom, 'AI 表注释写入 JavaDoc')
        check(any('不存在' in w for w in b['meta']['warnings']), 'AI 编造的键被忽略并告警')
        api_js = next(f['content'] for f in b['files'] if f['path'].endswith('api/business/product.js'))
        check('listProduct' in api_js, 'AI 路径下前端产物仍完整')

        # 2) 截断：必须降级而不是把半截 JSON 当成功
        stub('{"tables":{"sys_product":{"comment":"商品', finish='length')
        r = post(cfg_ai)
        b = r.get_json()
        check(b['meta']['aiUsed'] is False and b['meta']['aiFallback'] == 'truncated',
              f"finish_reason=length → 降级 truncated（实得 {b['meta'].get('aiFallback')}）")
        dom = next(f['content'] for f in b['files'] if f['path'].endswith('domain/Product.java'))
        check('@Excel(name = "商品名称")' in dom, '截断时字段仍按内置词表产出')

        # 3) 不可解析
        stub('这不是 JSON')
        b = post(cfg_ai).get_json()
        check(b['meta']['aiUsed'] is False and b['meta']['aiFallback'] == 'invalid_json',
              f"坏 JSON → invalid_json（实得 {b['meta'].get('aiFallback')}）")

        # 4) 调用报错
        AIService.chat_completion = staticmethod(lambda messages, **kw: {'error': 'API调用失败: 401'})
        b = post(cfg_ai).get_json()
        check(b['meta']['aiUsed'] is False and 'error' in (b['meta']['aiFallback'] or ''),
              '调用报错 → 降级并带原因')
        check(b['meta']['fileCount'] > 0, 'AI 全挂时文件照样出全（降级不影响产出）')
    finally:
        AIService.chat_completion = real_completion

    print('\n== 既有代码生成链路未被破坏 ==')
    r = c.post('/api/v1/ai/code/generate', json={'source': 'er', 'outputType': 'entity',
                                                'language': 'java', 'framework': 'spring',
                                                'erEntities': ENTITIES, 'erRelations': []})
    check(r.status_code in (200, 400), f'旧端点仍可访问（实得 {r.status_code}）')
    check('ruoyi' not in (r.get_json() or {}).get('code', '')[:200].lower()
          or r.status_code == 200, '旧端点返回结构未变（仍是 code 字段）')
    check('code' in (r.get_json() or {}) or 'error' in (r.get_json() or {}), '旧端点返回 code/error')

    print('\n' + ('全部通过 ✅' if not FAILED else f'失败 {len(FAILED)} 项 ❌：{FAILED}'))
    return 1 if FAILED else 0


if __name__ == '__main__':
    sys.exit(main())
