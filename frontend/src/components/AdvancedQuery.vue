<template>
  <div class="advanced-query-container">
    <!-- 收缩状态：右下角圆形按钮 -->
    <div v-if="collapsed" class="collapsed-button" @click="expand">
      <el-icon :size="20"><Search /></el-icon>
    </div>

    <!-- 展开状态 -->
    <div v-else class="search-panel" :class="{ 'panel-expanded': showAdvanced }" ref="searchPanelRef">
      <!-- 一级搜索栏 -->
      <div class="search-bar">
        <div class="search-input-wrapper" :class="{ 'has-input-tags': selectedTags.length > 0 || selectedFavorite }">
          <el-icon class="search-icon"><Search /></el-icon>
          <!-- 输入框前缀：选中的标签 -->
          <div class="input-tags-container" v-if="selectedTags.length > 0 || selectedFavorite">
            <div class="input-tags-wrapper">
              <span
                v-if="selectedFavorite"
                class="input-tag favorite-tag"
              >
                <span class="input-tag-text" :title="'★ ' + selectedFavorite.name">★ {{ selectedFavorite.name }}</span>
                <el-icon class="input-tag-close" @click.stop="clearSelectedFavorite"><Close /></el-icon>
              </span>
              <span
                v-for="tag in selectedTags"
                :key="tag"
                class="input-tag"
              >
                <span class="input-tag-text" :title="'#' + tag">#{{ tag }}</span>
                <el-icon class="input-tag-close" @click.stop="removeInputTag(tag)"><Close /></el-icon>
              </span>
            </div>
          </div>
          <el-input
            class="search-input"
            v-model="searchText"
            :placeholder="selectedTags.length > 0 ? '继续输入标签...' : '输入标签搜索（用空格分隔，+tag包含 -tag排除）'"
            @keyup.enter="handleTagInput"
            clearable
          />
        </div>
        <div class="search-actions">
          <el-button circle size="small" @click="toggleFavoritePanel">
            <el-icon><Folder /></el-icon>
          </el-button>
          <el-button circle size="small" @click="toggleAdvanced">
            <el-icon><Setting /></el-icon>
          </el-button>
          <el-button circle size="small" @click="collapse">
            <el-icon><Minus /></el-icon>
          </el-button>
        </div>

        <!-- 收藏夹/Tags 面板 -->
        <transition name="el-fade-in-linear">
          <div v-if="showFavoritePanel" class="favorite-dropdown" @click.stop ref="favoriteDropdownRef" :style="{ width: favoriteDropdownWidth + 'px' }">
            <!-- 收藏夹内容 -->
            <div v-if="activePanelTab === 'favorites'" class="panel-content">
              <FavoritePanel
                ref="favoritePanelRef"
                :folders="favoriteFolders"
                :color-options="colorOptions"
                :source-mode="sourceMode"
                @select="selectFavorite"
                @longPress="handleLongPress"
                @create="handleCreateFolder"
                @update="handleUpdateFolder"
                @delete="handleDeleteFolder"
                @reset-sync="handleResetFolderSync"
                @mode-change="handleFavoriteModeChange"
              />
            </div>

            <!-- 标签浏览内容 - 倒装顺序 -->
            <div v-if="activePanelTab === 'tags'" class="panel-content">
              <div class="tag-list">
                <div
                  v-for="tag in tagList"
                  :key="tag.id"
                  class="tag-item"
                  :class="{ selected: selectedTags.includes(tag.name) }"
                  @click="selectTag(tag)"
                >
                  <el-icon
                    class="tag-star"
                    :class="{ starred: isTagFavorited(tag.name) }"
                    @click.stop="favoriteTag(tag)"
                  >
                    <Star />
                  </el-icon>
                  <span class="tag-name" :style="{ color: getTagColor(tag.type) }">#{{ tag.name }}</span>
                  <span class="tag-check" v-if="selectedTags.includes(tag.name)">
                    <el-icon><Check /></el-icon>
                  </span>
                  <span class="tag-stats">
                    <span v-if="sourceMode === 'local'" class="stat-local">
                      本地 {{ tag.local_count || 0 }}
                    </span>
                    <span class="stat-remote">
                      / yande {{ formatCount(tag.count) }}
                    </span>
                  </span>
                </div>
                <div v-if="tagList.length === 0" class="tag-empty">
                  暂无标签
                </div>
              </div>
              <div class="tag-type-tabs">
                <span
                  v-for="type in tagTypeOptions"
                  :key="type.value"
                  :class="{ active: selectedTagType === type.value }"
                  class="tag-type-tab"
                  @click="selectTagType(type.value)"
                >
                  <span class="type-dot" :style="{ backgroundColor: type.color }"></span>
                  {{ type.label }}
                </span>
              </div>
              <div class="tag-search-bar">
                <el-input
                  v-model="tagSearchKeyword"
                  placeholder="搜索标签..."
                  size="small"
                  clearable
                  @input="handleTagSearch"
                >
                  <template #prefix>
                    <el-icon><Search /></el-icon>
                  </template>
                </el-input>
              </div>
            </div>

            <!-- 面板头部 - 移到最下方; inline-form (创建/编辑) 时隐藏 -->
            <div v-if="!isFavoriteInlineForm" class="panel-header">
              <div class="segmented-control">
                <div
                  :class="['segment-item', { active: activePanelTab === 'favorites' }]"
                  @click="activePanelTab = 'favorites'"
                >
                  我的收藏
                </div>
                <div
                  :class="['segment-item', { active: activePanelTab === 'tags' }]"
                  @click="switchToTagsTab"
                >
                  标签浏览
                </div>
              </div>
              <el-button
                size="small"
                type="primary"
                class="subscribe-btn"
                @click="subscribeCurrentSearch"
              >
                订阅当前
              </el-button>
            </div>
          </div>
        </transition>
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

          <!-- 第三行：排序 (仅在线模式) -->
          <div class="panel-row" v-if="sourceMode === 'yande'">
            <div class="row-item">
              <label>排序</label>
              <div class="sort-selects">
                <el-select v-model="queryParams.sortBy" size="small">
                  <el-option label="ID" value="id" />
                  <el-option label="评分" value="score" />
                  <el-option label="像素" value="mpixels" />
                  <el-option label="横向优先" value="landscape" />
                  <el-option label="纵向优先" value="portrait" />
                  <el-option label="投票" value="vote" />
                </el-select>
                <el-select v-model="queryParams.sortOrder" size="small">
                  <el-option label="降序" value="desc" />
                  <el-option label="升序" value="asc" />
                </el-select>
              </div>
            </div>
          </div>

          <!-- 第四行：ID范围 (仅在线模式) -->
          <div class="panel-row" v-if="sourceMode === 'yande'">
            <div class="row-item range-item">
              <label>ID范围</label>
              <div class="range-inputs">
                <el-input-number v-model="queryParams.minId" :min="0" size="small" placeholder="最小" />
                <span class="range-separator">-</span>
                <el-input-number v-model="queryParams.maxId" :min="0" size="small" placeholder="最大" />
              </div>
            </div>

            <div class="row-item range-item">
              <label>像素(M)</label>
              <div class="range-inputs">
                <el-input-number v-model="queryParams.minMpixels" :min="0" :precision="1" size="small" placeholder="最小" />
                <span class="range-separator">-</span>
                <el-input-number v-model="queryParams.maxMpixels" :min="0" :precision="1" size="small" placeholder="最大" />
              </div>
            </div>

            <div class="row-item">
              <label>比例</label>
              <el-input
                v-model="queryParams.ratio"
                placeholder="如 16:9"
                size="small"
                clearable
                style="width: 100px;"
              />
            </div>
          </div>

          <!-- 第五行：日期范围 (仅在线模式) -->
          <div class="panel-row" v-if="sourceMode === 'yande'">
            <div class="row-item range-item">
              <label>日期范围</label>
              <div class="range-inputs">
                <el-date-picker
                  v-model="queryParams.minDate"
                  type="date"
                  size="small"
                  placeholder="开始日期"
                  style="width: 140px;"
                  format="YYYY-MM-DD"
                  value-format="YYYY-MM-DD"
                />
                <span class="range-separator">-</span>
                <el-date-picker
                  v-model="queryParams.maxDate"
                  type="date"
                  size="small"
                  placeholder="结束日期"
                  style="width: 140px;"
                  format="YYYY-MM-DD"
                  value-format="YYYY-MM-DD"
                />
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
import { ref, reactive, computed, onMounted, onUnmounted, watch } from 'vue'
import { Search, Setting, Minus, Folder, Close, Star, Check } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getAllFolders, createFolder, updateFolder, deleteFolder, resetFolderSync } from '@/api/favorites'
import { tagCacheApi } from '@/api/tagCache'
import FavoritePanel from './FavoritePanel.vue'

