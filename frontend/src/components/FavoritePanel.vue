<template>
  <div class="favorite-panel">
    <template v-if="mode === 'list'">
      <div class="folder-list">
        <div
          v-for="folder in filteredFolders"
          :key="folder.id"
          class="folder-item"
          @click="handleSelect(folder)"
          @mousedown="handlePressStart(folder, $event)"
          @mouseup="handlePressEnd(folder)"
          @mouseleave="handlePressEnd(folder)"
          @touchstart.passive="handlePressStart(folder, $event)"
          @touchend="handlePressEnd(folder)"
          @touchcancel="handlePressEnd(folder)"
        >
          <div class="folder-icon" :style="{ backgroundColor: folder.color }">
            <el-icon><Star v-if="folder.icon === 'star'" /><Folder v-else /></el-icon>
          </div>
          <div class="folder-info">
            <div class="folder-name">{{ folder.name }}</div>
            <div class="folder-tags">{{ folder.tags || '无标签' }}</div>
          </div>
          <div class="folder-meta">
            <el-tag
              v-if="folder.schedule_enabled && folder.last_synced_id != null"
              type="info"
              size="small"
              effect="plain"
              class="cursor-badge"
              :title="`同步游标：上次实际处理到的图片 ID #${folder.last_synced_id}`"
            >
              <el-icon><Aim /></el-icon>
              #{{ folder.last_synced_id }}
            </el-tag>
            <el-tag
              v-if="folder.schedule_enabled"
              :type="scheduleStatusType(folder.last_schedule_status)"
              size="small"
              effect="light"
              class="schedule-badge"
            >
              <el-icon><Clock /></el-icon>
              {{ formatLastScheduled(folder.last_scheduled_at) }}
            </el-tag>
            <el-button
              v-if="folder.tags && folder.tags.trim()"
              link
              size="small"
              :loading="triggeringSet.has(folder.id)"
              class="folder-trigger-btn"
              :title="`立即执行：${folder.name}`"
              @click.stop="handleTrigger(folder)"
            >
              <el-icon><VideoPlay /></el-icon>
            </el-button>
            <span class="folder-count">
              {{ sourceMode === 'local' ? (folder.local_count || 0) : (folder.online_count || 0) }}
            </span>
          </div>
        </div>
        <div v-if="folders.length === 0" class="empty-state">
          <el-icon class="empty-icon"><FolderOpened /></el-icon>
          <div class="empty-text">暂无收藏夹</div>
        </div>
        <div v-else-if="filteredFolders.length === 0 && folderSearchKeyword" class="empty-state">
          <el-icon class="empty-icon"><Search /></el-icon>
          <div class="empty-text">无匹配收藏夹</div>
        </div>
      </div>
      <div v-if="folders.length > 0" class="tag-search-bar">
        <el-input
          v-model="folderSearchKeyword"
          placeholder="搜索收藏夹..."
          size="small"
          clearable
        >
          <template #prefix>
            <el-icon><Search /></el-icon>
          </template>
        </el-input>
      </div>
    </template>

    <div v-else class="inline-form">
      <div class="inline-form-header">
        <el-icon class="form-mode-icon"><Folder v-if="mode === 'create'" /><Edit v-else /></el-icon>
        <span class="form-mode-title">{{ mode === 'create' ? '新建收藏夹' : '编辑收藏夹' }}</span>
        <el-button text size="small" class="back-btn" @click="cancelForm">
          <el-icon><ArrowLeft /></el-icon> 返回
        </el-button>
      </div>
      <el-form :model="form" label-width="80px" class="form-body" size="small">
        <el-form-item label="名称">
          <el-input v-model="form.name" placeholder="收藏夹名称" maxlength="50" />
        </el-form-item>
        <el-form-item label="标签">
          <div class="tags-display">
            <template v-if="parsedFormTags.length">
              <el-tag
                v-for="tag in parsedFormTags"
                :key="tag"
                size="small"
                effect="plain"
                type="info"
                class="tag-chip"
              >
                {{ tag }}
              </el-tag>
            </template>
            <span v-else class="empty-tags">无标签</span>
          </div>
        </el-form-item>
        <el-form-item label="颜色">
          <div class="color-picker">
            <div
              v-for="color in colorOptions"
              :key="color"
              class="color-option"
              :class="{ active: form.color === color }"
              :style="{ backgroundColor: color }"
              @click="form.color = color"
            />
          </div>
        </el-form-item>
        <el-form-item label="定时任务">
          <el-switch
            v-model="form.schedule_enabled"
            active-text="启用"
            inactive-text="关闭"
          />
        </el-form-item>
        <template v-if="form.schedule_enabled">
          <el-form-item label="频率">
            <el-radio-group v-model="form.schedule_freq" size="small" class="freq-group">
              <el-radio value="daily">每天</el-radio>
              <el-radio value="weekly">每周</el-radio>
              <el-radio value="monthly">每月</el-radio>
              <el-radio value="custom">自定义</el-radio>
            </el-radio-group>
          </el-form-item>
          <el-form-item v-if="form.schedule_freq !== 'custom'" label="时间">
            <el-time-picker
              v-model="form.schedule_time"
              format="HH:mm"
              value-format="HH:mm"
              placeholder="选择时间"
              size="small"
              style="width: 100%"
            />
          </el-form-item>
          <el-form-item v-if="form.schedule_freq === 'weekly'" label="星期">
            <el-checkbox-group v-model="form.schedule_weekdays" size="small">
              <el-checkbox :value="1">一</el-checkbox>
              <el-checkbox :value="2">二</el-checkbox>
              <el-checkbox :value="3">三</el-checkbox>
              <el-checkbox :value="4">四</el-checkbox>
              <el-checkbox :value="5">五</el-checkbox>
              <el-checkbox :value="6">六</el-checkbox>
              <el-checkbox :value="0">日</el-checkbox>
            </el-checkbox-group>
          </el-form-item>
          <el-form-item v-if="form.schedule_freq === 'monthly'" label="日期">
            <el-input-number
              v-model="form.schedule_day"
              :min="1"
              :max="31"
              size="small"
              style="width: 100%"
            />
            <div class="form-tip">1-31 号</div>
          </el-form-item>
          <el-form-item v-if="form.schedule_freq === 'custom'" label="Cron">
            <el-input
              v-model="form.schedule_cron"
              placeholder="如 '0 3 * * *' 表示每天凌晨 3 点"
            />
            <div class="form-tip">
              5 字段：分 时 日 月 周 ·
              <a href="https://crontab.guru/" target="_blank" rel="noopener">语法参考</a>
            </div>
          </el-form-item>
          <el-form-item label="模式">
            <el-radio-group v-model="form.schedule_mode" size="small">
              <el-radio value="last_id">增量</el-radio>
              <el-radio value="max">最大</el-radio>
            </el-radio-group>
          </el-form-item>
