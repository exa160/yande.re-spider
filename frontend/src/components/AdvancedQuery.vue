<template>
  <div class="advanced-query-container">
    <!-- 收缩状态：右下角圆形按钮 -->
    <div v-if="collapsed" class="collapsed-button" @click="expand">
      <el-icon :size="20"><Search /></el-icon>
    </div>

    <!-- 展开状态 -->
    <div v-else class="search-panel" :class="{ 'panel-expanded': showAdvanced }">
      <!-- 一级搜索栏 -->
      <div class="search-bar">
        <div class="search-input-wrapper">
          <el-icon class="search-icon"><Search /></el-icon>
          <el-input
            v-model="searchText"
            placeholder="输入标签搜索（用空格分隔，+tag包含 -tag排除）"
            clearable
            @keyup.enter="handleSearch"
          />
        </div>
        <div class="search-tags" v-if="activeFilters.length > 0">
          <el-tag
            v-for="filter in activeFilters"
            :key="filter.key"
            closable
            @close="removeFilter(filter)"
            size="small"
          >
            {{ filter.label }}
          </el-tag>
        </div>
        <div class="search-actions">
          <el-button circle size="small" @click="toggleAdvanced">
            <el-icon><Setting /></el-icon>
          </el-button>
          <el-button circle size="small" @click="collapse">
            <el-icon><Minus /></el-icon>
          </el-button>
        </div>
      </div>

      <!-- 高级筛选面板 -->
      <el-collapse-transition>
        <div v-if="showAdvanced" class="advanced-panel">
          <!-- 第一行：上传者、评分、格式 -->
          <div class="panel-row">
            <div class="row-item">
              <label>上传者</label>
              <el-input
                v-model="queryParams.author"
                placeholder="作者名称"
                size="small"
                clearable
              />
            </div>

            <div class="row-item">
              <label>评分</label>
              <div class="checkbox-group">
                <el-checkbox-button
                  v-for="opt in ratingOptions"
                  :key="opt.value"
                  :value="opt.value"
                  v-model="queryParams.rating"
                  :label="opt.label"
                />
              </div>
            </div>

            <div class="row-item">
              <label>格式</label>
              <div class="checkbox-group" v-if="sourceMode === 'local'">
                <el-checkbox-button
                  v-for="opt in fileTypeOptions"
                  :key="opt.value"
                  :value="opt.value"
                  v-model="queryParams.fileType"
                  :label="opt.label"
                />
              </div>
              <el-radio-group v-else v-model="queryParams.fileTypeSingle" class="radio-group">
                <el-radio-button
                  v-for="opt in fileTypeOptions"
                  :key="opt.value"
                  :value="opt.value"
                >
                  {{ opt.label }}
                </el-radio-button>
              </el-radio-group>
            </div>
          </div>

          <!-- 第二行：宽度、高度 -->
          <div class="panel-row">
            <div class="row-item range-item">
              <label>宽度</label>
              <div class="range-inputs">
                <el-input-number v-model="queryParams.minWidth" :min="0" size="small" placeholder="最小" />
                <span class="range-separator">-</span>
                <el-input-number v-model="queryParams.maxWidth" :min="0" size="small" placeholder="最大" />
              </div>
            </div>

            <div class="row-item range-item">
              <label>高度</label>
              <div class="range-inputs">
                <el-input-number v-model="queryParams.minHeight" :min="0" size="small" placeholder="最小" />
                <span class="range-separator">-</span>
                <el-input-number v-model="queryParams.maxHeight" :min="0" size="small" placeholder="最大" />
              </div>
            </div>

            <div class="row-item range-item">
              <label>文件大小</label>
              <div class="range-inputs">
                <el-input-number v-model="queryParams.minFileSize" :min="0" size="small" placeholder="最小" />
                <span class="range-separator">-</span>
                <el-input-number v-model="queryParams.maxFileSize" :min="0" size="small" placeholder="最大" />
              </div>
            </div>
          </div>

          <!-- 第三行：排序 -->
          <div class="panel-row">
            <div class="row-item">
              <label>排序</label>
              <div class="sort-selects">
                <el-select v-model="queryParams.sortBy" size="small">
                  <el-option label="创建时间" value="created_at" />
                  <el-option label="评分" value="rating" />
                  <el-option label="文件大小" value="file_size" />
                  <el-option label="宽度" value="width" />
                  <el-option label="高度" value="height" />
                </el-select>
                <el-select v-model="queryParams.sortOrder" size="small">
                  <el-option label="降序" value="desc" />
                  <el-option label="升序" value="asc" />
                </el-select>
              </div>
            </div>
          </div>

          <!-- 底部按钮 -->
          <div class="panel-footer">
            <el-button size="small" @click="resetParams">重置</el-button>
            <el-button type="primary" size="small" @click="applyAndSearch">应用</el-button>
          </div>
        </div>
      </el-collapse-transition>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed } from 'vue'
