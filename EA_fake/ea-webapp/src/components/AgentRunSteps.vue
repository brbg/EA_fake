<script setup lang="ts">
import { computed, reactive } from 'vue'
import type { AgentStepView } from '../agentService'

const props = withDefaults(defineProps<{ steps: AgentStepView[]; closable?: boolean }>(), {
  closable: true,
})

const emit = defineEmits<{ (e: 'close'): void }>()

const overall = computed(() => {
  if (!props.steps.length) return 'idle'
  if (props.steps.some((s) => s.status === 'running')) return 'running'
  if (props.steps.some((s) => s.status === 'error')) return 'partial'
  if (props.steps.every((s) => s.status === 'ok')) return 'ok'
  return 'done'
})
const doneCount = computed(() => props.steps.filter((s) => s.status === 'ok').length)
const percent = computed(() =>
  props.steps.length ? Math.round((doneCount.value / props.steps.length) * 100) : 0
)

// 各状态图标（pending 为空心点，不渲染图标）
const ICONS: Record<string, string> = {
  running: 'fas fa-circle-notch fa-spin',
  ok: 'fas fa-check',
  error: 'fas fa-xmark',
  skipped: 'fas fa-minus',
}

// 详情展开状态（按步骤 key 记录，默认收起）
const opened = reactive<Record<string, boolean>>({})
const toggle = (k: string) => { opened[k] = !opened[k] }

