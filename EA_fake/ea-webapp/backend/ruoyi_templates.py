"""若依 RuoYi-Vue3 代码模板（纯字符串渲染，无 IO、无业务逻辑）。

模板逐字对齐官方 `yangzongzhuan/RuoYi-Vue` 的 `ruoyi-generator/src/main/resources/vm/*`
与 `yangzongzhuan/RuoYi-Vue3` 的真实页面。已核实的几个**易错点**（改动前务必先看）：

- Mapper 接口是**裸接口**（无 extends），6 个方法名都带类名前缀：
  select{X}ById / select{X}List / insert{X} / update{X} / delete{X}ById / delete{X}ByIds。
  （`extends BaseMapper` + `selectById/updateById/deleteBatchIds` 是 **RuoYi-Vue-Plus** 的写法，经典版用了编译不过）
- Mapper.xml **含完整 CRUD**（insert 用 <trim> 动态列、update 用 <trim prefix="SET">、
  delete{X}ByIds 用 <foreach collection="array">），不是「只写 select 交给 BaseMapper」。
- controller 的 export 用 `jakarta.servlet.http.HttpServletResponse`（若依 3.9.x / Spring Boot 3、4），
  3.8.x 是 `javax.servlet.http.HttpServletResponse`。
- 前端页面 `<script setup name="{ClassName}">` 的 name 必须有（tags-view/keep-alive 依赖）；
  依赖 unplugin-auto-import，ref/useDict/parseTime 都不 import；图标是字符串（icon="Plus"），
  不是 FontAwesome 的 class。

**版本事实（2026-10-04 从 gitee.com/y_project/RuoYi-Vue 实拉核对，不是猜的）**：
RuoYi-Vue `3.9.2`、`ruoyi.version=3.9.2`、`java.version=17`、`spring-boot.version=4.1.0`；
根 pom 有 `<packaging>pom</packaging>`，并在 `<dependencyManagement>` 里给各 ruoyi-* 模块管版本。

**真编译验证**：同日在 JDK 17 + Maven 3.9.16 上，把生成的模块按
`render_integration_readme` 的三处编辑接入官方工程，`mvn -DskipTests compile` **BUILD SUCCESS**
（10 个生成类全部编译，全项目 0 错误 0 警告）。改动模板后请重跑这条验证。

**集成需三处编辑**（`render_integration_readme` 产出可粘贴片段），第三处最容易漏：
根 pom 的 `<modules>`、根 pom 的 `<dependencyManagement>`（给新模块管版本）、
`ruoyi-admin/pom.xml` 的 `<dependencies>`。少了第二处会报
`'dependencies.dependency.version' for com.ruoyi:<module>:jar is missing`。
"""

# ---------------------------------------------------------------- 小工具

BACKEND_ROOT = 'backend/ruoyi-{module}'


def _attr_name(field):
    """Java bean 访问器名：第 2 个字符是大写时按原样（uName → getuName），否则首字母大写。"""
    if len(field) > 2 and field[1].isupper():
        return field
    return field[:1].upper() + field[1:]


def _getter(field):
    return f'get{_attr_name(field)}'


def _setter(field):
    return f'set{_attr_name(field)}'


def _comment(doc_lines, indent):
    """JavaDoc 块。"""
    pad = ' ' * indent
    out = [f'{pad}/**']
    for line in doc_lines:
        out.append(f'{pad} * {line}'.rstrip())
    out.append(f'{pad} */')
    return '\n'.join(out)


def _java_file(pkg, imports, body, doc=None):
    lines = [f'package {pkg};', '']
    if imports:
        lines += [f'import {i};' for i in imports]
        lines.append('')
    if doc:
        lines.append(doc)
    lines.append(body)
    return '\n'.join(lines).rstrip() + '\n'


def _business_columns(table):
    return [c for c in table['columns'] if not c['is_super']]


def _dict_types(table):
    seen = []
    for c in table['columns']:
        if c['dict_type'] and c['dict_type'] not in seen:
            seen.append(c['dict_type'])
    return seen


def _table_field(table):
    return table['business_name']


# ---------------------------------------------------------------- Java: domain

def render_domain(table, cfg):
    columns = table['columns']
    imports = []
    if any(c['java_type'] == 'Date' for c in columns):
        imports.append('java.util.Date')
    if any(c['java_type'] == 'BigDecimal' for c in columns):
        imports.append('java.math.BigDecimal')
    if any(c['java_type'] == 'Date' and c['base'] == 'DATE' for c in columns):
        imports.append('com.fasterxml.jackson.annotation.JsonFormat')
    imports += [
        'org.apache.commons.lang3.builder.ToStringBuilder',
        'org.apache.commons.lang3.builder.ToStringStyle',
        'com.ruoyi.common.annotation.Excel',
        'com.ruoyi.common.core.domain.BaseEntity',
    ]

    body = [f'public class {table["class_name"]} extends BaseEntity', '{']
    body.append('    private static final long serialVersionUID = 1L;')
    for c in columns:
        body.append('')
        body.append(f'    /** {c["comment"]} */')
        if c['list']:
            if c['dict_type']:
                body.append(f'    @Excel(name = "{c["comment"]}", readConverterExp = "{c["read_converter"]}")')
            elif c['java_type'] == 'Date':
                pattern = 'yyyy-MM-dd' if c['base'] == 'DATE' else 'yyyy-MM-dd HH:mm:ss'
                if c['base'] == 'DATE':
                    body.append('    @JsonFormat(pattern = "yyyy-MM-dd")')
                body.append(f'    @Excel(name = "{c["comment"]}", width = 30, dateFormat = "{pattern}")')
            else:
                body.append(f'    @Excel(name = "{c["comment"]}")')
        body.append(f'    private {c["java_type"]} {c["java_field"]};')

    for c in columns:
        body.append('')
        body.append(f'    public void {_setter(c["java_field"])}({c["java_type"]} {c["java_field"]}) ')
        body.append('    {')
        body.append(f'        this.{c["java_field"]} = {c["java_field"]};')
        body.append('    }')
        body.append('')
        body.append(f'    public {c["java_type"]} {_getter(c["java_field"])}() ')
        body.append('    {')
        body.append(f'        return {c["java_field"]};')
        body.append('    }')

    body.append('')
    body.append('    @Override')
    body.append('    public String toString() {')
    body.append('        return new ToStringBuilder(this, ToStringStyle.MULTI_LINE_STYLE)')
    for c in columns:
        body.append(f'            .append("{c["java_field"]}", {_getter(c["java_field"])}())')
    body.append('            .toString();')
    body.append('    }')
    body.append('}')

    doc = _comment([f'{table["comment"]}对象 {table["table_name"]}', '', f'@author {cfg.author}', f'@date {_today()}'], 0)
    return _java_file(table['package_name'] + '.domain', imports, '\n'.join(body), doc)


# ---------------------------------------------------------------- 主键辅助
# 单主键与复合主键（中间表常见）在这里统一出口，渲染函数不各判一次。
# **注意：若依官方只支持单主键**；复合主键是本平台自定义的自洽方案
# （多参数 + 不提供批量删除），与官方生成器的产出形态不同。

def _pk_list(table):
    """全部主键列。没有主键时返回空列表。"""
    return table.get('pk_fields') or ([table['pk']] if table.get('pk') else [])


def _is_composite(table):
    return len(_pk_list(table)) > 1


def _pk_args(table):
    """Java 形参：'Long id' / 'Long orderId, Long productId'。"""
    pks = _pk_list(table)
    if not pks:
        return 'Long id'
    return ', '.join(f"{c['java_type']} {c['java_field']}" for c in pks)


def _pk_params(table):
    """Java 实参：'id' / 'orderId, productId'。"""
    pks = _pk_list(table)
    if not pks:
        return 'id'
    return ', '.join(c['java_field'] for c in pks)