import { Search, Setting, Minus } from '@element-plus/icons-vue'

const props = defineProps({
  sourceMode: {
    type: String,
    default: 'local'
  }
})

const emit = defineEmits(['search'])

// 状态
const collapsed = ref(false)
const showAdvanced = ref(false)
const searchText = ref('')

// 选项配置
const ratingOptions = [
  { label: 'Safe', value: 's' },
  { label: 'Questionable', value: 'q' },
  { label: 'Explicit', value: 'e' },
]

const fileTypeOptions = [
  { label: 'JPG', value: 'jpg' },
  { label: 'PNG', value: 'png' },
  { label: 'GIF', value: 'gif' },
  { label: 'WEBP', value: 'webp' },
]

// 查询参数
const queryParams = reactive({
  author: '',
  rating: [],
  fileType: [],
  fileTypeSingle: '',
  minWidth: null,
  maxWidth: null,
  minHeight: null,
  maxHeight: null,
  minFileSize: null,
  maxFileSize: null,
  minScore: null,
  maxScore: null,
  sortBy: 'created_at',
  sortOrder: 'desc',
})

// 计算激活的筛选标签
const activeFilters = computed(() => {
  const filters = []

  if (queryParams.author) {
    filters.push({ key: 'author', label: `上传者:${queryParams.author}` })
  }

  if (queryParams.rating.length > 0) {
    filters.push({ key: 'rating', label: `评分:${queryParams.rating.join(',')}` })
  }

  if (queryParams.fileType.length > 0) {
    filters.push({ key: 'fileType', label: `格式:${queryParams.fileType.join(',')}` })
  }

  if (queryParams.fileTypeSingle) {
    filters.push({ key: 'fileTypeSingle', label: `格式:${queryParams.fileTypeSingle}` })
  }

  if (queryParams.minWidth || queryParams.maxWidth) {
    const min = queryParams.minWidth || 0
    const max = queryParams.maxWidth || '∞'
    filters.push({ key: 'width', label: `宽度:${min}-${max}` })
  }

  if (queryParams.minHeight || queryParams.maxHeight) {
    const min = queryParams.minHeight || 0
    const max = queryParams.maxHeight || '∞'
    filters.push({ key: 'height', label: `高度:${min}-${max}` })
  }

  if (queryParams.minFileSize || queryParams.maxFileSize) {
    const min = queryParams.minFileSize || 0
    const max = queryParams.maxFileSize || '∞'
    filters.push({ key: 'fileSize', label: `大小:${min}-${max}KB` })
  }

  return filters
})

// 移除筛选标签
const removeFilter = (filter) => {
  switch (filter.key) {
    case 'author':
      queryParams.author = ''
      break
    case 'rating':
      queryParams.rating = []
      break
    case 'fileType':
      queryParams.fileType = []
      break
    case 'fileTypeSingle':
      queryParams.fileTypeSingle = ''
      break
    case 'width':
      queryParams.minWidth = null
      queryParams.maxWidth = null
      break
    case 'height':
      queryParams.minHeight = null
      queryParams.maxHeight = null
      break
    case 'fileSize':
      queryParams.minFileSize = null
      queryParams.maxFileSize = null
      break
  }
}

// 收缩/展开
const collapse = () => {
  collapsed.value = true
  showAdvanced.value = false
}

const expand = () => {
  collapsed.value = false
}

// 切换高级面板
const toggleAdvanced = () => {
  showAdvanced.value = !showAdvanced.value
}