const fmt = (d: any): string => {
  if (d == null) return ''
  if (typeof d === 'object') {
    const kvs = Object.entries(d).filter(([, v]) => v !== undefined && v !== null && v !== '')
    if (!kvs.length) return ''
    return kvs.map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join('/') : v}`).join(' · ')
  }
  return String(d)
}
</script>

<template>
  <div class="agent-steps" :class="overall">
    <!-- 头部：标题 + 计数 + 进度条 + 状态 + 收起 -->
    <div class="steps-head">
      <span class="head-icon"><i class="fas fa-list-check"></i></span>
      <span class="head-title">工作进度</span>
      <span class="head-count">{{ doneCount }}/{{ steps.length }}</span>
      <span class="head-bar"><i :style="{ width: percent + '%' }"></i></span>
      <span v-if="overall === 'running'" class="head-tag running"><i class="fas fa-circle-notch fa-spin"></i> 执行中</span>
      <span v-else-if="overall === 'ok'" class="head-tag ok"><i class="fas fa-check"></i> 全部完成</span>
      <span v-else-if="overall === 'partial'" class="head-tag partial"><i class="fas fa-triangle-exclamation"></i> 部分失败</span>
      <span v-else-if="overall === 'done'" class="head-tag done">已结束</span>
      <button
        v-if="closable"
        type="button"
        class="head-close"
        title="收起工作进度"
        aria-label="收起工作进度"
        @click="emit('close')"
      ><i class="fas fa-xmark"></i></button>
    </div>

    <!-- 时间线：左侧圆点 + 连线，右侧步骤卡片 -->
    <div class="steps-body">
      <div v-for="(s, i) in steps" :key="s.key + i" class="step-node" :class="s.status">
        <div class="node-col">
          <span class="node-dot"><i v-if="ICONS[s.status]" :class="ICONS[s.status]"></i></span>
          <span v-if="i < steps.length - 1" class="node-line"></span>
        </div>

        <div class="node-card">
          <div class="card-head">
            <span class="card-title">{{ s.title }}</span>
            <span v-if="fmt(s.detail)" class="card-brief">{{ fmt(s.detail) }}</span>
            <button
              v-if="s.detail && fmt(s.detail)"
              type="button"
              class="card-toggle"
              :class="{ open: opened[s.key + i] }"
              @click="toggle(s.key + i)"
            ><i class="fas fa-chevron-down"></i> {{ opened[s.key + i] ? '收起' : '详情' }}</button>
          </div>
          <pre v-if="opened[s.key + i]" class="card-pre">{{ JSON.stringify(s.detail, null, 2) }}</pre>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.agent-steps {
  max-width: 760px;
  margin: 6px auto 12px;
  border: 1px solid #e3e8f1;
  border-radius: 16px;
  background: #fff;
  box-shadow: 0 2px 12px rgba(15, 23, 42, .05);
  overflow: hidden;
  font-size: 13px;
  animation: steps-in .28s cubic-bezier(.22, .9, .3, 1);
}
@keyframes steps-in { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: none; } }

/* ---------- 头部 ---------- */
.steps-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px 10px 14px;
  border-bottom: 1px solid #eef2f9;
  background: linear-gradient(180deg, #fbfcff 0%, #f6f9ff 100%);
}
.head-icon {
  width: 26px; height: 26px; border-radius: 8px;
  display: flex; align-items: center; justify-content: center;
  background: #eef4ff; color: #1f5eff; font-size: 12px; flex-shrink: 0;
}
.head-title { font-weight: 600; color: #22304a; white-space: nowrap; }
.head-count {
  font-size: 11px; font-weight: 500; color: #1f5eff;
  background: #eef3ff; border-radius: 999px; padding: 1px 8px;
  font-variant-numeric: tabular-nums;
}
.head-bar {
  flex: 1; min-width: 40px; height: 4px; border-radius: 999px;
  background: #e8eefb; overflow: hidden;
}
.head-bar > i {
  display: block; height: 100%; width: 0; border-radius: 999px;
  background: linear-gradient(90deg, #5b93ff 0%, #1f5eff 100%);
  transition: width .45s cubic-bezier(.22, .9, .3, 1);
}
.agent-steps.partial .head-bar > i { background: linear-gradient(90deg, #f6a96a 0%, #dc2626 100%); }
.agent-steps.ok .head-bar > i { background: linear-gradient(90deg, #4fd18b 0%, #16a34a 100%); }

.head-tag {
  font-size: 11px; padding: 2px 10px; border-radius: 999px;
  display: inline-flex; align-items: center; gap: 4px; white-space: nowrap;
}
.head-tag.running { background: #eaf1ff; color: #1f5eff; }
.head-tag.ok { background: #e8f7ee; color: #16a34a; }
.head-tag.partial { background: #fdf0f0; color: #dc2626; }
.head-tag.done { background: #f1f3f7; color: #64748b; }

.head-close {
  width: 24px; height: 24px; flex-shrink: 0;
  border: none; border-radius: 50%; background: transparent;
  color: #9aa7bb; font-size: 12px; cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  transition: background .18s, color .18s, transform .18s;
}
.head-close:hover { background: #eef2f9; color: #22304a; transform: rotate(90deg); }

/* ---------- 时间线主体 ---------- */
.steps-body { padding: 12px 14px 2px; }

.step-node { display: flex; gap: 10px; animation: card-in .3s cubic-bezier(.22, .9, .3, 1); }
@keyframes card-in { from { opacity: 0; transform: translateY(-6px); } to { opacity: 1; transform: none; } }

.node-col { display: flex; flex-direction: column; align-items: center; width: 22px; flex-shrink: 0; }
.node-dot {
  width: 22px; height: 22px; border-radius: 50%; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
  font-size: 10px; color: #fff;
  background: #fff; border: 2px solid #d4dded;
  transition: all .25s;
}
.step-node.ok .node-dot { background: #16a34a; border-color: #16a34a; }
.step-node.error .node-dot { background: #dc2626; border-color: #dc2626; }
.step-node.skipped .node-dot { background: #cbd5e1; border-color: #cbd5e1; }
.step-node.running .node-dot {
  background: #1f5eff; border-color: #1f5eff; font-size: 11px;
  animation: node-pulse 1.5s ease-in-out infinite;
}
@keyframes node-pulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(31, 94, 255, .30); }
  50% { box-shadow: 0 0 0 6px rgba(31, 94, 255, 0); }
}
.node-line { flex: 1; width: 2px; border-radius: 2px; background: #e9eef7; margin: 3px 0; }
.step-node.ok .node-line { background: #c7ecd5; }
.step-node.error .node-line { background: #f5cfcf; }

/* ---------- 步骤卡片 ---------- */
.node-card {
  flex: 1; min-width: 0;
  position: relative;
  margin-bottom: 10px;
  padding: 8px 12px 8px 14px;
  background: #fff;
  border: 1px solid #eef2f9;
  border-radius: 12px;
  transition: border-color .2s, box-shadow .2s, background .2s;
}
.node-card::before {
  content: ''; position: absolute; left: 0; top: 9px; bottom: 9px; width: 3px;
  border-radius: 999px; background: #e2e9f5; transition: background .25s;
}
.node-card:hover { border-color: #dbe6ff; box-shadow: 0 4px 14px rgba(31, 94, 255, .07); }

.step-node.ok .node-card::before { background: linear-gradient(180deg, #4fd18b 0%, #16a34a 100%); }
.step-node.error .node-card::before { background: linear-gradient(180deg, #f6a96a 0%, #dc2626 100%); }
.step-node.error .node-card { background: #fffbfb; border-color: #f7e2e2; }
.step-node.skipped .node-card { background: #fbfcfe; }
.step-node.running .node-card {
  border-color: #cfdeff;
  background: linear-gradient(180deg, #ffffff 0%, #f5f9ff 100%);
  box-shadow: 0 2px 12px rgba(31, 94, 255, .10);
}
.step-node.running .node-card::before { background: linear-gradient(180deg, #5b93ff 0%, #1f5eff 100%); }

.card-head { display: flex; align-items: baseline; gap: 8px; min-width: 0; }
.card-title { font-size: 13px; font-weight: 500; color: #64748b; }
.step-node.running .card-title { color: #1f5eff; font-weight: 600; }
.step-node.ok .card-title { color: #1f2937; }
.step-node.error .card-title { color: #dc2626; }
.card-brief {
  flex: 1; min-width: 0;
  font-size: 11.5px; color: #8b98ab;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.card-toggle {
  margin-left: auto; flex-shrink: 0;
  border: none; background: transparent; padding: 0 2px;
  font-size: 11px; color: #1f5eff; cursor: pointer;
  display: inline-flex; align-items: center; gap: 3px;
}
.card-toggle i { font-size: 9px; transition: transform .2s; }
.card-toggle.open i { transform: rotate(180deg); }
.card-toggle:hover { color: #1749c9; }

.card-pre {
  margin: 6px 0 0; padding: 8px 10px;
  font-size: 11px; line-height: 1.5; color: #4a5568;
  background: #f8fafd; border: 1px solid #e9eef7; border-radius: 8px;
  white-space: pre-wrap; word-break: break-all;
  max-height: 200px; overflow: auto;
}
</style>