def _pk_args_annotated(table):
    """Mapper 接口的形参：多参数时逐个加 @Param。

    不加 @Param 时 MyBatis 只认 `param1/param2`/`arg0/arg1`，想用 `#{orderId}` 这种
    真参数名得同时满足「编译带 -parameters」且「MyBatis useActualParamName=true」——
    两个隐式条件任一不成立，XML 里的 `#{orderId}` 就会在**运行时**报
    「Parameter 'orderId' not found」。显式注解把这个坑堵死。
    """
    pks = _pk_list(table)
    if len(pks) <= 1:
        return _pk_args(table)
    return ', '.join(f'@Param("{c["java_field"]}") {c["java_type"]} {c["java_field"]}' for c in pks)


def _pk_suffix(table):
    """方法名里的主键后缀：单主键沿用 pk_cap（Id）；复合用 OrderIdAndProductId。"""
    pks = _pk_list(table)
    if len(pks) <= 1:
        return table['pk_cap']
    return 'And'.join(c['java_field'][:1].upper() + c['java_field'][1:] for c in pks)


def _pk_where(table):
    """Mapper.xml 的 where：'id = #{id}' / 'order_id = #{orderId} and product_id = #{productId}'。"""
    pks = _pk_list(table)
    if not pks:
        return 'id = #{id}'
    return ' and '.join(f"{c['column_name']} = #{{{c['java_field']}}}" for c in pks)


def _pk_path_vars(table):
    """Controller 形参：'@PathVariable("id") Long id'；复合主键逐个列举。"""
    pks = _pk_list(table)
    if not pks:
        return '@PathVariable("id") Long id'
    return ', '.join(f'@PathVariable("{c["java_field"]}") {c["java_type"]} {c["java_field"]}' for c in pks)


def _pk_path(table):
    """REST 路径变量：'{id}' / '{orderId}/{productId}'。"""
    pks = _pk_list(table)
    if not pks:
        return '{id}'
    return '/'.join('{' + c['java_field'] + '}' for c in pks)


def _pk_doc(table):
    """javadoc 里逐参数说明。"""
    pks = _pk_list(table)
    return [f'     * @param {c["java_field"]} 主键' for c in pks] or ['     * @param id 主键']


# ---------------------------------------------------------------- Java: mapper

def render_mapper_java(table, cfg):
    cls = table['class_name']
    var = table['business_name']
    pk_args = _pk_args_annotated(table)
    pk_suffix = _pk_suffix(table)

    body = [
        f'public interface {cls}Mapper ',
        '{',
        '    /**',
        f'     * 查询{table["comment"]}',
        '     * ',
    ] + _pk_doc(table) + [
        f'     * @return {table["comment"]}',
        '     */',
        f'    public {cls} select{cls}By{pk_suffix}({pk_args});',
        '',
        '    /**',
        f'     * 查询{table["comment"]}列表',
        '     * ',
        f'     * @param {var} {table["comment"]}',
        f'     * @return {table["comment"]}集合',
        '     */',
        f'    public List<{cls}> select{cls}List({cls} {var});',
        '',
        '    /**',
        f'     * 新增{table["comment"]}',
        '     * ',
        f'     * @param {var} {table["comment"]}',
        '     * @return 结果',
        '     */',
        f'    public int insert{cls}({cls} {var});',
        '',
        '    /**',
        f'     * 修改{table["comment"]}',
        '     * ',
        f'     * @param {var} {table["comment"]}',
        '     * @return 结果',
        '     */',
        f'    public int update{cls}({cls} {var});',
        '',
        '    /**',
        f'     * 删除{table["comment"]}',
        '     * ',
    ] + _pk_doc(table) + [
        '     * @return 结果',
        '     */',
        f'    public int delete{cls}By{pk_suffix}({pk_args});',
    ]
    # 批量删除：复合主键下「一维主键数组」表达不了成对的键，语义不成立，故不生成
    if not _is_composite(table):
        pk_type = table['pk']['java_type'] if table['pk'] else 'Long'
        body += [
            '',
            '    /**',
            f'     * 批量删除{table["comment"]}',
            '     * ',
            f'     * @param {table["pk_field"]}s 需要删除的数据主键集合',
            '     * @return 结果',
            '     */',
            f'    public int delete{cls}By{pk_suffix}s({pk_type}[] {table["pk_field"]}s);',
        ]
    body.append('}')
    imports = ['java.util.List', f'{table["package_name"]}.domain.{cls}']
    if _is_composite(table):
        imports.append('org.apache.ibatis.annotations.Param')   # 多参数必须显式命名
    doc = _comment([f'{table["comment"]}Mapper接口', '', f'@author {cfg.author}', f'@date {_today()}'], 0)
    return _java_file(table['package_name'] + '.mapper', imports, '\n'.join(body), doc)


# ---------------------------------------------------------------- Java: service

def _service_methods(table, suffix=';'):
    cls = table['class_name']
    var = table['business_name']
    pk_args = _pk_args(table)
    pk_suffix = _pk_suffix(table)
    methods = [
        f'    public {cls} select{cls}By{pk_suffix}({pk_args}){suffix}',
        '',
        f'    public List<{cls}> select{cls}List({cls} {var}){suffix}',
        '',
        f'    public int insert{cls}({cls} {var}){suffix}',
        '',
        f'    public int update{cls}({cls} {var}){suffix}',
        '',
        f'    public int delete{cls}By{pk_suffix}({pk_args}){suffix}',
    ]
    if not _is_composite(table):
        pk_type = table['pk']['java_type'] if table['pk'] else 'Long'
        methods += ['', f'    public int delete{cls}By{pk_suffix}s({pk_type}[] {table["pk_field"]}s){suffix}']
    return methods


def render_service_interface(table, cfg):
    cls = table['class_name']
    body = [f'public interface I{cls}Service ', '{'] + _service_methods(table) + ['}']
    imports = ['java.util.List', f'{table["package_name"]}.domain.{cls}']
    doc = _comment([f'{table["comment"]}Service接口', '', f'@author {cfg.author}', f'@date {_today()}'], 0)
    return _java_file(table['package_name'] + '.service', imports, '\n'.join(body), doc)


def render_service_impl(table, cfg):
    cls = table['class_name']
    var = table['business_name']
    pk_type = table['pk']['java_type'] if table['pk'] else 'Long'
    pk_field = table['pk_field']
    pk_args = _pk_args(table)
    pk_params = _pk_params(table)
    pk_suffix = _pk_suffix(table)

    body = [
        '@Service',
        f'public class {cls}ServiceImpl implements I{cls}Service ',
        '{',
        '    @Autowired',
        f'    private {cls}Mapper {var}Mapper;',
        '',
        '    /**',
        f'     * 查询{table["comment"]}',
        '     * ',
    ] + _pk_doc(table) + [
        f'     * @return {table["comment"]}',
        '     */',
        '    @Override',
        f'    public {cls} select{cls}By{pk_suffix}({pk_args})',
        '    {',
        f'        return {var}Mapper.select{cls}By{pk_suffix}({pk_params});',
        '    }',
        '',
        '    /**',
        f'     * 查询{table["comment"]}列表',
        '     * ',
        f'     * @param {var} {table["comment"]}',
        f'     * @return {table["comment"]}',
        '     */',
        '    @Override',
        f'    public List<{cls}> select{cls}List({cls} {var})',
        '    {',
        f'        return {var}Mapper.select{cls}List({var});',
        '    }',
        '',
        '    /**',
        f'     * 新增{table["comment"]}',
        '     * ',
        f'     * @param {var} {table["comment"]}',
        '     * @return 结果',
        '     */',
        '    @Override',
        f'    public int insert{cls}({cls} {var})',
        '    {',
    ]
    if table['has_create_time']:
        body.append(f'        {var}.setCreateTime(DateUtils.getNowDate());')
    body += [
        f'        return {var}Mapper.insert{cls}({var});',
        '    }',
        '',
        '    /**',
        f'     * 修改{table["comment"]}',
        '     * ',
        f'     * @param {var} {table["comment"]}',
        '     * @return 结果',
        '     */',
        '    @Override',
        f'    public int update{cls}({cls} {var})',
        '    {',
    ]
    if table['has_update_time']:
        body.append(f'        {var}.setUpdateTime(DateUtils.getNowDate());')
    body += [
        f'        return {var}Mapper.update{cls}({var});',
        '    }',
    ]
    # 批量删除只对单主键成立（复合主键要传成对的键，一维数组表达不了）
    if not _is_composite(table):
        body += [
            '',
            '    /**',
            f'     * 批量删除{table["comment"]}',
            '     * ',
            f'     * @param {pk_field}s 需要删除的{table["comment"]}主键',
            '     * @return 结果',
            '     */',
            '    @Override',
            f'    public int delete{cls}By{pk_suffix}s({pk_type}[] {pk_field}s)',
            '    {',
            f'        return {var}Mapper.delete{cls}By{pk_suffix}s({pk_field}s);',
            '    }',
        ]
    body += [
        '',
        '    /**',
        f'     * 删除{table["comment"]}信息',
        '     * ',
    ] + _pk_doc(table) + [
        '     * @return 结果',
        '     */',
        '    @Override',
        f'    public int delete{cls}By{pk_suffix}({pk_args})',
        '    {',
        f'        return {var}Mapper.delete{cls}By{pk_suffix}({pk_params});',
        '    }',
        '}',
    ]

    imports = ['java.util.List', 'org.springframework.beans.factory.annotation.Autowired', 'org.springframework.stereotype.Service']
    if table['has_create_time'] or table['has_update_time']:
        imports.append('com.ruoyi.common.utils.DateUtils')
    imports += [
        f'{table["package_name"]}.domain.{cls}',
        f'{table["package_name"]}.mapper.{cls}Mapper',
        f'{table["package_name"]}.service.I{cls}Service',
    ]
    doc = _comment([f'{table["comment"]}Service业务层处理', '', f'@author {cfg.author}', f'@date {_today()}'], 0)
    return _java_file(table['package_name'] + '.service.impl', imports, '\n'.join(body), doc)