const props = defineProps({
  sourceMode: {
    type: String,
    default: 'local'
  }
})

const emit = defineEmits(['search'])

// 收藏夹相关
const showFavoritePanel = ref(false)
const favoriteFolders = ref([])
const favoritePanelRef = ref(null)
const searchPanelRef = ref(null)
const favoriteDropdownRef = ref(null)
const panelWidthTrigger = ref(0)
// 收藏夹子组件当前模式 ('list' | 'create' | 'edit'), inline-form 时隐藏 panel-header
const favoritePanelMode = ref('list')
const isFavoriteInlineForm = computed(() => favoritePanelMode.value !== 'list')

// 动态宽度：当 search-panel 变窄时，favorite-dropdown 也同步缩小
const favoriteDropdownWidth = computed(() => {
  const panel = searchPanelRef.value
  if (!panel) return 360

  // 引用 trigger 强制依赖响应式变化
  void panelWidthTrigger.value

  const panelWidth = panel.offsetWidth
  const minWidth = 280
  const maxWidth = 360

  return Math.min(maxWidth, Math.max(minWidth, panelWidth))
})

// 监听 panel 宽度变化
onMounted(() => {
  const panel = searchPanelRef.value
  if (panel) {
    const resizeObserver = new ResizeObserver(() => {
      panelWidthTrigger.value++
    })
    resizeObserver.observe(panel)
  }
})