<el-form-item label="单次上限">
            <el-input-number
              v-model="form.schedule_max_images"
              :min="1"
              :max="10000"
              placeholder="留空用全局默认"
              size="small"
              style="width: 100%"
            />
          </el-form-item>
          <el-form-item v-if="currentEditingFolder && currentEditingFolder.schedule_enabled" label="同步游标" class="sync-cursor-form-item">
            <div class="sync-cursor-row">
              <span class="sync-cursor-value">
                <template v-if="currentEditingFolder.last_synced_id != null">
                  上次同步至 <strong>#{{ currentEditingFolder.last_synced_id }}</strong>
                </template>
                <template v-else>
                  <em>未初始化</em>
                </template>
              </span>
              <el-popconfirm
                title="重置同步游标？下次调度将从头开始（增量模式回退到当前已下载位置，全量模式直接全量）。"
                confirm-button-text="重置"
                cancel-button-text="取消"
                @confirm="handleResetSync"
              >
                <template #reference>
                  <el-button size="small" type="warning" plain class="sync-cursor-reset">
                    <el-icon><RefreshRight /></el-icon> 重置游标
                  </el-button>
                </template>
              </el-popconfirm>
            </div>
          </el-form-item>
        </template>
      </el-form>
      <div class="inline-form-footer">
        <el-popconfirm
          v-if="mode === 'edit'"
          title="确定删除该收藏夹？"
          confirm-button-text="删除"
          cancel-button-text="取消"
          @confirm="handleDeleteConfirm"
        >
          <template #reference>
            <el-button size="small" type="danger" plain>
              <el-icon><Delete /></el-icon> 删除
            </el-button>
          </template>
        </el-popconfirm>
        <div class="footer-spacer" />
        <el-button size="small" @click="cancelForm">取消</el-button>
        <el-button size="small" type="primary" @click="handleSubmit">
          {{ mode === 'create' ? '创建' : '保存' }}
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { ArrowLeft, Clock, Delete, Edit, Folder, FolderOpened, RefreshRight, Search, Star, VideoPlay } from '@element-plus/icons-vue'
import { triggerFolderSchedule } from '@/api/favorites'