# ---------------------------------------------------------------- Java: controller

def render_controller(table, cfg):
    cls = table['class_name']
    var = table['business_name']
    pk_type = table['pk']['java_type'] if table['pk'] else 'Long'
    pk_field = table['pk_field']
    pk_suffix = _pk_suffix(table)
    pk_params = _pk_params(table)
    pk_path = _pk_path(table)
    pk_path_ann = _pk_path_vars(table)
    perm = table['permission_prefix']
    func = table['comment']
    servlet_pkg = 'jakarta' if cfg.servlet_api == 'jakarta' else 'javax'

    body = [
        '@RestController',
        f'@RequestMapping("/{table["module_name"]}/{var}")',
        f'public class {cls}Controller extends BaseController',
        '{',
        '    @Autowired',
        f'    private I{cls}Service {var}Service;',
        '',
        '    /**',
        f'     * 查询{func}列表',
        '     */',
        f'    @PreAuthorize("@ss.hasPermi(\'{perm}:list\')")',
        '    @GetMapping("/list")',
        f'    public TableDataInfo list({cls} {var})',
        '    {',
        '        startPage();',
        f'        List<{cls}> list = {var}Service.select{cls}List({var});',
        '        return getDataTable(list);',
        '    }',
        '',
        '    /**',
        f'     * 导出{func}列表',
        '     */',
        f'    @PreAuthorize("@ss.hasPermi(\'{perm}:export\')")',
        f'    @Log(title = "{func}", businessType = BusinessType.EXPORT)',
        '    @PostMapping("/export")',
        f'    public void export(HttpServletResponse response, {cls} {var})',
        '    {',
        f'        List<{cls}> list = {var}Service.select{cls}List({var});',
        f'        ExcelUtil<{cls}> util = new ExcelUtil<{cls}>({cls}.class);',
        f'        util.exportExcel(response, list, "{func}数据");',
        '    }',
        '',
        '    /**',
        f'     * 获取{func}详细信息',
        '     */',
        f'    @PreAuthorize("@ss.hasPermi(\'{perm}:query\')")',
        f'    @GetMapping(value = "/{pk_path}")',
        f'    public AjaxResult getInfo({pk_path_ann})',
        '    {',
        f'        return success({var}Service.select{cls}By{pk_suffix}({pk_params}));',
        '    }',
        '',
        '    /**',
        f'     * 新增{func}',
        '     */',
        f'    @PreAuthorize("@ss.hasPermi(\'{perm}:add\')")',
        f'    @Log(title = "{func}", businessType = BusinessType.INSERT)',
        '    @PostMapping',
        f'    public AjaxResult add(@Validated @RequestBody {cls} {var})',
        '    {',
        f'        return toAjax({var}Service.insert{cls}({var}));',
        '    }',
        '',
        '    /**',
        f'     * 修改{func}',
        '     */',
        f'    @PreAuthorize("@ss.hasPermi(\'{perm}:edit\')")',
        f'    @Log(title = "{func}", businessType = BusinessType.UPDATE)',
        '    @PutMapping',
        f'    public AjaxResult edit(@Validated @RequestBody {cls} {var})',
        '    {',
        f'        return toAjax({var}Service.update{cls}({var}));',
        '    }',
        '',
        '    /**',
        f'     * 删除{func}',
        '     */',
        f'    @PreAuthorize("@ss.hasPermi(\'{perm}:remove\')")',
        f'    @Log(title = "{func}", businessType = BusinessType.DELETE)',
    ]
    if _is_composite(table):
        # 复合主键：没有「主键数组」这种形态，删除走组合键
        body += [
            f'    @DeleteMapping("/{pk_path}")',
            f'    public AjaxResult remove({pk_path_ann})',
            '    {',
            f'        return toAjax({var}Service.delete{cls}By{pk_suffix}({pk_params}));',
            '    }',
        ]
    else:
        body += [
            f'    @DeleteMapping("/{{{pk_field}s}}")',
            f'    public AjaxResult remove(@PathVariable {pk_type}[] {pk_field}s)',
            '    {',
            f'        return toAjax({var}Service.delete{cls}By{pk_suffix}s({pk_field}s));',
            '    }',
        ]
    body.append('}')

    imports = ['java.util.List', f'{servlet_pkg}.servlet.http.HttpServletResponse']
    imports += [
        'org.springframework.security.access.prepost.PreAuthorize',
        'org.springframework.beans.factory.annotation.Autowired',
        'org.springframework.validation.annotation.Validated',
        'org.springframework.web.bind.annotation.DeleteMapping',
        'org.springframework.web.bind.annotation.GetMapping',
        'org.springframework.web.bind.annotation.PathVariable',
        'org.springframework.web.bind.annotation.PostMapping',
        'org.springframework.web.bind.annotation.PutMapping',
        'org.springframework.web.bind.annotation.RequestBody',
        'org.springframework.web.bind.annotation.RequestMapping',
        'org.springframework.web.bind.annotation.RestController',
        'com.ruoyi.common.annotation.Log',
        'com.ruoyi.common.core.controller.BaseController',
        'com.ruoyi.common.core.domain.AjaxResult',
        'com.ruoyi.common.core.page.TableDataInfo',
        'com.ruoyi.common.enums.BusinessType',
        'com.ruoyi.common.utils.poi.ExcelUtil',
        f'{table["package_name"]}.domain.{cls}',
        f'{table["package_name"]}.service.I{cls}Service',
    ]
    doc = _comment([f'{func}Controller', '', f'@author {cfg.author}', f'@date {_today()}'], 0)
    return _java_file(table['package_name'] + '.controller', imports, '\n'.join(body), doc)


# ---------------------------------------------------------------- MyBatis XML

