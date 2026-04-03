<template>
  <div class="advanced-query-container">
    <!-- 收缩状态：展开的搜索栏 -->
    <div v-if="collapsed" class="collapsed-search-bar">
      <div class="search-input-wrapper">
        <el-icon class="search-icon"><Search /></el-icon>
        <el-input
          v-model="searchText"
          placeholder="输入标签搜索..."
          clearable
          @keyup.enter="handleSearch"
        />
      </div>
      <el-button type="primary" @click="handleSearch" class="search-btn">搜索</el-button>
      <el-button circle @click="expand" class="expand-btn">
        <el-icon><Setting /></el-icon>
      </el-button>
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
              <div class="checkbox-group">
                <el-checkbox-button
                  v-for="opt in fileTypeOptions"
                  :key="opt.value"
                  :value="opt.value"
                  v-model="queryParams.fileType"
                  :label="opt.label"
                />
              </div>
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
  minWidth: null,
  maxWidth: null,
  minHeight: null,
  maxHeight: null,
  minFileSize: null,
  maxFileSize: null,
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
  queryParams.minWidth = null
  queryParams.maxWidth = null
  queryParams.minHeight = null
  queryParams.maxHeight = null
  queryParams.minFileSize = null
  queryParams.maxFileSize = null
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
    rating: queryParams.rating.length > 0 ? queryParams.rating.join(',') : undefined,
    file_type: queryParams.fileType.length > 0 ? queryParams.fileType.join(',') : undefined,
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

// 构建在线模式搜索参数字符串
const buildOnlineParams = () => {
  const { include, exclude } = parseTags(searchText.value)
  const tagsParts = [...include]

  // 评分多选：只选一个时用 rating:xxx，只选两个时用排除语法
  if (queryParams.rating.length === 1) {
    tagsParts.push(`rating:${queryParams.rating[0]}`)
  } else if (queryParams.rating.length === 2) {
    const allRatings = ['s', 'q', 'e']
    const excludeRatings = allRatings.filter(r => !queryParams.rating.includes(r))
    excludeRatings.forEach(r => tagsParts.push(`-${r}`))
  }

  // 格式多选用 OR 语法
  if (queryParams.fileType.length > 0) {
    if (queryParams.fileType.length === 1) {
      tagsParts.push(`ext:${queryParams.fileType[0]}`)
    } else {
      tagsParts.push(`(${queryParams.fileType.map(t => `ext:${t}`).join(' OR ')})`)
    }
  }

  // 排除的标签
  exclude.forEach(tag => {
    if (tag) tagsParts.push(`-${tag}`)
  })

  // 宽度
  if (queryParams.minWidth != null) {
    tagsParts.push(`width:>=${queryParams.minWidth}`)
  }
  if (queryParams.maxWidth != null) {
    tagsParts.push(`width:<=${queryParams.maxWidth}`)
  }

  // 高度
  if (queryParams.minHeight != null) {
    tagsParts.push(`height:>=${queryParams.minHeight}`)
  }
  if (queryParams.maxHeight != null) {
    tagsParts.push(`height:<=${queryParams.maxHeight}`)
  }

  // 文件大小
  if (queryParams.minFileSize != null) {
    tagsParts.push(`filesize:>=${queryParams.minFileSize}`)
  }
  if (queryParams.maxFileSize != null) {
    tagsParts.push(`filesize:<=${queryParams.maxFileSize}`)
  }

  const tags = tagsParts.join(' ')

  return {
    tags: tags,
    author: queryParams.author || undefined,
    sort_by: queryParams.sortBy,
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

/* 收缩状态搜索栏 */
.collapsed-search-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  background: var(--bg-secondary);
  backdrop-filter: blur(30px);
  border: 1px solid var(--border-color);
  border-radius: 24px;
  padding: 8px 8px 8px 16px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.2);
}

.collapsed-search-bar .search-input-wrapper {
  flex: 1;
  background: transparent;
  border: none;
  padding: 0;
}

.collapsed-search-bar .search-icon {
  color: var(--text-muted);
}

.search-btn {
  border-radius: 20px;
  padding: 8px 20px;
}

.expand-btn {
  background: transparent;
  border: none;
  color: var(--text-secondary);
}

.expand-btn:hover {
  color: var(--el-color-primary);
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
