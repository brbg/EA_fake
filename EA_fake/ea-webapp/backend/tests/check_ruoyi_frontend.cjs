// 若依前端产物的编译期检查（需要 Node + 本项目已装的 @vue/compiler-sfc / typescript）
//
//   node backend/tests/check_ruoyi_frontend.cjs <产物目录>
//
// 用途：后端产物可以用 Maven 真编译验证，前端此前只有 Python 侧的静态检查
// （vue_lint 查标签配平/ref 一致/字典声明）。本脚本补上前端的编译验证：
//   .vue    → SFC 解析 + 模板编译 + <script setup> 编译
//   .ts/.js → TypeScript 语法诊断
//
// 不执行任何外部仓库的代码——用的是本项目 node_modules 里已有的工具链，
// 这点是刻意的（第三方克隆来的仓库跑 npm install 会执行它自己的生命周期脚本）。
//
// 已验证检查器本身有效：故意写坏的 .vue 能报出「插值未闭合/标签未闭合」，
// 故意写坏的 .ts 能报出「':' expected」等语法错误——不是恒过的安慰剂。
//
// 配合用法：
//   cd backend && python -c "...生成产物..."   # 把 frontend/** 导出到某个目录
//   node tests/check_ruoyi_frontend.cjs <那个目录>

// 用「本项目自己装的」@vue/compiler-sfc + typescript 编译若依产物里的前端文件。
// 不执行任何外部仓库的代码，只做编译期检查：
//   .vue  → SFC parse + compileTemplate + compileScript
//   .ts/.js → TypeScript transpileModule（只看语法诊断）
const fs = require('fs')
const path = require('path')
// 显式指向本项目已装的工具链（脚本可能在任意位置运行）
const PROJ = 'e:/daima/项目/EA_fake/EA_fake/ea-webapp'
const fromProj = (m) => require(require.resolve(m, { paths: [PROJ] }))
const sfc = fromProj('@vue/compiler-sfc')
const ts = fromProj('typescript')

const root = process.argv[2]
if (!root) { console.error('用法: node check_vue.js <产物目录>'); process.exit(2) }

const files = []
;(function walk(d) {
  for (const e of fs.readdirSync(d, { withFileTypes: true })) {
    const p = path.join(d, e.name)
    if (e.isDirectory()) walk(p)
    else files.push(p)
  }
})(root)

let checked = 0
const problems = []

for (const f of files) {
  const rel = path.relative(root, f).replace(/\\/g, '/')
  const src = fs.readFileSync(f, 'utf8')
  if (f.endsWith('.vue')) {
    checked++
    const { descriptor, errors } = sfc.parse(src, { filename: f })
    for (const e of errors) problems.push(`${rel}: SFC 解析: ${e.message || e}`)
    if (descriptor.template) {
      const r = sfc.compileTemplate({
        source: descriptor.template.content, filename: f, id: 'probe',
        compilerOptions: { mode: 'module' },
      })
      for (const e of r.errors || []) problems.push(`${rel}: 模板编译: ${e.message || e}`)
    }
    if (descriptor.scriptSetup) {
      try {
        sfc.compileScript(descriptor, { id: 'probe' })
      } catch (e) {
        problems.push(`${rel}: <script setup> 编译: ${e.message}`)
      }
    }
  } else if (/\.(ts|js)$/.test(f)) {
    checked++
    const out = ts.transpileModule(src, {
      reportDiagnostics: true,
      compilerOptions: { target: ts.ScriptTarget.ESNext, module: ts.ModuleKind.ESNext, isolatedModules: true },
    })
    for (const d of out.diagnostics || []) {
      if (d.category === ts.DiagnosticCategory.Error) {
        const m = ts.flattenDiagnosticMessageText(d.messageText, ' ')
        problems.push(`${rel}: TS 语法: ${m}`)
      }
    }
  }
}

console.log(`检查 ${checked} 个前端文件（${files.length} 个文件里筛出 .vue/.ts/.js）`)
if (problems.length) {
  console.log(`发现 ${problems.length} 个问题：`)
  for (const p of problems.slice(0, 20)) console.log('  ✗', p)
  process.exit(1)
}
console.log('全部通过 ✅')

// 注意：文件名必须是 .cjs —— ea-webapp/package.json 里是 "type": "module"，
// 用 .js 会被当成 ES module，require 直接报 ReferenceError。