def render_mapper_xml(table, cfg):
    cls = table['class_name']
    var = table['business_name']
    pk_field = table['pk_field']
    pk_suffix = _pk_suffix(table)
    pk_where = _pk_where(table)
    # 复合主键走多参数 + @Param，MyBatis 自己推断参数，写 parameterType 反而错
    pk_ptype = '' if _is_composite(table) else f' parameterType="{table["pk"]["java_type"] if table["pk"] else "Long"}"'
    columns = table['columns']
    col_names = ', '.join(c['column_name'] for c in columns)
    pk_col = table['pk']['column_name'] if table['pk'] else 'id'
    increment = bool(table['pk'] and table['pk']['increment'])

    # 动态 where：一份按 query_type 分派（对齐官方 mapper.xml.vm）
    wheres = []
    for c in columns:
        if not c['query']:
            continue
        f, col, jt = c['java_field'], c['column_name'], c['java_type']
        str_extra = f' and {f}.trim() != \'\'' if jt == 'String' else ''
        qt = c['query_type']
        if qt == 'LIKE':
            cond = f"and {col} like concat('%', #{{{f}}}, '%')"
        elif qt == 'BETWEEN':
            attr = _attr_name(f)
            cond = (f'and {col} between #{{params.begin{attr}}} and #{{params.end{attr}}}')
            wheres.append(
                f'            <if test="params.begin{attr} != null and params.begin{attr} != \'\' '
                f'and params.end{attr} != null and params.end{attr} != \'\'"> {cond}</if>'
            )
            continue
        elif qt == 'EQ':
            cond = f'and {col} = #{{{f}}}'
        elif qt == 'NE':
            cond = f'and {col} != #{{{f}}}'
        elif qt in ('GT', 'GTE', 'LT', 'LTE'):
            op = {'GT': '&gt;', 'GTE': '&gt;=', 'LT': '&lt;', 'LTE': '&lt;='}[qt]
            cond = f'and {col} {op} #{{{f}}}'
        else:
            cond = f'and {col} = #{{{f}}}'
        wheres.append(f'            <if test="{f} != null{str_extra}"> {cond}</if>')

    insert_cols, insert_vals = [], []
    for c in columns:
        if c['is_pk'] and increment:
            continue
        extra = f" and {c['java_field']} != ''" if c['java_type'] == 'String' and c['required'] else ''
        insert_cols.append(f'            <if test="{c["java_field"]} != null{extra}">{c["column_name"]},</if>')
        insert_vals.append(f'            <if test="{c["java_field"]} != null{extra}">#{{{c["java_field"]}}},</if>')

    update_sets = []
    for c in columns:
        if c['is_pk']:
            continue
        extra = f" and {c['java_field']} != ''" if c['java_type'] == 'String' and c['required'] else ''
        update_sets.append(f'            <if test="{c["java_field"]} != null{extra}">{c["column_name"]} = #{{{c["java_field"]}}},</if>')

    insert_attrs = f' parameterType="{cls}"'
    if increment:
        insert_attrs += f' useGeneratedKeys="true" keyProperty="{pk_field}"'

    lines = [
        '<?xml version="1.0" encoding="UTF-8" ?>',
        '<!DOCTYPE mapper',
        'PUBLIC "-//mybatis.org//DTD Mapper 3.0//EN"',
        '"http://mybatis.org/dtd/mybatis-3-mapper.dtd">',
        f'<mapper namespace="{table["package_name"]}.mapper.{cls}Mapper">',
        '    ',
        f'    <resultMap type="{cls}" id="{cls}Result">',
    ]
    for c in columns:
        lines.append(f'        <result property="{c["java_field"]}"    column="{c["column_name"]}"    />')
    lines += [
        '    </resultMap>',
        '        ',
        f'    <sql id="select{cls}Vo">',
        f'        select {col_names} from {table["table_name"]}',
        '    </sql>',
        '        ',
        f'    <select id="select{cls}List" parameterType="{cls}" resultMap="{cls}Result">',
        f'        <include refid="select{cls}Vo"/>',
        '        <where>  ',
    ]
    lines += wheres
    lines += [
        '        </where>',
        '    </select>',
        '    ',
        f'    <select id="select{cls}By{pk_suffix}"{pk_ptype} resultMap="{cls}Result">',
        f'        <include refid="select{cls}Vo"/>',
        f'        where {pk_where}',
        '    </select>',
        '    ',
        f'    <insert id="insert{cls}"{insert_attrs}>',
        f'        insert into {table["table_name"]}',
        '        <trim prefix="(" suffix=")" suffixOverrides=",">',
    ]
    lines += insert_cols
    lines += [
        '         </trim>',
        '        <trim prefix="values (" suffix=")" suffixOverrides=",">',
    ]
    lines += insert_vals
    lines += [
        '         </trim>',
        '    </insert>',
        '',
        f'    <update id="update{cls}" parameterType="{cls}">',
        f'        update {table["table_name"]}',
        '        <trim prefix="SET" suffixOverrides=",">',
    ]
    lines += update_sets
    lines += [
        '        </trim>',
        f'        where {pk_where}',
        '    </update>',
        '',
        f'    <delete id="delete{cls}By{pk_suffix}"{pk_ptype}>',
        f'        delete from {table["table_name"]} where {pk_where}',
        '    </delete>',
    ]
    # 批量删除只对单主键成立（复合主键要传成对的键，一维数组表达不了）
    if not _is_composite(table):
        lines += [
            '',
            f'    <delete id="delete{cls}By{pk_suffix}s" parameterType="String">',
            f'        delete from {table["table_name"]} where {pk_col} in ',
            f'        <foreach item="{pk_field}" collection="array" open="(" separator="," close=")">',
            f'            #{{{pk_field}}}',
            '        </foreach>',
            '    </delete>',
        ]
    lines += [
        '    ',
        '</mapper>',
    ]
    return '\n'.join(lines).rstrip() + '\n'


# ---------------------------------------------------------------- SQL

def render_table_sql(table, cfg, join_tables=None):
    columns = table['columns']
    width = max([len(c['column_name']) for c in columns] + [12]) + 2
    lines = [
        '-- ----------------------------',
        f'-- {table["comment"]}',
        '-- ----------------------------',
        f'drop table if exists {table["table_name"]};',
        f'create table {table["table_name"]} (',
    ]
    for c in columns:
        name = c['column_name'].ljust(width)
        typ = c['sql_type'].ljust(14)
        # 主键 / 必填 加 not null；审计列给默认值；TEXT/JSON 在 MySQL 下不给 default
        if c['is_pk']:
            tail = 'not null auto_increment' if c['increment'] else 'not null'
        elif c['required']:
            tail = 'not null'
        elif c['is_super'] and c['column_name'] in ('create_by', 'update_by'):
            tail = "default ''"
        elif c['base'] in ('TEXT', 'LONGTEXT', 'MEDIUMTEXT', 'TINYTEXT', 'JSON', 'BLOB', 'LONGBLOB'):
            tail = ''
        else:
            tail = 'default null'
        pad = (' ' * max(1, 28 - len(tail)))
        comment = f"comment '{c['comment']}'"
        lines.append(f'  {name}{typ}{tail}{pad}{comment},')
    pk_col = table['pk']['column_name'] if table['pk'] else 'id'
    pks = table.get('pk_columns') or [pk_col]
    lines.append(f'  primary key ({", ".join(pks)})')
    lines.append(f') engine=innodb auto_increment=1 comment = \'{table["comment"]}\';')

    for jt in join_tables or []:
        w = max(len(jt['left_column']), len(jt['right_column'])) + 2
        lines += [
            '',
            '-- ----------------------------',
            f'-- {jt["comment"]}',
            '-- ----------------------------',
            f'drop table if exists {jt["table_name"]};',
            f'create table {jt["table_name"]} (',
            f'  {jt["left_column"].ljust(w)}bigint(20)    not null  comment \'关联主键\',',
            f'  {jt["right_column"].ljust(w)}bigint(20)    not null  comment \'关联主键\',',
            f'  primary key ({jt["left_column"]}, {jt["right_column"]})',
            f') engine=innodb comment = \'{jt["comment"]}\';',
        ]

    parent = cfg.parent_menu_id
    func = table['comment']
    perm = table['permission_prefix']
    biz = table['business_name']
    mod = table['module_name']
    menu_cols = ('menu_name, parent_id, order_num, path, component, is_frame, is_cache, '
                 'menu_type, visible, status, perms, icon, create_by, create_time, update_by, update_time, remark')

    def menu_row(name, parent_expr, order_num, path, component, menu_type, perms, remark):
        return (f"insert into sys_menu ({menu_cols})\n"
                f"values('{name}', {parent_expr}, '{order_num}', '{path}', '{component}', 1, 0, "
                f"'{menu_type}', '0', '0', '{perms}', '#', 'admin', sysdate(), '', null, '{remark}');")

    lines += [
        '',
        '-- ----------------------------',
        '-- 菜单 SQL',
        '-- ----------------------------',
        menu_row(func, f"'{parent}'", 1, biz, f'{mod}/{biz}/index', 'C', f'{perm}:list', f'{func}菜单'),
        '',
        '-- 按钮父菜单ID',
        'SELECT @parentId := LAST_INSERT_ID();',
        '',
        '-- 按钮 SQL',
        menu_row(f'{func}查询', '@parentId', 1, '#', '', 'F', f'{perm}:query', ''),
        menu_row(f'{func}新增', '@parentId', 2, '#', '', 'F', f'{perm}:add', ''),
        menu_row(f'{func}修改', '@parentId', 3, '#', '', 'F', f'{perm}:edit', ''),
        menu_row(f'{func}删除', '@parentId', 4, '#', '', 'F', f'{perm}:remove', ''),
        menu_row(f'{func}导出', '@parentId', 5, '#', '', 'F', f'{perm}:export', ''),
    ]
    return '\n'.join(lines) + '\n'


