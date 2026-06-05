<template>
  <div class="favorite-panel">
    <!-- 收藏夹列表 -->
    <div class="folder-list">
      <div class="folder-list-header">
        <span class="folder-list-title">我的收藏</span>
        <el-button type="primary" size="small" circle @click="handleCreate" class="add-btn">
          <el-icon><Plus /></el-icon>
        </el-button>
      </div>
      
      <div class="folder-items">
        <div
          v-for="folder in folders"
          :key="folder.id"
          class="folder-item"
          :class="{ active: selectedFolder?.id === folder.id }"
          @click="handleSelect(folder)"
        >
          <div class="folder-icon" :style="{ backgroundColor: folder.color }">
            <el-icon><Folder /></el-icon>
          </div>
          <div class="folder-info">
            <div class="folder-name">{{ folder.name }}</div>
            <div class="folder-meta">
              <span class="folder-count">{{ folder.local_count || 0 }} 张</span>
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
          <div class="folder-actions">
            <el-button
              size="small"
              circle
              @click.stop="handleEdit(folder)"
              class="action-btn"
            >
              <el-icon><Edit /></el-icon>
            </el-button>
            <el-button
              size="small"
              circle
              @click.stop="handleDelete(folder)"
              class="action-btn delete-btn"
            >
              <el-icon><Delete /></el-icon>
            </el-button>
          </div>
        </div>
      </div>

      <div v-if="folders.length === 0" class="empty-state">
        <el-icon class="empty-icon"><FolderOpened /></el-icon>
        <div class="empty-text">暂无收藏夹</div>
        <el-button type="primary" size="small" @click="handleCreate">
          创建第一个收藏夹
        </el-button>
      </div>
    </div>

    <!-- 新建/编辑弹窗 -->
    <el-dialog
      v-model="dialogVisible"
      :title="isEdit ? '编辑收藏夹' : '新建收藏夹'"
      width="500px"
      class="center-dialog"
    >
      <el-form :model="form" label-width="80px" class="folder-form">
        <el-form-item label="名称">
          <el-input v-model="form.name" placeholder="收藏夹名称" maxlength="50" />
        </el-form-item>

        <el-form-item label="标签">
          <el-input
            v-model="form.tags"
            placeholder="rating:s score:>100 order:score"
            type="textarea"
            :rows="3"
          />
          <div class="form-tip">
            支持高级搜索语法，如 rating:s score:>100 width:>=1000 ext:png
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

        <el-form-item label="图标">
          <el-select v-model="form.icon" placeholder="选择图标" style="width: 100%">
            <el-option value="folder" label="文件夹">
              <el-icon><Folder /></el-icon> 文件夹
            </el-option>
            <el-option value="star" label="星标">
              <el-icon><Star /></el-icon> 星标
            </el-option>
            <el-option value="Present" label="礼物">
              <el-icon><Present /></el-icon> 礼物
            </el-option>
            <el-option value="Collection" label="收藏">
              <el-icon><Collection /></el-icon> 收藏
            </el-option>
          </el-select>
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
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSubmit">
          {{ isEdit ? '保存' : '创建' }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Folder, Edit, Delete, FolderOpened, Star, Collection, Present, Clock } from '@element-plus/icons-vue'
import { getAllFolders, createFolder, updateFolder, deleteFolder } from '@/api/favorites'

const emit = defineEmits(['select', 'create'])

const folders = ref([])
const selectedFolder = ref(null)
const dialogVisible = ref(false)
const isEdit = ref(false)
const editingId = ref(null)

const form = ref({
  name: '',
  tags: '',
  color: '#409EFF',
  icon: 'folder',
  sort_order: 0,
  schedule_enabled: false,
  schedule_cron: '',
  schedule_mode: 'last_id',
  schedule_max_images: null,
})

const colorOptions = [
  '#409EFF', // 蓝色
  '#67C23A', // 绿色
  '#E6A23C', // 橙色
  '#F56C6C', // 红色
  '#909399', // 灰色
  '#BD35EF', // 紫色
  '#00BCD4', // 青色
  '#FF69B4', // 粉色
]

const loadFolders = async () => {
  try {
    const response = await getAllFolders()
    folders.value = response.data || []
  } catch (error) {
    ElMessage.error('加载收藏夹失败')
  }
}

const handleSelect = (folder) => {
  selectedFolder.value = folder
  emit('select', folder)
}

const handleCreate = () => {
  isEdit.value = false
  editingId.value = null
  form.value = {
    name: '',
    tags: '',
    color: '#409EFF',
    icon: 'folder',
    sort_order: folders.value.length,
    schedule_enabled: false,
    schedule_cron: '',
    schedule_mode: 'last_id',
    schedule_max_images: null,
  }
  dialogVisible.value = true
}