// 标签浏览相关
const activePanelTab = ref('favorites')
const tagSearchKeyword = ref('')
const selectedTagType = ref(0)
const tagList = ref([])
const tagStatsLoaded = ref(false)

const tagTypeOptions = [
  { label: '全部', value: -1, color: '#888' },
  { label: '通用', value: 0, color: '#ee8887' },
  { label: '艺术家', value: 1, color: '#cccc00' },
  { label: '版权', value: 3, color: '#D0D' },
  { label: '角色', value: 4, color: '#0A0' },
]

const TAG_TYPE_COLORS = {
  0: '#ee8887',  // 通用
  1: '#cccc00',  // 艺术家
  3: '#D0D',     // 版权
  4: '#0A0',     // 角色
}

const getTagColor = (type) => {
  return TAG_TYPE_COLORS[type] || TAG_TYPE_COLORS[0]
}

const formatCount = (count) => {
  if (count >= 1000) {
    return (count / 1000).toFixed(1) + 'k'
  }
  return count
}

const switchToTagsTab = async () => {
  activePanelTab.value = 'tags'
  await loadFavoriteFolders()
  if (!tagStatsLoaded.value) {
    await calculateLocalStats()
    tagStatsLoaded.value = true
  }
  loadTags()
}

const selectTagType = (type) => {
  selectedTagType.value = type
  loadTags()
}

const handleTagSearch = () => {
  loadTags()
}

const calculateLocalStats = async () => {
  try {
    await tagCacheApi.calculateLocalStats()
  } catch (error) {
    console.error('计算本地统计失败:', error)
  }
}

const loadTags = async () => {
  try {
    const params = {
      limit: 100,
    }
    // -1 表示全部类型，不传 type 参数
    if (selectedTagType.value !== -1) {
      params.type = selectedTagType.value
    }
    if (tagSearchKeyword.value) {
      params.search = tagSearchKeyword.value
    }
    if (props.sourceMode === 'local') {
      params.has_local_only = true
    }
    const res = await tagCacheApi.getTagsWithStats(params)
    tagList.value = res.data?.tags || []
  } catch (error) {
    console.error('加载标签失败:', error)
    tagList.value = []
  }
}

// 点击标签列表项时切换选中状态
const selectTag = (tag) => {
  // 如果已有相同标签则移除，否则添加
  const index = selectedTags.value.indexOf(tag.name)
  if (index >= 0) {
    selectedTags.value.splice(index, 1)
  } else {
    selectedTags.value.push(tag.name)
  }
  // searchText 由用户输入，不同步
  // 触发搜索
  handleSearch()
}

// 移除输入框中的标签
const removeInputTag = (tag) => {
  const index = selectedTags.value.indexOf(tag)
  if (index >= 0) {
    selectedTags.value.splice(index, 1)
    handleSearch()
  }
}

// 处理标签输入（回车时将输入内容转为标签）
const handleTagInput = () => {
  const text = searchText.value.trim()
  if (text && !selectedTags.value.includes(text)) {
    selectedTags.value.push(text)
    searchText.value = ''  // 清空输入框准备下一个标签
    handleSearch()
  }
}

const isTagFavorited = (tagName) => {
  return favoriteFolders.value.some(folder => 
    folder.tags === tagName || folder.tags === `#${tagName}`
  )
}

const favoriteTag = async (tag) => {
  const existingFolder = favoriteFolders.value.find(folder =>
    folder.tags === tag.name || folder.tags === `#${tag.name}`
  )

  if (existingFolder) {
    try {
      await deleteFolder(existingFolder.id)
      ElMessage.success('已取消收藏')
      loadFavoriteFolders()
    } catch (error) {
      ElMessage.error('取消收藏失败')
    }
    return
  }

  try {
    await createFolder({
      name: `#${tag.name}`,
      tags: tag.name,
      color: '#E6A23C',
      icon: 'star',
      sort_order: favoriteFolders.value.length,
    })
    ElMessage.success('已收藏标签')
    loadFavoriteFolders()
  } catch (error) {
    ElMessage.error('收藏失败')
  }
}