# ---------------------------------------------------------------- 前端 api

def render_api(table, cfg):
    cls = table['class_name']
    var = table['business_name']
    url = f'/{table["module_name"]}/{var}'
    pk_field = table['pk_field']
    ts = cfg.frontend_ts
    # 复合主键：get/del 收多个参数，URL 拼成 a/b 两段（与 Controller 的 /{a}/{b} 对应）
    _jstype = ': number | string' if ts else ''
    if _is_composite(table):
        _pks = [c['java_field'] for c in _pk_list(table)]
        pk_sig = ', '.join(f'{f}{_jstype}' for f in _pks)
        pk_url = f"'{url}/' + " + " + '/' + ".join(_pks)
    else:
        pk_sig = f'{pk_field}{_jstype}'
        pk_url = f"'{url}/' + {pk_field}"
    q = ': any' if ts else ''
    head = "import request from '@/utils/request'\n\n" if ts else "import request from '@/utils/request'\n\n"
    body = [
        f'// 查询{cls}列表',
        f'export function list{cls}(query{q}) {{',
        '  return request({',
        f"    url: '{url}/list',",
        "    method: 'get',",
        '    params: query',
        '  })',
        '}',
        '',
        f'// 查询{cls}详细',
        f'export function get{cls}({pk_sig}) {{',
        '  return request({',
        f"    url: {pk_url},",
        "    method: 'get'",
        '  })',
        '}',
        '',
        f'// 新增{cls}',
        f'export function add{cls}(data{q}) {{',
        '  return request({',
        f"    url: '{url}',",
        "    method: 'post',",
        '    data: data',
        '  })',
        '}',
        '',
        f'// 修改{cls}',
        f'export function update{cls}(data{q}) {{',
        '  return request({',
        f"    url: '{url}',",
        "    method: 'put',",
        '    data: data',
        '  })',
        '}',
        '',
        f'// 删除{cls}',
        f'export function del{cls}({pk_sig}) {{',
        '  return request({',
        f"    url: {pk_url},",
        "    method: 'delete'",
        '  })',
        '}',
    ]
    return head + '\n'.join(body) + '\n'


# ---------------------------------------------------------------- 前端页面

def _query_form_item(c):
    """查询表单控件。"""
    f, label = c['java_field'], c['comment']
    if c['dict_type']:
        return [
            f'      <el-form-item label="{label}" prop="{f}">',
            f'        <el-select v-model="queryParams.{f}" placeholder="请选择{label}" clearable style="width: 200px">',
            f'          <el-option',
            f'            v-for="dict in {c["dict_type"]}"',
            '            :key="dict.value"',
            '            :label="dict.label"',
            '            :value="dict.value"',
            '          />',
            '        </el-select>',
            '      </el-form-item>',
        ]
    if c['query_type'] == 'BETWEEN':
        return [
            f'      <el-form-item label="{label}">',
            f'        <el-date-picker',
            f'          v-model="daterange{_attr_name(f)}"',
            '          style="width: 240px"',
            '          value-format="YYYY-MM-DD"',
            '          type="daterange"',
            '          range-separator="-"',
            '          start-placeholder="开始日期"',
            '          end-placeholder="结束日期"',
            '        ></el-date-picker>',
            '      </el-form-item>',
        ]
    return [
        f'      <el-form-item label="{label}" prop="{f}">',
        f'        <el-input',
        f'          v-model="queryParams.{f}"',
        f'          placeholder="请输入{label}"',
        '          clearable',
        '          style="width: 200px"',
        '          @keyup.enter="handleQuery"',
        '        />',
        '      </el-form-item>',
    ]


def _table_column(c):
    f, label = c['java_field'], c['comment']
    if c['dict_type']:
        if c['html_type'] == 'checkbox':
            return [
                f'      <el-table-column label="{label}" align="center" prop="{f}">',
                '        <template #default="scope">',
                f'          <dict-tag :options="{c["dict_type"]}" :value="scope.row.{f} ? scope.row.{f}.split(\',\') : []" />',
                '        </template>',
                '      </el-table-column>',
            ]
        return [
            f'      <el-table-column label="{label}" align="center" prop="{f}">',
            '        <template #default="scope">',
            f'          <dict-tag :options="{c["dict_type"]}" :value="scope.row.{f}" />',
            '        </template>',
            '      </el-table-column>',
        ]
    if c['java_type'] == 'Date':
        return [
            f'      <el-table-column label="{label}" align="center" prop="{f}" width="180">',
            '        <template #default="scope">',
            f'          <span>{{{{ parseTime(scope.row.{f}) }}}}</span>',
            '        </template>',
            '      </el-table-column>',
        ]
    return [f'      <el-table-column label="{label}" align="center" prop="{f}" />']


def _form_item(c):
    f, label = c['java_field'], c['comment']
    if c['html_type'] == 'radio' and c['dict_type']:
        return [
            f'        <el-form-item label="{label}" prop="{f}">',
            f'          <el-radio-group v-model="form.{f}">',
            f'            <el-radio v-for="dict in {c["dict_type"]}" :key="dict.value" :value="dict.value">{{{{ dict.label }}}}</el-radio>',
            '          </el-radio-group>',
            '        </el-form-item>',
        ]
    if c['html_type'] == 'select' and c['dict_type']:
        return [
            f'        <el-form-item label="{label}" prop="{f}">',
            f'          <el-select v-model="form.{f}" placeholder="请选择{label}">',
            f'            <el-option',
            f'              v-for="dict in {c["dict_type"]}"',
            '              :key="dict.value"',
            '              :label="dict.label"',
            '              :value="dict.value"',
            '            ></el-option>',
            '          </el-select>',
            '        </el-form-item>',
        ]
    if c['html_type'] == 'datetime':
        return [
            f'        <el-form-item label="{label}" prop="{f}">',
            f'          <el-date-picker clearable',
            f'            v-model="form.{f}"',
            f'            type="date"',
            f'            value-format="YYYY-MM-DD"',
            f'            placeholder="请选择{label}">',
            '          </el-date-picker>',
            '        </el-form-item>',
        ]
    if c['html_type'] == 'textarea':
        return [
            f'        <el-form-item label="{label}" prop="{f}">',
            f'          <el-input v-model="form.{f}" type="textarea" placeholder="请输入{label}" />',
            '        </el-form-item>',
        ]
    return [
        f'        <el-form-item label="{label}" prop="{f}">',
        f'          <el-input v-model="form.{f}" placeholder="请输入{label}" />',
        '        </el-form-item>',
    ]