// 重置参数
const resetParams = () => {
  queryParams.author = ''
  queryParams.rating = []
  queryParams.fileType = []
  queryParams.fileTypeSingle = ''
  queryParams.minWidth = null
  queryParams.maxWidth = null
  queryParams.minHeight = null
  queryParams.maxHeight = null
  queryParams.minFileSize = null
  queryParams.maxFileSize = null
  queryParams.minScore = null
  queryParams.maxScore = null
  queryParams.sortBy = 'created_at'
  queryParams.sortOrder = 'desc'
}

// 解析标签文本中的包含/排除
const parseTags = (text) => {
  const include = []
  const exclude = []

  if (!text) return { include, exclude }

  text.split(/\s+/).forEach(tag => {
    if (!tag) return
    if (tag.startsWith('-')) {
      const t = tag.substring(1)
      if (t) exclude.push(t)
    } else if (tag.startsWith('+')) {
      const t = tag.substring(1)
      if (t) include.push(t)
    } else {
      include.push(tag)
    }
  })

  return { include, exclude }
}

// 构建搜索参数字符串（用于本地模式）
const buildLocalParams = () => {
  const { include, exclude } = parseTags(searchText.value)

  const tagsParts = [...include]
  exclude.forEach(tag => {
    if (tag) tagsParts.push(`-${tag}`)
  })

  return {
    tags: tagsParts.join(' '),
    author: queryParams.author || undefined,
    ratings: queryParams.rating.length > 0 ? queryParams.rating : undefined,
    file_types: queryParams.fileType.length > 0 ? queryParams.fileType : undefined,
    min_width: queryParams.minWidth || undefined,
    max_width: queryParams.maxWidth || undefined,
    min_height: queryParams.minHeight || undefined,
    max_height: queryParams.maxHeight || undefined,
    min_file_size: queryParams.minFileSize || undefined,
    max_file_size: queryParams.maxFileSize || undefined,
    sort_by: queryParams.sortBy,
    sort_order: queryParams.sortOrder,
    page: 1,
    page_size: 20,
  }
}

// 构建在线模式搜索参数（后端 search_trans 转换）
const buildOnlineParams = () => {
  const { include, exclude } = parseTags(searchText.value)
  const tagsParts = [...include]

  exclude.forEach(tag => {
    if (tag) tagsParts.push(`-${tag}`)
  })

  return {
    tags: tagsParts.join(' '),
    author: queryParams.author || undefined,
    ratings: queryParams.rating,
    file_types: queryParams.fileTypeSingle ? [queryParams.fileTypeSingle] : undefined,
    min_width: queryParams.minWidth || undefined,
    max_width: queryParams.maxWidth || undefined,
    min_height: queryParams.minHeight || undefined,
    max_height: queryParams.maxHeight || undefined,
    min_file_size: queryParams.minFileSize || undefined,
    max_file_size: queryParams.maxFileSize || undefined,
    min_score: queryParams.minScore || undefined,
    max_score: queryParams.maxScore || undefined,
    order: queryParams.sortBy === 'created_at' ? 'date' : queryParams.sortBy,
    sort_order: queryParams.sortOrder,
    page: 1,
    page_size: 20,
  }
}

// 执行搜索
const handleSearch = () => {
  const mode = props.sourceMode || 'local'
  const params = mode === 'local' ? buildLocalParams() : buildOnlineParams()
  emit('search', { mode, params })
}

// 应用并搜索
const applyAndSearch = () => {
  showAdvanced.value = false
  handleSearch()
}

// 暴露方法供父组件调用
defineExpose({
  reset: () => {
    searchText.value = ''
    resetParams()
    showAdvanced.value = false
  }
})
</script>

<style scoped>
.advanced-query-container {
  position: fixed;
  bottom: 20px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 1000;
  width: 90%;
  max-width: 900px;
}

/* 收缩状态按钮 */
.collapsed-button {
  width: 48px;
  height: 48px;
  border-radius: 50%;
  background: var(--bg-secondary);
  backdrop-filter: blur(30px);
  border: 1px solid var(--border-color);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: var(--text-primary);
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.2);
  transition: all 0.2s ease;
}