const loadFavoriteFolders = async () => {
  try {
    const res = await getAllFolders()
    favoriteFolders.value = res.data || []
  } catch (error) {
    console.error('加载收藏夹失败:', error)
  }
}

const toggleFavoritePanel = () => {
  showFavoritePanel.value = !showFavoritePanel.value
  if (showFavoritePanel.value) {
    loadFavoriteFolders()
    document.addEventListener('click', handleClickOutside)
  } else {
    document.removeEventListener('click', handleClickOutside)
  }
}

const handleLongPress = (folder) => {
  favoritePanelRef.value?.openEdit(folder)
}

const handleFavoriteModeChange = (newMode) => {
  favoritePanelMode.value = newMode
}

const handleCreateFolder = async (payload) => {
  try {
    await createFolder({
      ...payload,
      icon: 'folder',
      sort_order: favoriteFolders.value.length,
    })
    ElMessage.success('订阅成功')
    await loadFavoriteFolders()
  } catch (error) {
    ElMessage.error('订阅失败')
  }
}

const handleUpdateFolder = async ({ id, ...payload }) => {
  try {
    await updateFolder(id, payload)
    ElMessage.success('保存成功')
    await loadFavoriteFolders()
  } catch (error) {
    ElMessage.error('保存失败')
  }
}

const handleDeleteFolder = async (folder) => {
  try {
    await deleteFolder(folder.id)
    ElMessage.success('已删除')
    await loadFavoriteFolders()
  } catch (error) {
    ElMessage.error('删除失败')
  }
}

const handleResetFolderSync = async (folder) => {
  try {
    await resetFolderSync(folder.id, null)
    ElMessage.success(`已重置「${folder.name}」同步游标`)
    await loadFavoriteFolders()
  } catch (error) {
    ElMessage.error('重置同步游标失败')
  }
}

const handleClickOutside = (e) => {
  const container = document.querySelector('.advanced-query-container')
  if (!container) return
  if (container.contains(e.target)) return
  if (e.target.closest('.el-popper')) return
  showFavoritePanel.value = false
  document.removeEventListener('click', handleClickOutside)
}

onUnmounted(() => {
  document.removeEventListener('click', handleClickOutside)
})

// 一键订阅当前搜索
const subscribeCurrentSearch = () => {
  const tagsStr = buildCurrentTagsString()
  favoritePanelRef.value?.openCreate({ tags: tagsStr })
}

// 构建当前搜索的 tags 字符串
const buildCurrentTagsString = () => {
  const parts = []

  // 收藏夹标签
  if (selectedFavorite.value?.tags) {
    const favTags = parseFavoriteTagsToParts(selectedFavorite.value.tags)
    parts.push(...favTags)
  }

  // 基础标签 - 使用 selectedTags
  if (selectedTags.value.length > 0) {
    parts.push(...selectedTags.value)
  }

  // 评分
  if (queryParams.rating && queryParams.rating.length > 0) {
    queryParams.rating.forEach(r => {
      parts.push(`rating:${r}`)
    })
  }

  // 排序 (在线模式)
  if (props.sourceMode === 'yande') {
    const orderVal = queryParams.sortOrder === 'asc' 
      ? `${queryParams.sortBy}_asc` 
      : queryParams.sortBy
    if (orderVal !== 'id') {
      parts.push(`order:${orderVal}`)
    }
  }

  // 文件格式
  if (props.sourceMode === 'local' && queryParams.fileType && queryParams.fileType.length > 0) {
    queryParams.fileType.forEach(ext => {
      parts.push(`ext:${ext}`)
    })
  } else if (props.sourceMode === 'yande' && queryParams.fileTypeSingle) {
    parts.push(`ext:${queryParams.fileTypeSingle}`)
  }

  // 尺寸
  if (queryParams.minWidth) {
    parts.push(`width:>=${queryParams.minWidth}`)
  }
  if (queryParams.maxWidth) {
    parts.push(`width:<=${queryParams.maxWidth}`)
  }
  if (queryParams.minHeight) {
    parts.push(`height:>=${queryParams.minHeight}`)
  }
  if (queryParams.maxHeight) {
    parts.push(`height:<=${queryParams.maxHeight}`)
  }

  // ID范围 (在线模式)
  if (props.sourceMode === 'yande') {
    if (queryParams.minId) {
      parts.push(`id:>=${queryParams.minId}`)
    }
    if (queryParams.maxId) {
      parts.push(`id:<=${queryParams.maxId}`)
    }
    if (queryParams.minMpixels) {
      parts.push(`mpixels:>=${queryParams.minMpixels}`)
    }
    if (queryParams.maxMpixels) {
      parts.push(`mpixels:<=${queryParams.maxMpixels}`)
    }
    if (queryParams.ratio) {
      parts.push(`ratio:${queryParams.ratio}`)
    }
    if (queryParams.minDate) {
      parts.push(`date:>=${queryParams.minDate}`)
    }
    if (queryParams.maxDate) {
      parts.push(`date:<=${queryParams.maxDate}`)
    }
  }

  return parts.join(' ')
}