def render_index_vue(table, cfg):
    cls = table['class_name']
    var = table['business_name']
    var_list = f'{var}List'
    dict_types = _dict_types(table)
    query_cols = [c for c in table['columns'] if c['query']]
    list_cols = [c for c in table['columns'] if c['list']]
    # 主键列不进编辑表单：编辑时 form.value 由 getX() 回来的整行数据填充，
    # 主键在里面就够 update 用的，不需要（也不该）让用户改主键
    _pk_java = [c['java_field'] for c in _pk_list(table)] or [table['pk_field']]
    edit_cols = [c for c in _business_columns(table) if c['java_field'] not in _pk_java]
    required_cols = [c for c in edit_cols if c['required']]
    # 复合主键（中间表常见）：前端按组合键标识行，且不提供批量操作
    composite = _is_composite(table)
    pk_js = [c['java_field'] for c in _pk_list(table)] or [table['pk_field']]
    pk_call = ', '.join(pk_js)                                     # getX(a, b) / delX(a, b)
    pk_row_call = ', '.join(f'row.{f}' for f in pk_js)             # 行内取值
    pk_row_key_expr = ' + "-" + '.join(f'row.{f}' for f in pk_js)  # 组合键表达式
    pk_field = table['pk_field']
    perm = table['permission_prefix']
    between_cols = [c for c in query_cols if c['query_type'] == 'BETWEEN']
    ts = cfg.frontend_ts

    L = []
    A = L.append
    A('<template>')
    A('  <div class="app-container">')
    if query_cols:
        A('    <el-form :model="queryParams" ref="queryRef" :inline="true" v-show="showSearch" label-width="88px">')
        for c in query_cols:
            L.extend(_query_form_item(c))
        A('      <el-form-item>')
        A('        <el-button type="primary" icon="Search" @click="handleQuery">搜索</el-button>')
        A('        <el-button icon="Refresh" @click="resetQuery">重置</el-button>')
        A('      </el-form-item>')
        A('    </el-form>')
        A('')
    A('    <el-row :gutter="10" class="mb8">')
    A('      <el-col :span="1.5">')
    A(f'        <el-button type="primary" plain icon="Plus" @click="handleAdd" v-hasPermi="[\'{perm}:add\']">新增</el-button>')
    A('      </el-col>')
    # 批量修改/删除依赖「一行一个主键」，复合主键下不成立 → 不渲染这两个按钮
    if not composite:
        A('      <el-col :span="1.5">')
        A(f'        <el-button type="success" plain icon="Edit" :disabled="single" @click="handleUpdate" v-hasPermi="[\'{perm}:edit\']">修改</el-button>')
        A('      </el-col>')
        A('      <el-col :span="1.5">')
        A(f'        <el-button type="danger" plain icon="Delete" :disabled="multiple" @click="handleDelete" v-hasPermi="[\'{perm}:remove\']">删除</el-button>')
        A('      </el-col>')
    A('      <el-col :span="1.5">')
    A(f'        <el-button type="warning" plain icon="Download" @click="handleExport" v-hasPermi="[\'{perm}:export\']">导出</el-button>')
    A('      </el-col>')
    A('      <right-toolbar v-model:showSearch="showSearch" @queryTable="getList"></right-toolbar>')
    A('    </el-row>')
    A('')
    if composite:
        # 组合键标识行：不能用单一主键属性，给 row-key 一个函数
        A(f'    <el-table v-loading="loading" :data="{var_list}" :row-key="rowKey">')
    else:
        A(f'    <el-table v-loading="loading" :data="{var_list}" @selection-change="handleSelectionChange">')
        A('      <el-table-column type="selection" width="55" align="center" />')
    for c in list_cols:
        L.extend(_table_column(c))
    A('      <el-table-column label="操作" align="center" width="180" class-name="small-padding fixed-width">')
    A('        <template #default="scope">')
    A(f'          <el-button link type="primary" icon="Edit" @click="handleUpdate(scope.row)" v-hasPermi="[\'{perm}:edit\']">修改</el-button>')
    A(f'          <el-button link type="primary" icon="Delete" @click="handleDelete(scope.row)" v-hasPermi="[\'{perm}:remove\']">删除</el-button>')
    A('        </template>')
    A('      </el-table-column>')
    A('    </el-table>')
    A('')
    A('    <pagination')
    A('      v-show="total>0"')
    A('      :total="total"')
    A('      v-model:page="queryParams.pageNum"')
    A('      v-model:limit="queryParams.pageSize"')
    A('      @pagination="getList"')
    A('    />')
    A('')
    A('    <!-- 添加或修改对话框 -->')
    A('    <el-dialog :title="title" v-model="open" width="500px" append-to-body>')
    A(f'      <el-form ref="{var}Ref" :model="form" :rules="rules" label-width="100px">')
    for c in edit_cols:
        L.extend(_form_item(c))
    A('      </el-form>')
    A('      <template #footer>')
    A('        <div class="dialog-footer">')
    A('          <el-button type="primary" @click="submitForm">确 定</el-button>')
    A('          <el-button @click="cancel">取 消</el-button>')
    A('        </div>')
    A('      </template>')
    A('    </el-dialog>')
    A('  </div>')
    A('</template>')
    A('')
    A(f'<script setup name="{cls}"{" lang=\"ts\"" if ts else ""}>')
    A(f'import {{ list{cls}, get{cls}, del{cls}, add{cls}, update{cls} }} from "@/api/{table["module_name"]}/{var}"')
    A('')
    A('const { proxy } = getCurrentInstance()')
    if dict_types:
        names = ', '.join(f'"{d}"' for d in dict_types)
        A(f'const {{ {", ".join(dict_types)} }} = useDict({names})')
    A('')
    A(f'const {var_list} = ref<any[]>([])' if ts else f'const {var_list} = ref([])')
    A('const open = ref(false)')
    A('const loading = ref(true)')
    A('const showSearch = ref(true)')
    if composite:
        A('/** 复合主键：没有单一 id 可选，用组合键唯一标识一行 */')
        A('const rowKey = (row: any) => `${row.' + '}-${row.'.join(pk_js) + '}`' if ts
          else 'const rowKey = (row) => `${row.' + '}-${row.'.join(pk_js) + '}`')
    else:
        A('const ids = ref<any[]>([])' if ts else 'const ids = ref([])')
        A('const single = ref(true)')
        A('const multiple = ref(true)')
    A('const total = ref(0)')
    A('const title = ref("")')
    for c in between_cols:
        A(f'const daterange{_attr_name(c["java_field"])} = ref([])')
    A('')
    A('const data = reactive({')
    A('  form: {},')
    A('  queryParams: {')
    A('    pageNum: 1,')
    A('    pageSize: 10,')
    for c in query_cols:
        A(f'    {c["java_field"]}: undefined,')
    A('  },')
    A('  rules: {')
    for c in required_cols:
        A(f'    {c["java_field"]}: [{{ required: true, message: "{c["comment"]}不能为空", trigger: "{_trigger(c)}" }}],')
    A('  }')
    A('})')
    A('')
    A('const { queryParams, form, rules } = toRefs(data)')
    A('')
    A(f'/** 查询{cls}列表 */')
    A('function getList() {')
    A('  loading.value = true')
    A(f'  list{cls}(queryParams.value).then(response => {{')
    A(f'    {var_list}.value = response.rows')
    A('    total.value = response.total')
    A('    loading.value = false')
    A('  })')
    A('}')
    A('')
    A('/** 取消按钮 */')
    A('function cancel() {')
    A('  open.value = false')
    A('  reset()')
    A('}')
    A('')
    A('/** 表单重置 */')
    A('function reset() {')
    A('  form.value = {')
    for c in _business_columns(table):
        A(f'    {c["java_field"]}: undefined,')
    A('  }')
    A(f'  proxy.resetForm("{var}Ref")')
    A('}')
    A('')
    A('/** 搜索按钮操作 */')
    A('function handleQuery() {')
    A('  queryParams.value.pageNum = 1')
    for c in between_cols:
        A(f'  proxy.addDateRange(queryParams.value, daterange{_attr_name(c["java_field"])}.value, "{_attr_name(c["java_field"])}")')
    A('  getList()')
    A('}')
    A('')
    A('/** 重置按钮操作 */')
    A('function resetQuery() {')
    A('  proxy.resetForm("queryRef")')
    A('  handleQuery()')
    A('}')
    A('')
    if not composite:
        A('/** 多选框选中数据 */')
        A('function handleSelectionChange(selection) {')
        A(f'  ids.value = selection.map(item => item.{pk_field})')
        A('  single.value = selection.length != 1')
        A('  multiple.value = !selection.length')
        A('}')
        A('')
    A('/** 新增按钮操作 */')
    A('function handleAdd() {')
    A('  reset()')
    A('  open.value = true')
    A(f'  title.value = "添加{cls}"')
    A('}')
    A('')
    A('/** 修改按钮操作 */')
    A('function handleUpdate(row) {')
    A('  reset()')
    if composite:
        A(f'  const {{ {", ".join(pk_js)} }} = row')
        A(f'  get{cls}({pk_call}).then(response => {{')
    else:
        A(f'  const {pk_field} = row.{pk_field} || ids.value')
        A(f'  get{cls}({pk_field}).then(response => {{')
    A('    form.value = response.data')
    A('    open.value = true')
    A(f'    title.value = "修改{cls}"')
    A('  })')
    A('}')
    A('')
    A('/** 提交按钮 */')
    A('function submitForm() {')
    A(f'  proxy.$refs["{var}Ref"].validate(valid => {{')
    A('    if (valid) {')
    # 提交时判断「新增还是修改」：单主键看那一个，复合主键要几个都在才算修改
    A('      if (' + ' && '.join(f'form.value.{f}' for f in pk_js) + ') {')
    A(f'        update{cls}(form.value).then(response => {{')
    A('          proxy.$modal.msgSuccess("修改成功")')
    A('          open.value = false')
    A('          getList()')
    A('        })')
    A('      } else {')
    A(f'        add{cls}(form.value).then(response => {{')
    A('          proxy.$modal.msgSuccess("新增成功")')
    A('          open.value = false')
    A('          getList()')
    A('        })')
    A('      }')
    A('    }')
    A('  })')
    A('}')
    A('')
    A('/** 删除按钮操作 */')
    A('function handleDelete(row) {')
    if composite:
        A(f'  const _key = `${{row.{pk_js[0]}}}-${{row.{pk_js[1]}}}`' if ts
          else f'  const _key = `${{row.{pk_js[0]}}}-${{row.{pk_js[1]}}}`')
        A('  proxy.$modal.confirm(\'是否确认删除编号为"\' + _key + \'"的数据项？\').then(function() {')
        A(f'    return del{cls}({pk_row_call})')
    else:
        A('  const _' + pk_field + 's = row.' + pk_field + ' || ids.value')
        A(f'  proxy.$modal.confirm(\'是否确认删除编号为"\' + _{pk_field}s + \'"的数据项？\').then(function() {{')
        A(f'    return del{cls}(_{pk_field}s)')
    A('  }).then(() => {')
    A('    getList()')
    A('    proxy.$modal.msgSuccess("删除成功")')
    A('  }).catch(() => {})')
    A('}')
    A('')
    A('/** 导出按钮操作 */')
    A('function handleExport() {')
    A('  proxy.download(')
    A(f'    "{table["module_name"]}/{var}/export",')
    A('    {')
    A('      ...queryParams.value')
    A('    },')
    A(f'    `{var}_${{new Date().getTime()}}.xlsx`')
    A('  )')
    A('}')
    A('')
    A('getList()')
    A('</script>')
    return '\n'.join(L) + '\n'