const props = defineProps({
  folders: { type: Array, required: true },
  colorOptions: { type: Array, required: true },
  sourceMode: { type: String, default: 'local' },
})

const emit = defineEmits(['select', 'longPress', 'create', 'update', 'delete', 'reset-sync', 'mode-change', 'triggered'])

const mode = ref('list')
const editingFolder = ref(null)

// 编辑模式：从 props.folders 派生最新的 folder 对象（按 id 匹配）。
// 这样父组件刷新 favoriteFolders 后，编辑面板上的 last_synced_id 等字段自动同步，
// 避免持久的旧引用导致"重置游标后仍显示未初始化"的问题。
const currentEditingFolder = computed(() => {
  if (!editingFolder.value) return null
  return props.folders.find(f => f.id === editingFolder.value.id) || editingFolder.value
})

// 通知父组件 mode 变化 (父组件用此隐藏 panel-header 等装饰性头部)
watch(mode, (newMode) => emit('mode-change', newMode), { immediate: true })

const form = reactive({
  name: '',
  tags: '',
  color: '#409EFF',
  schedule_enabled: false,
  schedule_freq: 'daily',
  schedule_time: '03:00',
  schedule_weekdays: [1, 2, 3, 4, 5],
  schedule_day: 1,
  schedule_cron: '',
  schedule_mode: 'last_id',
  schedule_max_images: null,
})

// 搜索状态
const folderSearchKeyword = ref('')

// 触发中状态：正在触发的 folder.id 集合（用于按钮 loading 防重复点击）
const triggeringSet = ref(new Set())

// 设备是否支持精细 hover（用于决定按钮是 hover 显示还是常驻）
const hasHover = ref(true)

// matchMedia 监听引用（用于 onUnmounted 清理）
let mqlRef = null
const onMqChange = (e) => { hasHover.value = e.matches }

const pad2 = (n) => String(n).padStart(2, '0')

const parsedFormTags = computed(() => {
  if (!form.tags) return []
  return form.tags.split(/\s+/).filter(Boolean)
})

const effectiveCron = computed(() => {
  const [hh = '0', mm = '0'] = (form.schedule_time || '00:00').split(':')
  const m = pad2(parseInt(mm, 10) || 0)
  const h = pad2(parseInt(hh, 10) || 0)
  if (form.schedule_freq === 'daily') return `${m} ${h} * * *`
  if (form.schedule_freq === 'weekly') {
    const days = (form.schedule_weekdays || []).slice().sort()
    return `${m} ${h} * * ${days.length ? days.join(',') : '*'}`
  }
  if (form.schedule_freq === 'monthly') {
    const d = Math.max(1, Math.min(31, parseInt(form.schedule_day, 10) || 1))
    return `${m} ${h} ${d} * *`
  }
  return form.schedule_cron || ''
})

