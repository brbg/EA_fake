<script setup lang="ts">
// 若依 RuoYi-Vue3 整套模块的多文件预览：左侧按 group 分组选文件，右侧看内容。
// 用项目既有的 .card/.btn 视觉体系，不引 Element Plus（与 AgentRunSteps.vue 的做法一致）。
import { computed, ref, watch } from 'vue'

export interface RuoYiFile {
  path: string
  name: string
  group: string
  language: string
  content: string
}

const props = defineProps<{
  files: RuoYiFile[]
  meta: Record<string, any> | null
  generating?: boolean
  downloading?: boolean
}>()

const emit = defineEmits<{
  (e: 'download'): void
  (e: 'copy-file', path: string): void
}>()

const GROUPS: Array<{ key: string; label: string; icon: string }> = [
  { key: 'backend', label: '后端 Java / MyBatis', icon: 'fa-mug-hot' },
  { key: 'frontend', label: '前端 Vue / TS', icon: 'fa-code' },
  { key: 'sql', label: 'SQL（建表 + 菜单）', icon: 'fa-database' },
  { key: 'docs', label: '说明', icon: 'fa-file-lines' },
]

const current = ref<string>('')
const showWarnings = ref(false)

// 默认选中第一个文件；切换模型重生成后若原文件还在就保持选中
watch(
  () => props.files,
  (list) => {
    if (!list.length) {
      current.value = ''
      return
    }
    if (!list.some((f) => f.path === current.value)) current.value = list[0].path
  },
  { immediate: true }
)

const grouped = computed(() =>
  GROUPS.map((g) => ({ ...g, items: props.files.filter((f) => f.group === g.key) })).filter((g) => g.items.length)
)
const active = computed(() => props.files.find((f) => f.path === current.value) || null)
const warnings = computed<string[]>(() => props.meta?.warnings || [])
const tables = computed<any[]>(() => props.meta?.tables || [])

const aiBadge = computed(() => {
  if (!props.meta) return null
  if (props.meta.aiUsed) return { cls: 'ok', icon: 'fa-wand-magic-sparkles', text: 'AI 已补中文注释与列标签' }
  const reason = props.meta.aiFallback
  const map: Record<string, string> = {
    disabled: 'AI 未启用，表注释/列标签由内置词表生成',
    truncated: 'AI 返回被截断，已按内置词表降级',
    invalid_json: 'AI 返回格式异常，已按内置词表降级',
  }
  const text = map[reason] || (reason ? `AI 调用失败（${reason}），已按内置词表降级` : '已按内置词表生成')
  return { cls: 'off', icon: 'fa-circle-info', text }
})

const copyCurrent = () => {
  if (active.value) emit('copy-file', active.value.path)
}
</script>

<template>
  <div class="ry-panel">
    <div class="ry-head">
      <span class="ry-title"><i class="fas fa-cubes"></i> 若依模块文件</span>
      <span class="ry-count">共 {{ files.length }} 个文件<template v-if="tables.length"> · {{ tables.length }} 张表</template></span>
      <span v-if="aiBadge" class="ry-badge" :class="aiBadge.cls"><i class="fas" :class="aiBadge.icon"></i> {{ aiBadge.text }}</span>
      <button
        v-if="warnings.length"
        type="button"
        class="ry-warn-toggle"
        :class="{ open: showWarnings }"
        @click="showWarnings = !showWarnings"
      ><i class="fas fa-triangle-exclamation"></i> {{ warnings.length }} 条告警 <i class="fas fa-chevron-down"></i></button>
      <button type="button" class="btn btn-primary ry-dl" :disabled="!files.length || downloading" @click="emit('download')">
        <i class="fas" :class="downloading ? 'fa-spinner fa-spin' : 'fa-download'"></i>
        {{ downloading ? '打包中…' : '下载 ZIP' }}
      </button>
    </div>

    <div v-if="tables.length" class="ry-tables">
      <span v-for="t in tables" :key="t.tableName" class="ry-table-chip" :title="`权限前缀 ${t.permissionPrefix}`">
        <i class="fas fa-table"></i> {{ t.tableName }} → {{ t.className }}
      </span>
      <span v-if="meta?.joinTables?.length" class="ry-table-chip join">
        <i class="fas fa-link"></i> 中间表 {{ meta.joinTables.join('、') }}
      </span>
    </div>

    <ul v-if="showWarnings" class="ry-warns">
      <li v-for="(w, i) in warnings" :key="i">{{ w }}</li>
    </ul>

    <div class="ry-body">
      <div class="ry-tree">
        <div v-for="g in grouped" :key="g.key" class="ry-group">
          <div class="ry-group-title"><i class="fas" :class="g.icon"></i> {{ g.label }}</div>
          <button
            v-for="f in g.items"
            :key="f.path"
            type="button"
            class="ry-file"
            :class="{ active: f.path === current }"
            :title="f.path"
            @click="current = f.path"
          >{{ f.name }}</button>
        </div>
      </div>

      <div class="ry-view">
        <div class="ry-view-head">
          <span class="ry-path">{{ active?.path || '（无文件）' }}</span>
          <button type="button" class="ry-copy" :disabled="!active" @click="copyCurrent"><i class="fas fa-copy"></i> 复制当前文件</button>
        </div>
        <pre class="ry-code">{{ active?.content || '' }}</pre>
      </div>
    </div>
  </div>