// 选择收藏夹
const selectFavorite = (folder) => {
  selectedFavorite.value = folder
  // 解析收藏夹的特殊参数（rating, score 等）
  if (folder.tags) {
    const favParams = parseFavoriteTagsToParams(folder.tags)
    queryParams.rating = favParams.rating || []
    queryParams.minScore = favParams.min_score || null
    queryParams.maxScore = favParams.max_score || null
    queryParams.sortBy = favParams.sort_by || queryParams.sortBy
    queryParams.sortOrder = favParams.sort_order || queryParams.sortOrder
    queryParams.minWidth = favParams.min_width || null
    queryParams.maxWidth = favParams.max_width || null
    queryParams.minHeight = favParams.min_height || null
    queryParams.maxHeight = favParams.max_height || null
    queryParams.fileTypeSingle = favParams.file_types?.[0] || ''
    queryParams.minId = favParams.min_id || null
    queryParams.maxId = favParams.max_id || null
    queryParams.minMpixels = favParams.min_mpixels || null
    queryParams.maxMpixels = favParams.max_mpixels || null
    queryParams.ratio = favParams.ratio || ''
    queryParams.minDate = favParams.min_date || ''
    queryParams.maxDate = favParams.max_date || ''
  }
  showFavoritePanel.value = false
  handleSearch()
}

const clearSelectedFavorite = () => {
  selectedFavorite.value = null
  handleSearch()
}

// 解析收藏夹的 tags 字符串为查询参数
const parseFavoriteTagsToParams = (tagsStr) => {
  const params = {}
  if (!tagsStr) return params

  const parts = tagsStr.split(/\s+/)
  for (const part of parts) {
    if (part.startsWith('rating:')) {
      if (!params.rating) {
        params.rating = []
      }
      params.rating.push(part.split(':')[1])
    } else if (part.startsWith('score:>=')) {
      params.min_score = parseInt(part.split(':')[1])
    } else if (part.startsWith('score:<=')) {
      params.max_score = parseInt(part.split(':')[1])
    } else if (part.startsWith('sort_by:')) {
      params.sort_by = part.split(':')[1]
    } else if (part.startsWith('sort_order:')) {
      params.sort_order = part.split(':')[1]
    } else if (part.startsWith('width:>=')) {
      params.min_width = parseInt(part.split(':')[1])
    } else if (part.startsWith('width:<=')) {
      params.max_width = parseInt(part.split(':')[1])
    } else if (part.startsWith('height:>=')) {
      params.min_height = parseInt(part.split(':')[1])
    } else if (part.startsWith('height:<=')) {
      params.max_height = parseInt(part.split(':')[1])
    } else if (part.startsWith('ext:')) {
      params.file_types = [part.split(':')[1]]
    } else if (part.startsWith('id:>=')) {
      params.min_id = parseInt(part.split(':')[1])
    } else if (part.startsWith('id:<=')) {
      params.max_id = parseInt(part.split(':')[1])
    } else if (part.startsWith('mpixels:>=')) {
      params.min_mpixels = parseFloat(part.split(':')[1])
    } else if (part.startsWith('mpixels:<=')) {
      params.max_mpixels = parseFloat(part.split(':')[1])
    } else if (part.startsWith('ratio:')) {
      params.ratio = part.split(':')[1]
    } else if (part.startsWith('date:>=')) {
      params.min_date = part.split(':')[1]
    } else if (part.startsWith('date:<=')) {
      params.max_date = part.split(':')[1]
    } else if (!part.startsWith('-')) {
      if (!params.tags) {
        params.tags = part
      } else {
        params.tags += ' ' + part
      }
    }
  }
  return params
}

// 解析收藏夹的 tags 字符串为标签数组（用于显示）
const parseFavoriteTagsToParts = (tagsStr) => {
  if (!tagsStr) return []
  return tagsStr.split(/\s+/).filter(part => {
    return !part.startsWith('rating:') &&
           !part.startsWith('score:>=') &&
           !part.startsWith('score:<=') &&
           !part.startsWith('order:') &&
           !part.startsWith('width:>=') &&
           !part.startsWith('width:<=') &&
           !part.startsWith('height:>=') &&
           !part.startsWith('height:<=') &&
           !part.startsWith('ext:') &&
           !part.startsWith('id:>=') &&
           !part.startsWith('id:<=') &&
           !part.startsWith('mpixels:>=') &&
           !part.startsWith('mpixels:<=') &&
           !part.startsWith('ratio:') &&
           !part.startsWith('date:>=') &&
           !part.startsWith('date:<=')
  })
}

