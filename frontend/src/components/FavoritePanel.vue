<template>
  <div class="favorite-panel">
    <div class="folder-list">
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

    <el-dialog
      v-model="dialogVisible"
      :title="dialogMode === 'create' ? '新建收藏夹' : '编辑收藏夹'"
      width="500px"
      destroy-on-close
      @close="handleDialogClose"
    >
      <el-form :model="form" label-width="80px">
        <el-form-item label="名称">
          <el-input v-model="form.name" placeholder="收藏夹名称" maxlength="50" />
        </el-form-item>
        <el-form-item label="标签">
          <el-input
            v-model="form.tags"
            :placeholder="dialogMode === 'create' ? '如：rating:s score:>100' : '收藏夹标签查询字符串'"
            type="textarea"
            :rows="3"
            :readonly="dialogMode === 'create' && !!initialTags"
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
          <el-form-item label="Cron 表达式">
            <el-input
              v-model="form.schedule_cron"
              placeholder="如 '0 3 * * *' 表示每天凌晨 3 点"
            />
            <div class="form-tip">
              5 字段格式：分 时 日 月 周
              <a href="https://crontab.guru/" target="_blank" rel="noopener">语法参考</a>
            </div>
          </el-form-item>
          <el-form-item label="拉取模式">
            <el-radio-group v-model="form.schedule_mode">
              <el-radio value="last_id">增量（仅新图）</el-radio>
              <el-radio value="max">最大（全部）</el-radio>
            </el-radio-group>
          </el-form-item>
          <el-form-item label="单次最大数">
            <el-input-number
              v-model="form.schedule_max_images"
              :min="1"
              :max="10000"
              placeholder="留空使用全局默认"
              style="width: 100%"
            />
          </el-form-item>
        </template>
      </el-form>
      <template #footer>
        <el-button
          v-if="dialogMode === 'edit'"
          type="danger"
          plain
          @click="handleDeleteClick"
        >
          删除
        </el-button>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSubmit">
          {{ dialogMode === 'create' ? '创建' : '保存' }}
        </el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="deleteConfirmVisible"
      title="删除收藏夹"
      width="360px"
      center
    >
      <div style="text-align: center; padding: 12px 0;">
        确定删除收藏夹「{{ deletingFolder?.name }}」？
      </div>
      <template #footer>
        <el-button @click="deleteConfirmVisible = false">取消</el-button>
        <el-button type="danger" @click="handleDeleteConfirm">删除</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Clock, Folder, FolderOpened, Star } from '@element-plus/icons-vue'

const props = defineProps({
  folders: { type: Array, required: true },
  colorOptions: { type: Array, required: true },
  sourceMode: { type: String, default: 'local' },
})

const emit = defineEmits(['select', 'longPress', 'create', 'update', 'delete'])

const dialogVisible = ref(false)
const dialogMode = ref('create')
const editingFolder = ref(null)
const deletingFolder = ref(null)
const deleteConfirmVisible = ref(false)
const initialTags = ref('')

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

const handlePressEnd = (folder) => {
  if (pressTimer) {
    clearTimeout(pressTimer)
    pressTimer = null
  }
}

const handleSelect = (folder) => {
  if (pressMoved) return
  emit('select', folder)
}

const scheduleStatusType = (status) => {
  return {
    success: 'success',
    failed: 'danger',
    running: 'warning',
  }[status] || 'info'
}

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
}

const openCreate = (payload = {}) => {
  dialogMode.value = 'create'
  editingFolder.value = null
  initialTags.value = payload.tags || ''
  resetForm()
  form.tags = payload.tags || ''
  if (payload.name) form.name = payload.name
  if (payload.color) form.color = payload.color
  dialogVisible.value = true
}

const openEdit = (folder) => {
  dialogMode.value = 'edit'
  editingFolder.value = folder
  form.name = folder.name
  form.tags = folder.tags || ''
  form.color = folder.color
  form.schedule_enabled = folder.schedule_enabled || false
  form.schedule_cron = folder.schedule_cron || ''
  form.schedule_mode = folder.schedule_mode || 'last_id'
  form.schedule_max_images = folder.schedule_max_images
  dialogVisible.value = true
}

const openDeleteConfirm = (folder) => {
  deletingFolder.value = folder
  deleteConfirmVisible.value = true
}

const handleDeleteClick = () => {
  if (editingFolder.value) {
    deleteConfirmVisible.value = false
    dialogVisible.value = false
    deletingFolder.value = editingFolder.value
    deleteConfirmVisible.value = true
  }
}

const handleDeleteConfirm = () => {
  if (deletingFolder.value) {
    emit('delete', deletingFolder.value)
  }
  deleteConfirmVisible.value = false
  deletingFolder.value = null
}

const handleDialogClose = () => {
  editingFolder.value = null
  resetForm()
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
  if (dialogMode.value === 'create') {
    emit('create', payload)
  } else if (editingFolder.value) {
    emit('update', { id: editingFolder.value.id, ...payload })
  }
  dialogVisible.value = false
}

defineExpose({ openCreate, openEdit, openDeleteConfirm })
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

.color-picker {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.color-option {
  width: 24px;
  height: 24px;
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
  margin-top: 4px;
  line-height: 1.4;
}
</style>