.collapsed-button:hover {
  background: var(--bg-primary);
  transform: scale(1.05);
}

/* 搜索面板 */
.search-panel {
  background: var(--bg-secondary);
  backdrop-filter: blur(30px);
  border: 1px solid var(--border-color);
  border-radius: 12px;
  padding: 12px 16px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.15);
  transition: all 0.3s ease;
}

/* 一级搜索栏 */
.search-bar {
  display: flex;
  align-items: center;
  gap: 12px;
}

.search-input-wrapper {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 8px;
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  border-radius: 8px;
  padding: 0 12px;
}

.search-input-wrapper :deep(.el-input__wrapper) {
  background: transparent;
  box-shadow: none;
  padding: 0;
}

.search-input-wrapper :deep(.el-input__inner) {
  color: var(--text-primary);
}

.search-input-wrapper :deep(.el-input__inner::placeholder) {
  color: var(--text-muted);
}

.search-icon {
  color: var(--text-muted);
  flex-shrink: 0;
}

.search-tags {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.search-tags :deep(.el-tag) {
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  color: var(--text-secondary);
}

.search-actions {
  display: flex;
  gap: 8px;
}

.search-actions :deep(.el-button) {
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  color: var(--text-primary);
}

.search-actions :deep(.el-button:hover) {
  background: var(--bg-tertiary);
  border-color: #409EFF;
  color: #409EFF;
}

/* 高级筛选面板 */
.advanced-panel {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid var(--border-color);
}

.panel-row {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  margin-bottom: 16px;
}

.panel-row:last-of-type {
  margin-bottom: 12px;
}

.row-item {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  min-width: 150px;
}

.row-item label {
  color: var(--text-secondary);
  font-size: 13px;
  white-space: nowrap;
  min-width: 50px;
}

.range-item {
  flex: 2;
  min-width: 280px;
}

.range-inputs {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
}

.range-separator {
  color: var(--text-muted);
}

.checkbox-group {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.sort-selects {
  display: flex;
  gap: 8px;
}

.sort-selects .el-select {
  width: 120px;
}

/* 输入框样式 */
.row-item :deep(.el-input__wrapper) {
  background: var(--bg-primary);
  box-shadow: none;
  border: 1px solid var(--border-color);
}

.row-item :deep(.el-input__inner) {
  color: var(--text-primary);
}

.row-item :deep(.el-input-number) {
  width: 90px;
}

.row-item :deep(.el-input-number .el-input__wrapper) {
  background: var(--bg-primary);
  box-shadow: none;
  border: 1px solid var(--border-color);
}

.row-item :deep(.el-select .el-input__wrapper) {
  background: var(--bg-primary);
  box-shadow: none;
  border: 1px solid var(--border-color);
}

.row-item :deep(.el-checkbox-button__inner) {
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  color: var(--text-secondary);
  padding: 4px 10px;
  font-size: 12px;
}

.row-item :deep(.el-checkbox-button.is-checked .el-checkbox-button__inner) {
  background: #409EFF;
  border-color: #409EFF;
  color: white;
}

.row-item :deep(.el-radio-button__inner) {
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  color: var(--text-secondary);
  padding: 4px 10px;
  font-size: 12px;
}

.row-item :deep(.el-radio-button.is-active .el-radio-button__inner) {
  background: #409EFF;
  border-color: #409EFF;
  color: white;
}

.row-item :deep(.el-radio-button:first-child .el-radio-button__inner) {
  border-radius: 4px 0 0 4px;
}

.row-item :deep(.el-radio-button:last-child .el-radio-button__inner) {
  border-radius: 0 4px 4px 0;
}

.radio-group {
  display: flex;
}

/* 面板底部 */
.panel-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--border-color);
}

.panel-footer :deep(.el-button) {
  background: var(--bg-primary);
  border: 1px solid var(--border-color);
  color: var(--text-primary);
}

.panel-footer :deep(.el-button--primary) {
  background: #409EFF;
  border-color: #409EFF;
  color: white;
}

.panel-footer :deep(.el-button--primary:hover) {
  background: #66b1ff;
  border-color: #66b1ff;
}
</style>