// 颜色选项
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

// 状态
const collapsed = ref(false)
const showAdvanced = ref(false)
const searchText = ref('')

// 选中的标签列表（多标签搜索）
const selectedTags = ref([])

// 选中的收藏夹
const selectedFavorite = ref(null)

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
  sortBy: 'id',
  sortOrder: 'desc',
  minMpixels: null,
  maxMpixels: null,
  ratio: '',
  minDate: '',
  maxDate: '',
  minId: null,
  maxId: null,
})

// 计算激活的筛选标签（不包括已显示在输入框中的标签）
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

  // 在线模式专用筛选
  if (props.sourceMode === 'yande') {
    if (queryParams.minId || queryParams.maxId) {
      const min = queryParams.minId || 0
      const max = queryParams.maxId || '∞'
      filters.push({ key: 'idRange', label: `ID:${min}-${max}` })
    }
    if (queryParams.minMpixels || queryParams.maxMpixels) {
      const min = queryParams.minMpixels || 0
      const max = queryParams.maxMpixels || '∞'
      filters.push({ key: 'mpixels', label: `像素:${min}-${max}M` })
    }
    if (queryParams.ratio) {
      filters.push({ key: 'ratio', label: `比例:${queryParams.ratio}` })
    }
    if (queryParams.minDate || queryParams.maxDate) {
      const min = queryParams.minDate || '开始'
      const max = queryParams.maxDate || '结束'
      filters.push({ key: 'dateRange', label: `日期:${min}~${max}` })
    }
  }

  return filters
})

// 移除筛选标签
const removeFilter = (filter) => {
  // 处理标签移除
  if (filter.type === 'tag' && filter.key.startsWith('tag:')) {
    const tagName = filter.key.replace('tag:', '')
    const index = selectedTags.value.indexOf(tagName)
    if (index >= 0) {
      selectedTags.value.splice(index, 1)
      handleSearch()
    }
    return
  }

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
    case 'idRange':
      queryParams.minId = null
      queryParams.maxId = null
      break
    case 'mpixels':
      queryParams.minMpixels = null
      queryParams.maxMpixels = null
      break
    case 'ratio':
      queryParams.ratio = ''
      break
    case 'dateRange':
      queryParams.minDate = ''
      queryParams.maxDate = ''
      break
  }
  handleSearch()
}

