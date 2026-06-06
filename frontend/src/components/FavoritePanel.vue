<template>
  <div class="favorite-panel">
    <div v-if="mode === 'list'" class="folder-list">
      <div
        v-for="folder in folders"
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
          <span class="folder-count">
            {{ sourceMode === 'local' ? (folder.local_count || 0) : (folder.online_count || 0) }}
          </span>
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
        </div>
      </div>
      <div v-if="folders.length === 0" class="empty-state">
        <el-icon class="empty-icon"><FolderOpened /></el-icon>
        <div class="empty-text">暂无收藏夹</div>
      </div>
    </div>

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
          <el-input
            v-model="form.tags"
            :placeholder="mode === 'create' ? '如：rating:s score:>100' : '收藏夹标签查询字符串'"
            type="textarea"
            :rows="2"
            :readonly="mode === 'create' && hasInitialTags"
          />
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
          <el-form-item label="Cron">
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
            />
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
import { reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { ArrowLeft, Clock, Delete, Edit, Folder, FolderOpened, Star } from '@element-plus/icons-vue'

const props = defineProps({
  folders: { type: Array, required: true },
  colorOptions: { type: Array, required: true },
  sourceMode: { type: String, default: 'local' },
})

const emit = defineEmits(['select', 'longPress', 'create', 'update', 'delete'])

const mode = ref('list')
const editingFolder = ref(null)
const hasInitialTags = ref(false)

const form = reactive({
  name: '',
  tags: '',
  color: '#409EFF',
  schedule_enabled: false,
  schedule_cron: '',
  schedule_mode: 'last_id',
  schedule_max_images: null,
})

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

const resetForm = () => {
  form.name = ''
  form.tags = ''
  form.color = '#409EFF'
  form.schedule_enabled = false
  form.schedule_cron = ''
  form.schedule_mode = 'last_id'
  form.schedule_max_images = null
  hasInitialTags.value = false
}

const openCreate = (payload = {}) => {
  resetForm()
  editingFolder.value = null
  hasInitialTags.value = !!payload.tags
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
  form.schedule_cron = folder.schedule_cron || ''
  form.schedule_mode = folder.schedule_mode || 'last_id'
  form.schedule_max_images = folder.schedule_max_images
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

const handleSubmit = () => {
  if (!form.name.trim()) {
    ElMessage.warning('请输入收藏夹名称')
    return
  }
  if (form.schedule_enabled && !form.schedule_cron.trim()) {
    ElMessage.warning('启用调度时必须填写 Cron 表达式')
    return
  }
  const payload = {
    name: form.name.trim(),
    tags: form.tags,
    color: form.color,
    schedule_enabled: form.schedule_enabled,
    schedule_cron: form.schedule_cron,
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

.schedule-badge {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  font-size: 10px;
  padding: 0 4px;
  height: 18px;
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
</style>