const parseCron = (cron) => {
  if (!cron) {
    return { freq: 'daily', time: '03:00', weekdays: [1, 2, 3, 4, 5], day: 1, cron: '' }
  }
  const parts = cron.trim().split(/\s+/)
  if (parts.length !== 5) {
    return { freq: 'custom', time: '03:00', weekdays: [1, 2, 3, 4, 5], day: 1, cron }
  }
  const [mm, hh, dom, , dow] = parts
  const isStar = (s) => s === '*' || s === '?'
  const isWeekdayList = /^[0-6](,[0-6])*$/.test(dow)
  const isDomNum = /^[0-9]+$/.test(dom)
  const isDomList = /^[0-9]+(,[0-9]+)*$/.test(dom)

  let freq = 'custom'
  let weekdays = []
  let day = 1
  if (isStar(dom) && isStar(dow)) {
    freq = 'daily'
  } else if (isStar(dom) && isWeekdayList) {
    freq = 'weekly'
    weekdays = dow.split(',').map((s) => parseInt(s, 10))
  } else if ((isDomNum || isDomList) && isStar(dow)) {
    freq = 'monthly'
    day = parseInt(dom.split(',')[0], 10) || 1
  }

  return {
    freq,
    time: `${pad2(parseInt(hh, 10) || 0)}:${pad2(parseInt(mm, 10) || 0)}`,
    weekdays: weekdays.length ? weekdays : [1, 2, 3, 4, 5],
    day,
    cron,
  }
}

const LONG_PRESS_MS = 700
let pressTimer = null
let pressTarget = null
let pressMoved = false
let pressStartX = 0
let pressStartY = 0
const MOVE_THRESHOLD_PX = 10

const resetPressState = () => {
  if (pressTimer) {
    clearTimeout(pressTimer)
    pressTimer = null
  }
  pressTarget = null
  pressMoved = false
}

const handlePressStart = (folder, event) => {
  if (mode.value !== 'list') return
  resetPressState()
  pressTarget = folder
  pressMoved = false
  const point = event.touches ? event.touches[0] : event
  pressStartX = point.clientX
  pressStartY = point.clientY

  const onMove = (e) => {
    const p = e.touches ? e.touches[0] : e
    const dx = Math.abs(p.clientX - pressStartX)
    const dy = Math.abs(p.clientY - pressStartY)
    if (dx > MOVE_THRESHOLD_PX || dy > MOVE_THRESHOLD_PX) {
      pressMoved = true
      resetPressState()
      cleanup()
    }
  }
  const onUp = () => cleanup()

  const cleanup = () => {
    document.removeEventListener('mousemove', onMove)
    document.removeEventListener('mouseup', onUp)
    document.removeEventListener('touchmove', onMove)
    document.removeEventListener('touchend', onUp)
  }

  document.addEventListener('mousemove', onMove)
  document.addEventListener('mouseup', onUp)
  document.addEventListener('touchmove', onMove, { passive: true })
  document.addEventListener('touchend', onUp)

  pressTimer = setTimeout(() => {
    pressTimer = null
    if (pressTarget && !pressMoved) {
      emit('longPress', pressTarget)
    }
    cleanup()
  }, LONG_PRESS_MS)
}

const handlePressEnd = () => {
  if (pressTimer) {
    clearTimeout(pressTimer)
    pressTimer = null
  }
}

const handleSelect = (folder) => {
  if (pressMoved) return
  emit('select', folder)
}

const scheduleStatusType = (status) => ({
  success: 'success',
  failed: 'danger',
  running: 'warning',
}[status] || 'info')

const formatLastScheduled = (dt) => {
  if (!dt) return '未运行'
  const d = new Date(dt)
  const diffMs = Date.now() - d.getTime()
  if (diffMs < 60000) return '刚刚'
  if (diffMs < 3600000) return `${Math.floor(diffMs / 60000)} 分钟前`
  if (diffMs < 86400000) return `${Math.floor(diffMs / 3600000)} 小时前`
  return d.toLocaleDateString('zh-CN')
}

// 按 name / tags 过滤收藏夹（纯前端，零后端调用）
const filteredFolders = computed(() => {
  const kw = folderSearchKeyword.value.trim().toLowerCase()
  if (!kw) return props.folders
  return props.folders.filter(f =>
    (f.name || '').toLowerCase().includes(kw) ||
    (f.tags || '').toLowerCase().includes(kw)
  )
})

// 立即执行：手动触发指定 folder 的调度抓取
const handleTrigger = async (folder) => {
  if (triggeringSet.value.has(folder.id)) return  // 防重复点击
  triggeringSet.value.add(folder.id)
  try {
    await triggerFolderSchedule(folder.id)
    ElMessage.success(`后台更新中：${folder.name}`)
    emit('triggered', folder)
  } catch (e) {
    const msg = e?.response?.data?.message || e?.message || '未知错误'
    ElMessage.error(`触发失败：${msg}`)
  } finally {
    triggeringSet.value.delete(folder.id)
  }
}