</template>

<style scoped>
.ry-panel {
  margin-top: 14px;
  border: 1px solid #e3e8f1;
  border-radius: 14px;
  background: #fff;
  overflow: hidden;
  animation: ry-in .28s cubic-bezier(.22, .9, .3, 1);
}
@keyframes ry-in { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: none; } }

.ry-head { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; padding: 10px 14px; border-bottom: 1px solid #eef2f9; background: linear-gradient(180deg, #fbfcff 0%, #f6f9ff 100%); }
.ry-title { font-weight: 600; color: #22304a; }
.ry-title > i { color: #1f5eff; margin-right: 4px; }
.ry-count { font-size: 12px; color: #6b7a90; background: #eef3ff; border-radius: 999px; padding: 2px 10px; }
.ry-badge { font-size: 11.5px; border-radius: 999px; padding: 3px 10px; display: inline-flex; align-items: center; gap: 5px; }
.ry-badge.ok { background: #e8f7ee; color: #16a34a; }
.ry-badge.off { background: #fff7e8; color: #b45309; }
.ry-warn-toggle { border: none; background: transparent; color: #b45309; font-size: 11.5px; cursor: pointer; padding: 2px 4px; }
.ry-warn-toggle i:last-child { font-size: 9px; transition: transform .2s; }
.ry-warn-toggle.open i:last-child { transform: rotate(180deg); }
.ry-dl { margin-left: auto; }

.ry-tables { display: flex; flex-wrap: wrap; gap: 6px; padding: 9px 14px 3px; }
.ry-table-chip { font-size: 11.5px; color: #4a5568; background: #f4f7ff; border: 1px solid #e2e9f8; border-radius: 999px; padding: 2px 10px; }
.ry-table-chip > i { color: #1f5eff; margin-right: 3px; }
.ry-table-chip.join { background: #f8f5ff; border-color: #e7e0f8; }

.ry-warns { margin: 8px 14px 0; padding: 8px 12px 8px 28px; background: #fffbf3; border: 1px solid #f3e3c8; border-radius: 10px; font-size: 12px; color: #8a6d3b; line-height: 1.7; }
.ry-warns li { list-style: disc; }

.ry-body { display: flex; gap: 0; border-top: 1px solid #eef2f9; margin-top: 10px; min-height: 380px; }
.ry-tree { width: 230px; flex-shrink: 0; border-right: 1px solid #eef2f9; padding: 10px 8px; max-height: 620px; overflow-y: auto; }
.ry-group + .ry-group { margin-top: 10px; }
.ry-group-title { font-size: 11px; color: #8b98ab; padding: 0 6px 5px; letter-spacing: .3px; }
.ry-group-title > i { color: #1f5eff; margin-right: 4px; }
.ry-file {
  display: block; width: 100%; text-align: left;
  border: none; background: transparent; border-radius: 8px;
  padding: 5px 8px; font-size: 12px; color: #334155;
  cursor: pointer; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  transition: background .15s, color .15s;
}
.ry-file:hover { background: #f4f7ff; color: #1f5eff; }
.ry-file.active { background: #eef4ff; color: #1f5eff; font-weight: 600; }

.ry-view { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.ry-view-head { display: flex; align-items: center; gap: 8px; padding: 8px 12px; border-bottom: 1px solid #f2f5fb; }
.ry-path { flex: 1; min-width: 0; font-size: 11.5px; color: #6b7a90; font-family: Consolas, Monaco, monospace; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ry-copy { border: 1px solid #dbe4ff; background: #f4f7ff; color: #1f5eff; border-radius: 999px; padding: 3px 10px; font-size: 11.5px; cursor: pointer; }
.ry-copy:hover:not(:disabled) { background: #1f5eff; color: #fff; border-color: #1f5eff; }
.ry-copy:disabled { opacity: .5; cursor: not-allowed; }
.ry-code {
  flex: 1; margin: 0; padding: 14px 16px;
  background: #2d2d2d; color: #f8f8f2;
  font-family: Consolas, Monaco, 'Courier New', monospace; font-size: 12.5px; line-height: 1.55;
  max-height: 560px; overflow: auto; white-space: pre;
}
</style>