def _trigger(c):
    return 'change' if c['dict_type'] or c['html_type'] in ('datetime', 'radio', 'select') else 'blur'


# ---------------------------------------------------------------- README

def render_readme(schema, cfg):
    tables = schema['tables']
    root = BACKEND_ROOT.format(module=cfg.module_name)
    lines = [
        '# 若依 RuoYi-Vue3 模块代码',
        '',
        f'由 EA 平台从 ER 模型生成，共 **{len(tables)} 张表**、{len(schema["join_tables"])} 张中间表。',
        '代码骨架为确定性模板生成（对齐若依官方 Velocity 模板），中文注释/列标签由 AI 或内置词表补齐。',
        '',
        '## 目录怎么放',
        '',
        '| 本包内的路径 | 放到若依工程 |',
        '|---|---|',
        f'| `{root}/src/main/java/...` | 后端 Maven 模块 `{root}` 的 `src/main/java/...` |',
        f'| `{root}/src/main/resources/mapper/{cfg.module_name}/` | 同上模块的 `src/main/resources/mapper/{cfg.module_name}/` |',
        '| `frontend/src/api/...` | RuoYi-Vue3 前端工程的 `src/api/...` |',
        '| `frontend/src/views/...` | RuoYi-Vue3 前端工程的 `src/views/...` |',
        '| `sql/*.sql` | 直接在业务库里执行（建表 + 菜单）|',
        '',
        '## 生成信息',
        '',
        f'- 包名：`{cfg.package_name}`',
        f'- 模块名：`{cfg.module_name}`　业务名：按表推导（见下表）',
        f'- 作者：{cfg.author}　父菜单 ID：{cfg.parent_menu_id}',
        f'- Servlet API：`{cfg.servlet_api}`（若依 3.8.x 为 `javax`，3.9.x/Spring Boot 3 为 `jakarta`）',
        f'- 前端产物：`.{cfg.frontend_ext}`' + ('（`<script setup lang="ts">`）' if cfg.frontend_ts else ''),
        '',
        '| 表 | 类名 | 目录/权限前缀 | 表注释 |',
        '|---|---|---|---|',
    ]
    for t in tables:
        lines.append(f'| {t["table_name"]} | {t["class_name"]} | {t["module_name"]}/{t["business_name"]}　`{t["permission_prefix"]}` | {t["comment"]} |')

    if schema['join_tables']:
        lines += ['', '多对多中间表（只生成 DDL，不生成 Java/前端）：' + '、'.join(f'`{j["table_name"]}`' for j in schema['join_tables'])]

    lines += [
        '',
        '## 落地步骤',
        '',
        '1. 执行 `sql/*.sql`（建表 + 写入菜单）。',
        f'2. 后端：把 `{root}/src` 合并进目标模块，确认该模块已被 `ruoyi-admin` 依赖、且 Mapper 扫描路径覆盖 `{cfg.package_name}.mapper`。',
        '3. 前端：把 `frontend/src/api`、`frontend/src/views` 合并进 RuoYi-Vue3 工程。',
        f'4. 重新登录（或清一次菜单缓存）即可在左侧菜单看到；菜单默认挂在父 ID `{cfg.parent_menu_id}` 下。',
        '5. 启动后到「系统管理 → 菜单管理」给角色勾上新菜单的权限，否则按钮不显示（`v-hasPermi` 生效）。',
        '',
        '## 需要人工确认的地方',
        '',
        '- **导出功能**依赖 `ExcelUtil`，其 import 包名随若依版本不同（`jakarta` / `javax`），不对就改一行 import。',
        '- 若依代码生成器**不生成 M:N 关联导航**；多对多只给了中间表 DDL，两端按普通 CRUD 处理。',
        '- 关联关系按若依的**平铺外键**惯例处理，未自动改表结构；需要外键列请在 ER 图里补上再生成一次。',
        '- `@Excel` 的字典选项文本取自若依内置字典；若你的库里改过字典项，导出的 Excel 中文可能与页面不一致（无害）。',
        '- 本模板对齐**经典 RuoYi-Vue**（`com.ruoyi.*`、`@ss.hasPermi`、MyBatis）。RuoYi-Vue-Plus（`org.dromara.*`、`@SaCheckPermission`、MyBatis-Plus）不适用。',
        '- **复合主键表（如中间表）用的是本平台自定义方案**：若依官方只支持单主键，官方生成器遇到复合主键会只取第一个。'
        '这里的做法是——所有主键列都保持主键，Mapper/Service 收多参数（`selectXxxByAAndB`）、'
        'Controller 路径是两段（`/a/b`）、XML 用 `a = #{a} and b = #{b}`、'
        '**不生成批量删除**（复合主键的批量删语义不成立）。懂若依的人会看出与官方不同，这是刻意的。',
    ]
    if schema['warnings']:
        lines += ['', '## 生成告警', '']
        lines += [f'- {w}' for w in schema['warnings']]
    return '\n'.join(lines) + '\n'