// 设备能力检测：精细指针设备才支持 hover
onMounted(() => {
  mqlRef = window.matchMedia('(hover: hover) and (pointer: fine)')
  hasHover.value = mqlRef.matches
  mqlRef.addEventListener('change', onMqChange)
})

onUnmounted(() => {
  if (mqlRef) {
    mqlRef.removeEventListener('change', onMqChange)
    mqlRef = null
  }
})

const resetForm = () => {
  form.name = ''
  form.tags = ''
  form.color = '#409EFF'
  form.schedule_enabled = false
  form.schedule_freq = 'daily'
  form.schedule_time = '03:00'
  form.schedule_weekdays = [1, 2, 3, 4, 5]
  form.schedule_day = 1
  form.schedule_cron = ''
  form.schedule_mode = 'last_id'
  form.schedule_max_images = null
}

const openCreate = (payload = {}) => {
  resetForm()
  editingFolder.value = null
  form.tags = payload.tags || ''
  if (payload.name) form.name = payload.name
  if (payload.color) form.color = payload.color
  mode.value = 'create'
}

const openEdit = (folder) => {
  resetForm()
  editingFolder.value = folder
  form.name = folder.name
  form.tags = folder.tags || ''
  form.color = folder.color
  form.schedule_enabled = folder.schedule_enabled || false
  form.schedule_mode = folder.schedule_mode || 'last_id'
  form.schedule_max_images = folder.schedule_max_images
  const parsed = parseCron(folder.schedule_cron || '')
  form.schedule_freq = parsed.freq
  form.schedule_time = parsed.time
  form.schedule_weekdays = parsed.weekdays
  form.schedule_day = parsed.day
  form.schedule_cron = parsed.cron
  mode.value = 'edit'
}

const cancelForm = () => {
  mode.value = 'list'
  editingFolder.value = null
  resetForm()
}

const handleDeleteConfirm = () => {
  if (editingFolder.value) {
    emit('delete', editingFolder.value)
  }
  cancelForm()
}

const handleResetSync = () => {
  if (editingFolder.value) {
    emit('reset-sync', editingFolder.value)
  }
}

const handleSubmit = () => {
  if (!form.name.trim()) {
    ElMessage.warning('请输入收藏夹名称')
    return
  }
  const cronExpr = effectiveCron.value
  if (form.schedule_enabled && !cronExpr.trim()) {
    ElMessage.warning('启用调度时必须配置时间')
    return
  }
  const payload = {
    name: form.name.trim(),
    tags: form.tags,
    color: form.color,
    schedule_enabled: form.schedule_enabled,
    schedule_cron: cronExpr,
    schedule_mode: form.schedule_mode,
    schedule_max_images: form.schedule_max_images,
  }
  if (mode.value === 'create') {
    emit('create', payload)
  } else if (editingFolder.value) {
    emit('update', { id: editingFolder.value.id, ...payload })
  }
  mode.value = 'list'
}

defineExpose({ openCreate, openEdit, cancelForm })
</script>

<style scoped>
.favorite-panel {
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.folder-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 4px 0;
}

.folder-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  border-radius: 6px;
  cursor: pointer;
  user-select: none;
  -webkit-user-select: none;
  transition: background-color 0.15s;
}

.folder-item:hover {
  background: var(--bg-tertiary, rgba(0, 0, 0, 0.04));
}

.folder-icon {
  width: 28px;
  height: 28px;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  font-size: 14px;
  flex-shrink: 0;
}

.folder-info {
  flex: 1;
  min-width: 0;
}

