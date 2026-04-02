<template>
  <div class="download-page">
    <!-- 工具栏 -->
    <div class="toolbar">
      <span class="title">下载任务</span>
      <el-button type="primary" size="small" @click="loadTasks">
        <el-icon><Refresh /></el-icon>
        刷新
      </el-button>
    </div>

    <!-- 任务列表 -->
    <el-table :data="tasks" style="width: 100%" v-loading="loading" size="small">
      <el-table-column prop="image_id" label="图片ID" width="100" />
      <el-table-column prop="file_name" label="文件名" show-overflow-tooltip />
      <el-table-column prop="status" label="状态" width="90">
        <template #default="{ row }">
          <el-tag :type="getStatusType(row.status)" size="small">
            {{ row.status }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="progress" label="进度" width="140">
        <template #default="{ row }">
          <el-progress
            :percentage="Math.round(row.progress * 100)"
            :status="getProgressStatus(row.status)"
            :stroke-width="8"
          />
        </template>
      </el-table-column>
      <el-table-column label="大小" width="120">
        <template #default="{ row }">
          {{ formatFileSize(row.downloaded_size) }} / {{ row.total_size ? formatFileSize(row.total_size) : '-' }}
        </template>
      </el-table-column>
      <el-table-column label="操作" width="150" fixed="right">
        <template #default="{ row }">
          <el-button
            v-if="row.status === 'pending'"
            type="primary"
            size="small"
            link
            @click="startTask(row.task_id)"
          >
            启动
          </el-button>
          <el-button
            v-if="row.status === 'downloading'"
            type="warning"
            size="small"
            link
            @click="pauseTask(row.task_id)"
          >
            暂停
          </el-button>
          <el-button
            v-if="row.status === 'paused'"
            type="success"
            size="small"
            link
            @click="resumeTask(row.task_id)"
          >
            恢复
          </el-button>
          <el-button
            type="danger"
            size="small"
            link
            @click="deleteTask(row.task_id)"
          >
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 分页 -->
    <el-pagination
      v-model:current-page="currentPage"
      :page-size="pageSize"
      :total="total"
      layout="total, prev, pager, next"
      style="margin-top: 15px;"
      @current-change="loadTasks"
    />
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import api from '@/api'

const tasks = ref([])
const loading = ref(false)
const currentPage = ref(1)
const pageSize = ref(20)
const total = ref(0)

let pollTimer = null

const hasActiveTasks = computed(() => {
  return tasks.value.some(t => 
    ['downloading', 'pending', 'paused'].includes(t.status)
  )
})

const startPolling = () => {
  if (pollTimer) return
  pollTimer = setInterval(() => {
    loadTasks(false)
  }, 2000)
}

const stopPolling = () => {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

const loadTasks = async (showLoading = true) => {
  if (showLoading) {
    loading.value = true
  }
  try {
    const response = await api.get('/download/tasks', {
      params: {
        page: currentPage.value,
        page_size: pageSize.value
      }
    })
    tasks.value = response.tasks || []
    total.value = response.total || 0
    
    if (hasActiveTasks.value) {
      startPolling()
    } else {
      stopPolling()
    }
  } catch (error) {
    ElMessage.error('加载任务列表失败')
  } finally {
    if (showLoading) {
      loading.value = false
    }
  }
}

const startTask = async (taskId) => {
  try {
    await api.post(`/download/task/${taskId}/start`)
    ElMessage.success('任务已启动')
    await loadTasks()
  } catch (error) {
    ElMessage.error('启动任务失败')
  }
}

const pauseTask = async (taskId) => {
  try {
    await api.post(`/download/task/${taskId}/pause`)
    ElMessage.success('任务已暂停')
    await loadTasks()
  } catch (error) {
    ElMessage.error('暂停任务失败')
  }
}

const resumeTask = async (taskId) => {
  try {
    await api.post(`/download/task/${taskId}/resume`)
    ElMessage.success('任务已恢复')
    await loadTasks()
  } catch (error) {
    ElMessage.error('恢复任务失败')
  }
}

const cancelTask = async (taskId) => {
  try {
    await ElMessageBox.confirm('确定要取消该任务吗？', '提示', {
      type: 'warning'
    })
    await api.post(`/download/task/${taskId}/cancel`)
    ElMessage.success('任务已取消')
    await loadTasks()
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('取消任务失败')
    }
  }
}

const deleteTask = async (taskId) => {
  try {
    await ElMessageBox.confirm('确定要删除该任务吗？', '提示', {
      type: 'warning'
    })
    await api.delete(`/download/task/${taskId}`)
    ElMessage.success('任务已删除')
    await loadTasks()
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('删除任务失败')
    }
  }
}

const getStatusType = (status) => {
  const types = {
    'pending': 'info',
    'downloading': 'primary',
    'paused': 'warning',
    'completed': 'success',
    'failed': 'danger',
    'cancelled': 'info'
  }
  return types[status] || 'info'
}

const getProgressStatus = (status) => {
  if (status === 'completed') return 'success'
  if (status === 'failed') return 'exception'
  return null
}

const formatFileSize = (bytes) => {
  if (!bytes) return '0 B'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(2)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(2)} MB`
  return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`
}

onMounted(() => {
  loadTasks()
})

onUnmounted(() => {
  stopPolling()
})
</script>

<style scoped>
.download-page {
  padding: 15px;
}

.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 15px;
}

.title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

:deep(.el-table) {
  border-radius: 8px;
  overflow: hidden;
}

:deep(.el-progress__text) {
  font-size: 11px !important;
}
</style>