# ---------------------------------------------------------------- Maven 模块

def render_module_pom(schema, cfg):
    """生成模块自身的 pom.xml。

    形态不是抄来的、是**真编译验证过**的（2026-10-04，RuoYi-Vue 3.9.2 + Spring Boot 4.1.0 +
    JDK 17，`mvn compile` BUILD SUCCESS）：与官方 `ruoyi-system/pom.xml` 同形——
    parent 写根工程坐标、artifactId 只有模块名、**依赖只声明 ruoyi-common 且不写 version**
    （版本由根 pom 的 dependencyManagement 管）。

    为什么一个依赖就够：产物用到的 `com.ruoyi.common.*`（BaseEntity / BaseController /
    AjaxResult / TableDataInfo / ExcelUtil / DateUtils / BusinessType）以及
    `jakarta.servlet-api`、`spring-web`、`spring-boot-starter-security`(@PreAuthorize)、
    `commons-lang3`、`poi-ooxml`、`pagehelper` 全部由 ruoyi-common 传递带来。
    """
    module = cfg.module_name
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <parent>
        <artifactId>ruoyi</artifactId>
        <groupId>com.ruoyi</groupId>
        <version>{cfg.ruoyi_version}</version>
    </parent>
    <modelVersion>4.0.0</modelVersion>

    <artifactId>ruoyi-{module}</artifactId>

    <description>
        {module}业务模块
    </description>

    <dependencies>

        <!-- 通用工具。BaseEntity/BaseController/AjaxResult/TableDataInfo/ExcelUtil/DateUtils、
             jakarta.servlet-api、spring-security(@PreAuthorize)、commons-lang3、poi、pagehelper
             都由它传递带来，所以本模块只需要这一个依赖 -->
        <dependency>
            <groupId>com.ruoyi</groupId>
            <artifactId>ruoyi-common</artifactId>
        </dependency>

    </dependencies>

</project>
'''


def render_integration_readme(schema, cfg):
    """把「怎么把它接进若依工程」写成可直接粘贴的片段。

    **三处编辑缺一不可**——第三处（根 pom 的 dependencyManagement）是 2026-10-04 真编译
    才发现的：根 pom 只给官方那几个模块（ruoyi-common/system/framework/…）管了版本，
    新模块不加这条，`ruoyi-admin` 引用它会报
    `'dependencies.dependency.version' for com.ruoyi:{module}:jar is missing`。
    """
    module = cfg.module_name
    version = cfg.ruoyi_version
    return f'''# 集成步骤（{module} 模块）

按顺序做完这三处编辑，再执行 SQL、合并前端产物。**三处缺一不可**（第三处最容易漏，
漏了会在 `mvn compile` 时报 `'dependencies.dependency.version' ... is missing`）。

## 1. 根 `pom.xml` 的 `<modules>` 里加一行

```xml
        <module>ruoyi-{module}</module>
```

## 2. 根 `pom.xml` 的 `<dependencyManagement>` 里加版本（**最容易漏的一步**）

```xml
            <dependency>
                <groupId>com.ruoyi</groupId>
                <artifactId>ruoyi-{module}</artifactId>
                <version>${{ruoyi.version}}</version>
            </dependency>
```

> 根 pom 只为官方模块管了版本。新模块不加这条，下一步引用它时会因为拿不到版本而
> 直接让 Maven 解析失败（`ProjectBuildingException`）。

## 3. `ruoyi-admin/pom.xml` 的 `<dependencies>` 里加依赖

```xml
        <dependency>
            <groupId>com.ruoyi</groupId>
            <artifactId>ruoyi-{module}</artifactId>
        </dependency>
```

> 这里**不写 version**，由第 2 步统一管理。

## 4. 执行建表与菜单 SQL

```bash
mysql -u<用户> -p --default-character-set=utf8mb4 <数据库> < sql/*.sql
```

> **必须带 `--default-character-set=utf8mb4`**：SQL 里有中文表注释/菜单名，
> 客户端字符集不对会被截断或写乱码（实测报 `Data too long for column`）。
> 另外这些 SQL 会 **insert 到 `sys_menu`**，所以要导入**已经跑过若依自带
> `sql/ry_*.sql` 的业务库**，而不是新建的空库——否则会报 `Table 'sys_menu' doesn't exist`。

## 5. 合并前端产物

把 `frontend/src/api/` 与 `frontend/src/views/` 合并进 RuoYi-Vue3 工程。

## 6. 重启并授权

重新登录（或清一次菜单缓存）即可在左侧菜单看到；菜单挂在父 ID `{cfg.parent_menu_id}` 下。
首次还需到「系统管理 → 菜单管理」给角色勾上新菜单权限，否则按钮不显示（`v-hasPermi` 生效）。

---

## 版本对齐

本包按 **RuoYi-Vue {version}**（Spring Boot {'4.x/3.x' if cfg.servlet_api == 'jakarta' else '2.x'}、
`{cfg.servlet_api}` servlet API）生成。若你的工程是别的版本，请把 `ruoyiVersion` 配置项
改成你的版本号后重新生成——pom 的 `<parent><version>` 必须与目标工程一致。
'''


# ---------------------------------------------------------------- 组装

def render_module_files(schema, cfg):
    """schema → 文件列表 [{path, name, group, language, content}]。"""
    files = []
    root = BACKEND_ROOT.format(module=cfg.module_name)

    def add(path, content, group, language):
        files.append({
            'path': path,
            'name': path.rsplit('/', 1)[-1],
            'group': group,
            'language': language,
            'content': content,
        })

    for t in schema['tables']:
        cls, var, mod = t['class_name'], t['business_name'], t['module_name']
        base = f'{root}/src/main/java/{cfg.package_path}'
        add(f'{base}/domain/{cls}.java', render_domain(t, cfg), 'backend', 'java')
        add(f'{base}/mapper/{cls}Mapper.java', render_mapper_java(t, cfg), 'backend', 'java')
        add(f'{root}/src/main/resources/mapper/{mod}/{cls}Mapper.xml', render_mapper_xml(t, cfg), 'backend', 'xml')
        add(f'{base}/service/I{cls}Service.java', render_service_interface(t, cfg), 'backend', 'java')
        add(f'{base}/service/impl/{cls}ServiceImpl.java', render_service_impl(t, cfg), 'backend', 'java')
        add(f'{base}/controller/{cls}Controller.java', render_controller(t, cfg), 'backend', 'java')
        add(f'frontend/src/api/{mod}/{var}.{cfg.frontend_ext}', render_api(t, cfg), 'frontend', cfg.frontend_ext)
        add(f'frontend/src/views/{mod}/{var}/index.vue', render_index_vue(t, cfg), 'frontend', 'vue')

    # 每张表的 SQL 单独成文件；中间表 DDL 挂在它左表（名字在前的那张）的 SQL 里
    joins = schema['join_tables']
    for t in schema['tables']:
        mine = [j for j in joins if j['left_table'] == t['table_name']]
        add(f'sql/{t["table_name"]}.sql', render_table_sql(t, cfg, mine), 'sql', 'sql')

    if not schema['tables']:
        return []   # 空模型不产出任何文件（调用方按 meta.warnings 提示）
    # 模块自身的 pom：没有它就只能手工建模块，是这个包此前最卡的缺口
    add(f'{root}/pom.xml', render_module_pom(schema, cfg), 'backend', 'xml')
    add('INTEGRATION.md', render_integration_readme(schema, cfg), 'docs', 'md')
    add('README.md', render_readme(schema, cfg), 'docs', 'md')
    return files


def _today():
    import datetime
    return datetime.date.today().isoformat()