// 收缩/展开
const collapse = () => {
  if (showAdvanced.value) {
    // 如果高级搜索展开，先收起高级搜索
    showAdvanced.value = false
  } else {
    // 否则收起整个搜索栏
    collapsed.value = true
  }
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
  queryParams.sortBy = 'id'
  queryParams.sortOrder = 'desc'
  queryParams.minMpixels = null
  queryParams.maxMpixels = null
  queryParams.ratio = ''
  queryParams.minDate = ''
  queryParams.maxDate = ''
  queryParams.minId = null
  queryParams.maxId = null
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
// 构建本地模式搜索参数
const buildLocalParams = () => {
  // 合并收藏夹标签和用户选择的标签
  const favTags = selectedFavorite.value?.tags
    ? parseFavoriteTagsToParts(selectedFavorite.value.tags)
    : []
  const allTags = [...favTags, ...selectedTags.value]
  const tags = allTags.join(' ')

  return {
    tags: tags || undefined,
    author: queryParams.author || undefined,
    rating: queryParams.rating.length > 0 ? queryParams.rating : undefined,
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
  // 合并收藏夹标签和用户选择的标签
  const favTags = selectedFavorite.value?.tags
    ? parseFavoriteTagsToParts(selectedFavorite.value.tags)
    : []
  const allTags = [...favTags, ...selectedTags.value]
  const tags = allTags.join(' ')

  return {
    tags: tags || undefined,
    author: queryParams.author || undefined,
    rating: queryParams.rating,
    file_types: queryParams.fileTypeSingle ? [queryParams.fileTypeSingle] : undefined,
    min_width: queryParams.minWidth || undefined,
    max_width: queryParams.maxWidth || undefined,
    min_height: queryParams.minHeight || undefined,
    max_height: queryParams.maxHeight || undefined,
    min_file_size: queryParams.minFileSize || undefined,
    max_file_size: queryParams.maxFileSize || undefined,
    min_score: queryParams.minScore || undefined,
    max_score: queryParams.maxScore || undefined,
    min_mpixels: queryParams.minMpixels || undefined,
    max_mpixels: queryParams.maxMpixels || undefined,
    ratio: queryParams.ratio || undefined,
    min_date: queryParams.minDate || undefined,
    max_date: queryParams.maxDate || undefined,
    min_id: queryParams.minId || undefined,
    max_id: queryParams.maxId || undefined,
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
  emit('search', { mode, params, favorite: selectedFavorite.value })
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
    selectedTags.value = []
    selectedFavorite.value = null
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
  background: rgba(var(--bg-secondary-rgb, 255, 255, 255), 0.8);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 12px;
  padding: 8px 12px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.12);
  transition: all 0.3s ease;
}

/* 深色模式 */
html.dark-mode .search-panel {
  background: rgba(var(--bg-secondary-rgb, 45, 45, 45), 0.8);
  border: 1px solid rgba(255, 255, 255, 0.1);
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
  min-height: 40px;
  max-height: 40px;
  flex-wrap: wrap;
}

.search-input-wrapper.has-input-tags {
  padding: 4px 8px;
  flex-wrap: nowrap;
  overflow: hidden;
}

.search-input-wrapper :deep(.el-input__wrapper) {
  background: transparent;
  box-shadow: none;
  padding: 0;
}

.search-input-wrapper :deep(.el-input__inner) {
  color: var(--text-primary);
  flex: 1;
  min-width: 80px;
}

.search-input-wrapper :deep(.el-input__inner::placeholder) {
  color: var(--text-muted);
}

.search-input-wrapper :deep(.el-input) {
  flex: 1;
  min-width: 0;
}

/* 输入框中的标签容器 - 可以缩小标签 */
.input-tags-container {
  display: flex;
  flex-shrink: 1;
  min-width: 0;
  overflow: hidden;
}

/* 输入框中的标签样式 */
.input-tags-wrapper {
  display: flex;
  flex-wrap: nowrap;
  gap: 4px;
  align-items: center;
  overflow: hidden;
}

.search-input-wrapper :deep(.el-input__wrapper) {
  background: transparent;
  box-shadow: none;
  padding: 0;
  flex: 1;
  min-width: 120px;
}

.search-input-wrapper :deep(.el-input__inner) {
  color: var(--text-primary);
}

.search-input-wrapper :deep(.el-input__inner::placeholder) {
  color: var(--text-muted);
}

/* 输入框中的标签样式 */
.input-tags-wrapper {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  align-items: center;
}

.input-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  background: var(--el-color-primary-light-9);
  border: 1px solid var(--el-color-primary-light-7);
  border-radius: 4px;
  font-size: 12px;
  color: var(--el-color-primary);
  cursor: default;
  white-space: nowrap;
  max-width: 150px;
  overflow: hidden;
  flex-shrink: 0;
}

.input-tag-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
  flex: 1;
}

.input-tag-close {
  flex-shrink: 0;
  cursor: pointer;
  padding: 2px;
  border-radius: 2px;
  transition: background-color 0.2s;
}

.input-tag-close:hover {
  background: var(--el-color-primary-light-7);
}

.search-icon {
  color: var(--text-muted);
  flex-shrink: 0;
}

.input-clear-icon {
  color: var(--text-muted);
  cursor: pointer;
}

.input-clear-icon:hover {
  color: var(--text-secondary);
}

.search-tags {
  display: flex;
  flex-direction: column;
  gap: 1px;
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

/* 收藏夹下拉面板 - 向上展开 */
.favorite-dropdown {
  position: absolute;
  bottom: 100%;
  right: 0;
  margin-bottom: 8px;
  width: 360px;
  max-height: 400px;
  background: rgba(var(--bg-secondary-rgb, 255, 255, 255), 0.85);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 8px;
  box-shadow: 0 -4px 16px rgba(0, 0, 0, 0.1);
  z-index: 1001;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

/* 深色模式 */
html.dark-mode .favorite-dropdown {
  background: rgba(var(--bg-secondary-rgb, 45, 45, 45), 0.85);
  border: 1px solid rgba(255, 255, 255, 0.1);
}

.favorite-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border-color);
  font-weight: 600;
  font-size: 14px;
}

.favorite-header :deep(.el-button) {
  padding: 4px 12px;
  font-size: 12px;
}

.favorite-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

/* 半透明滑块滚动条 */
.favorite-list::-webkit-scrollbar,
.tag-list::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}

.favorite-list::-webkit-scrollbar-track,
.tag-list::-webkit-scrollbar-track {
  background: transparent;
}

.favorite-list::-webkit-scrollbar-thumb,
.tag-list::-webkit-scrollbar-thumb {
  background: rgba(128, 128, 128, 0.3);
  border-radius: 3px;
}