.folder-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.folder-tags {
  font-size: 11px;
  color: var(--text-muted, #999);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-top: 1px;
}

.folder-meta {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}

.folder-count {
  font-size: 11px;
  color: var(--text-muted, #999);
}

/* 触发按钮：默认透明，hover 显示 */
.folder-trigger-btn {
  opacity: 0;
  transition: opacity 0.15s;
  padding: 2px 4px;
  margin: 0;
  flex-shrink: 0;
}
.folder-item:hover .folder-trigger-btn,
.folder-trigger-btn:focus,
.folder-trigger-btn.is-loading {
  opacity: 1;
}

/* 移动端常驻（hover: none 或粗指针设备） */
@media (hover: none), (pointer: coarse) {
  .folder-trigger-btn {
    opacity: 1;
  }
}

.schedule-badge {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  font-size: 10px;
  padding: 0 4px;
  height: 18px;
}

.cursor-badge {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  font-size: 10px;
  padding: 0 4px;
  height: 18px;
  font-family: ui-monospace, 'SF Mono', Menlo, monospace;
}

.sync-cursor-value {
  font-size: 12px;
  color: var(--text-secondary);
}

.sync-cursor-value strong {
  color: var(--el-color-primary);
  font-weight: 600;
}

.sync-cursor-value em {
  color: var(--text-muted, #999);
  font-style: italic;
}

/* el-form-item__content 默认是 display:flex，子项会按内容撑开，
   导致我们的 .sync-cursor-row 无法占满整个 content 区域宽度。
   强制改成 block，让 row 自身 width:100% 生效，从而 flex 布局能正确占满空间。 */
:deep(.sync-cursor-form-item .el-form-item__content) {
  display: block;
}

.sync-cursor-row {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
}

.sync-cursor-value {
  flex: 1 1 auto;
  min-width: 0;
}

.sync-cursor-reset {
  flex: 0 0 auto;
  margin-left: auto;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 32px 16px;
  color: var(--text-muted, #999);
}

.empty-icon {
  font-size: 36px;
  margin-bottom: 8px;
  opacity: 0.5;
}

.empty-text {
  font-size: 12px;
}

.inline-form {
  display: flex;
  flex-direction: column;
  padding: 8px 12px 12px;
  gap: 4px;
}

.inline-form-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 0 0 8px;
  border-bottom: 1px solid var(--border-color, #ebeef5);
  margin-bottom: 8px;
}

.form-mode-icon {
  font-size: 16px;
  color: var(--el-color-primary);
}

.form-mode-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  flex: 1;
}

.back-btn {
  font-size: 12px;
}

.form-body {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.form-body :deep(.el-form-item) {
  margin-bottom: 0;
}

.form-body :deep(.el-form-item__label) {
  font-size: 12px;
  padding-right: 8px;
  color: var(--text-secondary);
}

.color-picker {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.color-option {
  width: 22px;
  height: 22px;
  border-radius: 4px;
  cursor: pointer;
  border: 2px solid transparent;
  transition: transform 0.15s;
}

.color-option:hover {
  transform: scale(1.1);
}

.color-option.active {
  border-color: var(--text-primary);
  box-shadow: 0 0 0 2px var(--bg-primary, #fff);
}

.form-tip {
  font-size: 11px;
  color: var(--text-muted, #999);
  margin-top: 2px;
  line-height: 1.3;
}

.cron-preview {
  display: inline-block;
  padding: 2px 8px;
  font-size: 12px;
  font-family: ui-monospace, 'SF Mono', Menlo, monospace;
  background: var(--bg-tertiary, rgba(0, 0, 0, 0.05));
  border-radius: 4px;
  color: var(--el-color-primary);
}

.freq-group :deep(.el-radio) {
  margin-right: 8px;
}
.freq-group :deep(.el-radio:last-child) {
  margin-right: 0;
}

.tags-display {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  align-items: center;
  min-height: 24px;
}

.tag-chip {
  margin: 0;
  cursor: default;
}

.empty-tags {
  font-size: 12px;
  color: var(--text-muted, #999);
  font-style: italic;
}

.inline-form-footer {
  display: flex;
  align-items: center;
  gap: 8px;
  padding-top: 12px;
  margin-top: 8px;
  border-top: 1px solid var(--border-color, #ebeef5);
}

.footer-spacer {
  flex: 1;
}

/* 搜索栏：与 AdvancedQuery.vue 保持一致 */
.tag-search-bar {
  padding: 8px 12px;
  border-top: 1px solid var(--border-color);
}
.tag-search-bar .el-input {
  width: 100%;
}
</style>
