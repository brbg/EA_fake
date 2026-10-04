"""若依模块生成的纯函数自测（不依赖 pytest，直接 `py backend/tests/test_ruoyi_gen.py` 运行）。

覆盖：命名/类型推导、规则降级（无 AI）、复合主键、M:N 中间表、中文表名兜底、
审计列别名重命名、未知类型退化、XML 合法性、zip 打包与条目名 ASCII。
"""

import io
import os
import re
import sys
import zipfile
import xml.etree.ElementTree as ET

try:
    sys.stdout.reconfigure(encoding='utf-8')   # Windows 控制台默认 GBK，中文与 emoji 会炸
except Exception:   # noqa: BLE001
    pass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ruoyi_gen as G   # noqa: E402
import ruoyi_templates as T  # noqa: E402
# 检查器已搬到生产侧 backend/code_lint.py：本测试改为 import，
# 这样它锁的是生产实现，而不是自己的一份副本
from code_lint import java_lint, vue_lint  # noqa: E402

FAILED = []


def check(cond, label):
    if cond:
        print(f'  ok   {label}')
    else:
        print(f'  FAIL {label}')
        FAILED.append(label)


def fixture():
    """构造一个有代表性的 ER 模型：正常表 / 复合主键 / 中文表名 / 类型边界 / M:N。"""
    return [
        {
            'id': 1,
            'name': 'sys_user',
            'fields': [
                {'name': 'id', 'type': 'INT', 'isPrimary': True},
                {'name': 'user_name', 'type': 'VARCHAR(255)'},
                {'name': 'email', 'type': 'VARCHAR(100)'},
                {'name': 'status', 'type': 'VARCHAR(255)'},
                {'name': 'sex', 'type': 'VARCHAR(10)'},
                {'name': 'created_at', 'type': 'DATETIME'},   # 审计列别名 → 应重命名为 create_time
                {'name': 'remark', 'type': 'VARCHAR(255)'},
            ],
        },
        {
            'id': 2,
            'name': 'order_item',
            'fields': [
                {'name': 'order_id', 'type': 'BIGINT', 'isPrimary': True},
                {'name': 'product_id', 'type': 'BIGINT', 'isPrimary': True},
                {'name': 'quantity', 'type': 'INT'},
                {'name': 'price', 'type': 'DECIMAL(10,2)'},
            ],
        },
        {
            'id': 3,
            'name': 'farm_crop',
            'fields': [
                {'name': 'id', 'type': 'BIGINT', 'isPrimary': True},
                {'name': 'crop_name', 'type': 'VARCHAR(255)'},
                {'name': 'area', 'type': 'DECIMAL(10,2)'},
                {'name': 'tags', 'type': 'JSON'},
                {'name': 'memo', 'type': 'TEXT'},
                {'name': 'budget', 'type': 'MONEY'},          # 未知类型 → 应退化为 VARCHAR(255) 并告警
            ],
        },
        {
            'id': 4,
            'name': '用户表',                                  # 纯中文表名 → 应兜底为 t_4 并告警
            'fields': [
                {'name': 'id', 'type': 'INT', 'isPrimary': True},
                {'name': 'name', 'type': 'VARCHAR(255)'},
            ],
        },
    ], [
        {'id': 11, 'type': 'manyToMany', 'startEntity': 3, 'endEntity': 1},
        {'id': 12, 'type': 'oneToMany', 'startEntity': 1, 'endEntity': 2},
    ]