.favorite-list::-webkit-scrollbar-thumb:hover,
.tag-list::-webkit-scrollbar-thumb:hover {
  background: rgba(128, 128, 128, 0.5);
}

.favorite-list::-webkit-scrollbar-button,
.tag-list::-webkit-scrollbar-button {
  height: 0;
  display: block;
}

.favorite-list::-webkit-scrollbar-track-piece,
.tag-list::-webkit-scrollbar-track-piece {
  background: transparent;
}

.favorite-list,
.tag-list {
  -ms-overflow-style: none;
  scrollbar-width: thin;
}

.favorite-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  border-radius: 8px;
  cursor: pointer;
  transition: background-color 0.2s;
}

.favorite-item:hover {
  background: var(--bg-tertiary);
}

.favorite-icon {
  width: 32px;
  height: 32px;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  font-size: 16px;
  flex-shrink: 0;
}

.favorite-info {
  flex: 1;
  min-width: 0;
}

.favorite-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.favorite-tags {
  font-size: 12px;
  color: var(--text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-top: 2px;
}

.favorite-count {
  font-size: 12px;
  color: var(--text-muted);
  background: var(--bg-primary);
  padding: 2px 8px;
  border-radius: 10px;
  flex-shrink: 0;
}

.favorite-empty {
  text-align: center;
  padding: 24px 16px;
  color: var(--text-muted);
  font-size: 13px;
}

/* Segmented Control 样式 */
.panel-header {
  padding: 8px 12px;
  border-bottom: 1px solid var(--border-color);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.segmented-control {
  display: flex;
  background: var(--bg-primary);
  border-radius: 8px;
  padding: 3px;
  gap: 3px;
  flex: 1;
}

.subscribe-btn {
  flex-shrink: 0;
}

.segment-item {
  flex: 1;
  padding: 6px 12px;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
  text-align: center;
  cursor: pointer;
  color: var(--text-muted);
  transition: all 0.2s;
}

.segment-item:hover {
  color: var(--text-primary);
}

.segment-item.active {
  background: var(--bg-secondary);
  color: #409EFF;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

.panel-content {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  /* 滚动条样式应用到 panel-content */
}

.panel-content::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}

.panel-content::-webkit-scrollbar-track {
  background: transparent;
}

.panel-content::-webkit-scrollbar-thumb {
  background: rgba(128, 128, 128, 0.3);
  border-radius: 3px;
}

.panel-content::-webkit-scrollbar-thumb:hover {
  background: rgba(128, 128, 128, 0.5);
}

.panel-content::-webkit-scrollbar-button {
  height: 0;
  display: block;
}

.panel-content::-webkit-scrollbar-track-piece {
  background: transparent;
}

.panel-footer-btn {
  padding: 8px 12px;
  border-top: 1px solid var(--border-color);
  display: flex;
  justify-content: center;
}

/* 标签浏览 */
.tag-search-bar {
  padding: 8px 12px;
  border-top: 1px solid var(--border-color); /* 视觉上现在是底部，加顶部边框 */
}

.tag-type-tabs {
  display: flex;
  padding: 8px 12px;
  gap: 6px;
  border-top: 1px solid var(--border-color); /* 视觉上现在是底部，加顶部边框 */
  flex-wrap: wrap;
}

.tag-type-tab {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  border-radius: 12px;
  font-size: 12px;
  cursor: pointer;
  background: var(--bg-primary);
  color: var(--text-muted);
  transition: all 0.2s;
}

.tag-type-tab:hover {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

.tag-type-tab.active {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

.type-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.tag-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.tag-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: 6px;
  cursor: pointer;
  transition: background-color 0.2s;
}

.tag-item:hover {
  background: var(--bg-tertiary);
}

.tag-item.selected {
  background: var(--bg-tertiary);
  border: 1px solid var(--el-color-primary);
}

.tag-check {
  font-size: 14px;
  color: var(--el-color-primary);
  flex-shrink: 0;
}

.tag-star {
  font-size: 14px;
  color: var(--text-muted);
  cursor: pointer;
  transition: color 0.2s;
  flex-shrink: 0;
  opacity: 0.4; /* 未收藏时不显眼 */
}

.tag-star:hover {
  opacity: 0.8;
  color: #E6A23C;
}

.tag-star.starred {
  opacity: 1;
  color: #E6A23C;
}

.tag-name {
  font-size: 13px;
  color: var(--text-primary);
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tag-stats {
  font-size: 11px;
  color: var(--text-muted);
}

.tag-stats .stat-local {
  color: #67C23A;
}

.tag-empty {
  text-align: center;
  padding: 24px 16px;
  color: var(--text-muted);
  font-size: 13px;
}
</style>