const handleEdit = (folder) => {
  isEdit.value = true
  editingId.value = folder.id
  form.value = {
    name: folder.name,
    tags: folder.tags,
    color: folder.color,
    icon: folder.icon,
    sort_order: folder.sort_order,
    schedule_enabled: folder.schedule_enabled || false,
    schedule_cron: folder.schedule_cron || '',
    schedule_mode: folder.schedule_mode || 'last_id',
    schedule_max_images: folder.schedule_max_images,
  }
  dialogVisible.value = true
}

const handleDelete = async (folder) => {
  try {
    await ElMessageBox.confirm(
      `确定删除收藏夹「${folder.name}」吗？`,
      '删除确认',
      {
        confirmButtonText: '删除',
        cancelButtonText: '取消',
        type: 'warning',
      }
    )
    await deleteFolder(folder.id)
    ElMessage.success('删除成功')
    if (selectedFolder.value?.id === folder.id) {
      selectedFolder.value = null
    }
    await loadFolders()
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('删除失败')
    }
  }
}

const handleSubmit = async () => {
  if (!form.value.name.trim()) {
    ElMessage.warning('请输入收藏夹名称')
    return
  }

  try {
    if (isEdit.value) {
      await updateFolder(editingId.value, form.value)
      ElMessage.success('保存成功')
    } else {
      await createFolder(form.value)
      ElMessage.success('创建成功')
    }
    dialogVisible.value = false
    await loadFolders()
    emit('create', form.value)
  } catch (error) {
    ElMessage.error(isEdit.value ? '保存失败' : '创建失败')
  }
}

onMounted(() => {
  loadFolders()
})

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

const openDialog = (prefill = {}) => {
  isEdit.value = false
  editingId.value = null
  form.value = {
    name: prefill.name || '',
    tags: prefill.tags || '',
    color: prefill.color || '#409EFF',
    icon: prefill.icon || 'folder',
    sort_order: folders.value.length,
    schedule_enabled: prefill.schedule_enabled ?? false,
    schedule_cron: prefill.schedule_cron || '',
    schedule_mode: prefill.schedule_mode || 'last_id',
    schedule_max_images: prefill.schedule_max_images ?? null,
  }
  dialogVisible.value = true
}

defineExpose({
  loadFolders,
  selectedFolder,
  openDialog,
})
</script>

<style scoped>
.favorite-panel {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.folder-list {
  flex: 1;
  overflow-y: auto;
}

.folder-list-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border-color);
}

.folder-list-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.add-btn {
  width: 28px;
  height: 28px;
}

.folder-items {
  padding: 8px;
}

.folder-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  border-radius: 8px;
  cursor: pointer;
  transition: background-color 0.2s;
}

.folder-item:hover {
  background: var(--bg-tertiary);
}

.folder-item.active {
  background: var(--bg-tertiary);
  box-shadow: inset 3px 0 0 var(--el-color-primary);
}

.folder-icon {
  width: 36px;
  height: 36px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  font-size: 18px;
  flex-shrink: 0;
}

.folder-info {
  flex: 1;
  min-width: 0;
}

.folder-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.folder-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 2px;
}

.folder-count {
  font-size: 12px;
  color: var(--text-muted);
}

.folder-actions {
  display: flex;
  gap: 4px;
  opacity: 0;
  transition: opacity 0.2s;
}

.folder-item:hover .folder-actions {
  opacity: 1;
}

.folder-actions .action-btn {
  width: 26px;
  height: 26px;
  background: transparent;
  border: none;
  color: var(--text-secondary);
}

.folder-actions .action-btn:hover {
  background: var(--bg-secondary);
  color: var(--el-color-primary);
}

.folder-actions .delete-btn:hover {
  color: var(--el-color-danger);
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px 20px;
  color: var(--text-muted);
}

.empty-icon {
  font-size: 48px;
  margin-bottom: 12px;
  opacity: 0.5;
}

.empty-text {
  font-size: 14px;
  margin-bottom: 16px;
}

.folder-form {
  padding: 10px 0;
}

.form-tip {
  font-size: 12px;
  color: var(--text-muted);
  margin-top: 4px;
  line-height: 1.4;
}

.color-picker {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.color-option {
  width: 28px;
  height: 28px;
  border-radius: 6px;
  cursor: pointer;
  border: 2px solid transparent;
  transition: all 0.2s;
}

.color-option:hover {
  transform: scale(1.1);
}

.color-option.active {
  border-color: var(--text-primary);
  box-shadow: 0 0 0 2px var(--bg-primary);
}

.schedule-badge {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  font-size: 11px;
}
</style>