def main():
    entities, relations = fixture()
    cfg, err = G.normalize_config({
        'packageBase': 'com.ruoyi', 'moduleName': 'system', 'tablePrefix': 'sys_',
        'author': 'ruoyi', 'parentMenuId': 3, 'servletApi': 'jakarta',
        'frontendTs': True, 'dbType': 'mysql',
    })
    print('== 配置校验 ==')
    check(err is None, f'配置合法（err={err}）')
    bad, berr = G.normalize_config({'packageBase': 'Com.RuoYi'})
    check(berr is not None, '非法包名被拒（不做静默修正）')
    check(isinstance(bad, G.RuoYiConfig), '非法包名仍返回配置对象供前端回显')

    print('\n== 命名 / 类型 / 规则 ==')
    check(G.to_snake('UserOrder') == 'user_order', "to_snake('UserOrder') == 'user_order'")
    check(G.to_snake('用户表') == '', "to_snake('用户表') 为空（触发兜底）")
    check(G.to_pascal('sys_user') == 'SysUser', "to_pascal('sys_user') == 'SysUser'")
    check(G.to_camel('SysUser') == 'sysUser', "to_camel('SysUser') == 'sysUser'")
    check(G.strip_table_prefix('sys_user', 'sys_') == 'user', "去表前缀 'sys_user' → 'user'")
    check(G.parse_sql_type('VARCHAR(255)')[:2] == ('VARCHAR', 255), 'VARCHAR(255) 解析')
    check(G.parse_sql_type('DECIMAL(10,2)')[:3] == ('DECIMAL', 10, 2), 'DECIMAL(10,2) 解析')
    base, length, _, warns = G.parse_sql_type('MONEY')
    check(base == 'VARCHAR' and warns, "未知类型 'MONEY' → VARCHAR(255) + 告警")
    check(G.guess_field_label('user_name') == '用户名称', "label('user_name') == 用户名称")
    check(G.guess_field_label('create_time') == '创建时间', "label('create_time') == 创建时间")
    check(G.guess_field_label('is_deleted') == '删除标志', "label('is_deleted') == 删除标志")
    check(G.guess_field_label('weird_col_x') == 'weird_col_x', 'label 兜底用原列名（永不为空）')
    check(G.guess_dict_type('status') == 'sys_normal_disable', "dict('status') == sys_normal_disable")
    check(G.guess_dict_type('del_flag') == '', 'del_flag 不猜字典（避免 dict-tag 空白）')

    print('\n== 生成（无 AI） ==')
    result = G.generate_ruoyi_module(entities, relations, cfg, annotation=None)
    files = result['files']
    meta = result['meta']
    by_path = {f['path']: f for f in files}
    for f in files:
        print(f"  - {f['path']}  ({len(f['content'])} 字符)")

    check(len(meta['tables']) == 4, '4 张表')
    # 4 表×8 + 4 个 SQL + README + 模块 pom.xml + INTEGRATION.md
    check(len(files) == 4 * 8 + 4 + 3, f'文件数 = 4 表×8 + 4 SQL + README + pom + INTEGRATION（实得 {len(files)}）')
    check(meta['joinTables'] == ['farm_crop_sys_user'], f"M:N 中间表名（实得 {meta['joinTables']}）")

    print('\n== Maven 模块与集成说明 ==')
    pom = by_path['backend/ruoyi-system/pom.xml']['content']
    check('<artifactId>ruoyi</artifactId>' in pom and '<version>3.9.2</version>' in pom,
          'pom 的 parent 指向根工程、版本默认 3.9.2')
    check('<artifactId>ruoyi-system</artifactId>' in pom, 'pom 的 artifactId = ruoyi-模块名')
    dep_block = pom.split('<artifactId>ruoyi-common</artifactId>')[1].split('</dependency>')[0]
    check('<version>' not in dep_block, 'ruoyi-common 依赖不写 version（由根 pom 的 dependencyManagement 管）')
    try:
        ET.fromstring(pom)
        check(True, 'pom 可被 XML 解析')
    except Exception as e:   # noqa: BLE001
        check(False, f'pom 解析失败：{e}')

    integ = by_path['INTEGRATION.md']['content']
    for frag, label in (('<module>ruoyi-system</module>', '根 pom 的 modules 片段'),
                        ('<dependencyManagement>', '根 pom 的 dependencyManagement 片段'),
                        ('ruoyi-admin/pom.xml', 'ruoyi-admin 的依赖片段'),
                        ('missing', '漏了第二处的报错提示')):
        check(frag in integ, f'集成说明含：{label}')

    # 版本可配置：换一个版本号要能流到 pom 的 parent 里
    cfg2, err2 = G.normalize_config({**{
        'packageBase': 'com.ruoyi', 'moduleName': 'business', 'tablePrefix': 'sys_',
        'author': 'ruoyi', 'parentMenuId': 3, 'servletApi': 'jakarta',
        'frontendTs': True, 'dbType': 'mysql'}, 'ruoyiVersion': '3.8.9'})
    check(err2 is None, f'自定义版本号通过校验（err={err2}）')
    check('3.8.9' in T.render_module_pom({'tables': []}, cfg2), '自定义版本写进了 pom 的 parent')
    badv, bade = G.normalize_config({**{
        'packageBase': 'com.ruoyi', 'moduleName': 'business', 'parentMenuId': 3,
        'dbType': 'mysql'}, 'ruoyiVersion': 'v3.9.x'})
    check(bade is not None and '版本号' in bade, f'非法版本号被拒（实得 {bade}）')

    t1 = meta['tables'][0]
    check(t1['tableName'] == 'sys_user' and t1['className'] == 'User', 'sys_user → 类名 User')
    check(t1['businessName'] == 'user', 'sys_user → 业务名 user')
    check(t1['permissionPrefix'] == 'system:user', '权限前缀 system:user')
    check(any('t_4' == t['tableName'] for t in meta['tables']), '中文表名兜底为 t_4')
    check(any(t['compositePk'] for t in meta['tables']), '复合主键被识别')

    print('\n== 内容健全性 ==')
    joined = '\n'.join(f['content'] for f in files)
    # 只找 Python 的 None / 模板占位符泄漏；`undefined` 与 `${new Date().getTime()}` 是若依代码本就有的写法
    check(re.search(r'\bNone\b', joined) is None, "生成物里没有 Python 的 'None' 残留")
    placeholders = re.findall(r'\{(ClassName|className|moduleName|businessName|pk_field|pkColumn|functionName|permissionPrefix|tableName|column)\}', joined)
    check(not placeholders, f'没有未替换的模板占位符（实得 {set(placeholders)}）')
    check('null comment' not in joined, "没有 'null comment'（注释全部非空）")
    check("comment ''" not in joined, '没有空的列注释')

    dom = by_path['backend/ruoyi-system/src/main/java/com/ruoyi/system/domain/User.java']['content']
    check('extends BaseEntity' in dom, 'domain 继承 BaseEntity')
    check('private String userName;' in dom, '用户名字段驼峰化')
    check('@Excel(name = "用户名称")' in dom, '@Excel 中文名来自 label')
    check('@Excel(name = "状态", readConverterExp = "0=正常,1=停用")' in dom, '字典列带 readConverterExp')
    check('private Long id;' in dom and 'private Integer id' not in dom, '主键归一化为 Long')
    check('private String createdAt' not in dom, '审计列别名已重命名（无 createdAt）')
    check('private String createTime' not in dom, '审计列不在 domain 里重复声明')

    xml_txt = by_path['backend/ruoyi-system/src/main/resources/mapper/system/UserMapper.xml']['content']
    tmp = os.path.join(os.environ.get('TEMP', '/tmp'), 'ruoyi_UserMapper.xml')
    with io.open(tmp, 'w', encoding='utf-8') as fh:
        fh.write(xml_txt)
    try:
        ET.parse(tmp)
        check(True, 'Mapper.xml 可被 XML 解析器解析')
    except Exception as e:   # noqa: BLE001
        check(False, f'Mapper.xml 解析失败：{e}')
    finally:
        os.remove(tmp)
    for frag in ('<insert id="insertUser" parameterType="User" useGeneratedKeys="true" keyProperty="id">',
                 '<update id="updateUser"', '<delete id="deleteUserByIds"',
                 '<foreach item="id" collection="array"', 'like concat'):
        check(frag in xml_txt, f'XML 含 {frag[:38]}…')

    ctrl = by_path['backend/ruoyi-system/src/main/java/com/ruoyi/system/controller/UserController.java']['content']
    check("@PreAuthorize(\"@ss.hasPermi('system:user:list')\")" in ctrl, 'controller 权限串正确')
    check('import jakarta.servlet.http.HttpServletResponse;' in ctrl, '默认 servletApi=jakarta')
    check('@Validated @RequestBody User user' in ctrl, 'add/edit 带 @Validated')
    check('create table' not in ctrl, 'controller 里没混进 SQL')

    svc = by_path['backend/ruoyi-system/src/main/java/com/ruoyi/system/service/impl/UserServiceImpl.java']['content']
    check('user.setCreateTime(DateUtils.getNowDate());' in svc, 'insert 回填 createTime')
    check('import com.ruoyi.common.utils.DateUtils;' in svc, '按需 import DateUtils')

    mpr = by_path['backend/ruoyi-system/src/main/java/com/ruoyi/system/mapper/UserMapper.java']['content']
    check('public interface UserMapper ' in mpr, 'Mapper 是裸接口')
    check('extends BaseMapper' not in mpr, 'Mapper 不 extends BaseMapper（RuoYi-Vue-Plus 写法）')
    check('public int deleteUserByIds(Long[] ids);' in mpr, 'deleteUserByIds(Long[]) 签名')

    sql = by_path['sql/sys_user.sql']['content']
    check('create table sys_user (' in sql, 'SQL 含建表语句')
    check("comment = '用户表'" in sql or 'comment = ' in sql, 'SQL 表注释非空')
    check("insert into sys_menu" in sql and sql.count('insert into sys_menu') == 6, 'sys_menu 插入 6 行')
    check("'system/user/index'" in sql, '菜单 component 格式正确（无前导斜杠/无 .vue）')
    check(re.search(r'^  id\s+bigint\(20\)\s+not null auto_increment', sql, re.M) is not None,
          '主键列归一化为 bigint(20) 自增')
    check(sql.index('create_by') > sql.index('sex'), '审计列收到业务列之后')
    check(sql.rindex('remark') > sql.rindex('update_time'), 'remark 排在最后')

    farm_sql = by_path['sql/farm_crop.sql']['content']
    check('farm_crop_sys_user' in farm_sql, 'M:N 中间表 DDL 挂在 SQL 里')

    vue = by_path['frontend/src/views/system/user/index.vue']['content']
    check('<script setup name="User" lang="ts">' in vue, 'index.vue 的 name 属性正确')
    check('useDict("sys_normal_disable"' in vue or 'useDict(' in vue, '使用 useDict 加载字典')
    check('v-hasPermi="[\'system:user:add\']"' in vue, '按钮权限指令正确')
    check('icon="Plus"' in vue and 'fas fa-' not in vue, '图标是字符串（不是 FontAwesome class）')
    check('response.rows' in vue, '列表读 response.rows')
    check('parseTime(scope.row.createTime)' in vue, '时间列用 parseTime')
    check('dict-tag' in vue, '字典列用 dict-tag')
    api = by_path['frontend/src/api/system/user.ts']['content']
    check("url: '/system/user/list'" in api, 'api.ts 路径与 controller 一致')

    readme = by_path['README.md']['content']
    check('ruoyi-system/src/main/java' in readme, 'README 说明放置路径')
    check('## 生成告警' in readme, 'README 汇总告警')

    print('\n== Java 结构体检（本机无 JDK，用 import 完整性替代真编译） ==')
    java_files = [f for f in files if f['language'] == 'java']
    for f in java_files:
        problems = java_lint(f['content'])
        check(not problems, f"{f['name']} 结构完好" + (f"：{problems}" if problems else ''))

    print('\n== Vue 一致性 ==')
    vue_problems = vue_lint(vue)
    check(not vue_problems, 'index.vue 内部引用自洽' + (f'：{vue_problems}' if vue_problems else ''))

    print('\n== 告警 ==')
    for w in meta['warnings']:
        print(f'  ! {w}')
    check(any('MONEY' in w for w in meta['warnings']), '未知类型有告警')
    check(any('复合主键' in w for w in meta['warnings']), '复合主键有告警')
    check(any('t_4' in w for w in meta['warnings']), '中文表名有告警')
    check(any('created_at' in w and 'create_time' in w for w in meta['warnings']), '审计列重命名有告警')

    print('\n== zip ==')
    raw, zerr = G.build_zip(files)
    check(zerr is None and raw, f'打包成功（err={zerr}）')
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        names = zf.namelist()
        check(len(names) == len(files), f'条目数一致（{len(names)}）')
        check(all(n.isascii() for n in names), '所有条目名都是 ASCII')
        check(all('..' not in n and not n.startswith('/') for n in names), '无路径穿越')
        check(zf.read('README.md').decode('utf-8').startswith('# 若依'), 'UTF-8 内容可正确读回')
    check(G.safe_zip_entry('../../etc/passwd') is None, 'Zip Slip 路径被拒')
    check(G.safe_zip_entry('/abs/x.java') is None, '绝对路径被拒')
    check(G.safe_zip_entry('a/b.exe') is None, '非法扩展名被拒')
    check(G.safe_zip_entry('a/b/User.java') == 'a/b/User.java', '合法路径通过')

    print('\n== AI 标注合并 ==')
    ann = {
        'tables': {'sys_user': {'comment': '系统用户表'}},
        'fields': {'sys_user': {
            'user_name': {'label': '登录账号', 'required': True, 'queryType': 'EQ'},
            'status': {'label': '账号状态', 'dictType': 'sys_normal_disable'},
            '不存在的列': {'label': 'x'},
        }},
    }
    r2 = G.generate_ruoyi_module(entities, relations, cfg, annotation=ann)
    dom2 = {f['path']: f['content'] for f in r2['files']}
    d2 = dom2['backend/ruoyi-system/src/main/java/com/ruoyi/system/domain/User.java']
    check('@Excel(name = "登录账号")' in d2, 'AI label 覆盖生效')
    check('系统用户表' in d2, 'AI 表注释覆盖生效')
    check(any('不存在的表' in w or '不存在的列' in w or '不存在的' in w for w in r2['meta']['warnings']),
          'AI 编造的键被忽略并告警')
    check('@Excel(name = "邮箱")' in d2, 'AI 未覆盖的字段保留规则 label')
    svc2 = dom2['backend/ruoyi-system/src/main/java/com/ruoyi/system/service/IUserService.java']
    check('selectUserList' in svc2, 'service 接口完整')

    print('\n== 空模型 ==')
    empty = G.generate_ruoyi_module([], [], cfg)
    check(empty['meta']['fileCount'] == 0 and empty['files'] == [], '空模型不产出文件')
    check(bool(empty['meta']['warnings']), '空模型给出告警')

    print('\n' + ('全部通过 ✅' if not FAILED else f'失败 {len(FAILED)} 项 ❌：{FAILED}'))
    return 1 if FAILED else 0


if __name__ == '__main__':
    sys.exit(main())
