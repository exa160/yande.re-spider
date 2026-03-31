<template>
  <div class="query-container">
    <!-- 一级查询：悬浮在页面上的小型查询栏 -->
    <div class="floating-query-bar">
      <el-card shadow="hover" class="query-bar-card">
        <el-form :model="basicParams" inline>
          <el-form-item label="标签">
            <el-input
              v-model="basicParams.tags"
              placeholder="输入标签搜索"
              clearable
              style="width: 200px;"
              @keyup.enter="handleSearch"
            />
          </el-form-item>
          <el-form-item label="作者">
            <el-input
              v-model="basicParams.author"
              placeholder="作者名称"
              clearable
              style="width: 120px;"
              @keyup.enter="handleSearch"
            />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" @click="handleSearch">
              <el-icon><Search /></el-icon>
              查询
            </el-button>
            <el-button @click="toggleAdvanced">
              {{ showAdvanced ? '收起' : '高级' }}
              <el-icon>
                <ArrowUp v-if="showAdvanced" />
                <ArrowDown v-else />
              </el-icon>
            </el-button>
          </el-form-item>
        </el-form>
      </el-card>
    </div>

    <!-- 二级高级查询：展开后显示的悬浮面板 -->
    <el-collapse-transition>
      <div v-if="showAdvanced" class="advanced-query-panel">
        <el-card shadow="hover">
          <template #header>
            <div style="display: flex; justify-content: space-between; align-items: center;">
              <span>高级筛选</span>
              <el-button type="text" @click="showAdvanced = false">
                <el-icon><Close /></el-icon>
              </el-button>
            </div>
          </template>

          <el-form :model="queryParams" label-width="100px">
            <el-row :gutter="20">
              <!-- 分辨率范围 -->
              <el-col :span="12">
                <el-form-item label="宽度范围">
                  <el-col :span="11">
                    <el-input-number v-model="queryParams.min_width" :min="0" :max="10000" placeholder="最小宽度" style="width: 100%;" />
                  </el-col>
                  <el-col :span="2" style="text-align: center;">-</el-col>
                  <el-col :span="11">
                    <el-input-number v-model="queryParams.max_width" :min="0" :max="10000" placeholder="最大宽度" style="width: 100%;" />
                  </el-col>
                </el-form-item>
              </el-col>

              <el-col :span="12">
                <el-form-item label="高度范围">
                  <el-col :span="11">
                    <el-input-number v-model="queryParams.min_height" :min="0" :max="10000" placeholder="最小高度" style="width: 100%;" />
                  </el-col>
                  <el-col :span="2" style="text-align: center;">-</el-col>
                  <el-col :span="11">
                    <el-input-number v-model="queryParams.max_height" :min="0" :max="10000" placeholder="最大高度" style="width: 100%;" />
                  </el-col>
                </el-form-item>
              </el-col>
            </el-row>

            <el-row :gutter="20">
              <!-- 评分过滤 -->
              <el-col :span="12">
                <el-form-item label="评分">
                  <el-select v-model="queryParams.rating" placeholder="选择评分" style="width: 100%;">
                    <el-option label="全部" value="All" />
                    <el-option label="Safe" value="Safe" />
                    <el-option label="Questionable" value="Questionable" />
                    <el-option label="Explicit" value="Explicit" />
                  </el-select>
                </el-form-item>
              </el-col>

              <!-- 文件类型 -->
              <el-col :span="12">
                <el-form-item label="文件类型">
                  <el-select v-model="queryParams.file_type" placeholder="选择文件类型" style="width: 100%;" clearable>
                    <el-option label="JPG" value="JPG" />
                    <el-option label="PNG" value="PNG" />
                    <el-option label="GIF" value="GIF" />
                    <el-option label="WEBP" value="WEBP" />
                  </el-select>
                </el-form-item>
              </el-col>
            </el-row>

            <!-- 文件大小范围 -->
            <el-form-item label="文件大小">
              <el-col :span="11">
                <el-input-number v-model="queryParams.min_file_size" :min="0" :max="1000000" placeholder="最小(KB)" style="width: 100%;" />
              </el-col>
              <el-col :span="2" style="text-align: center;">-</el-col>
              <el-col :span="11">
                <el-input-number v-model="queryParams.max_file_size" :min="0" :max="1000000" placeholder="最大(KB)" style="width: 100%;" />
              </el-col>
            </el-form-item>

            <!-- 排序 -->
            <el-form-item label="排序方式">
              <el-col :span="12">
                <el-select v-model="queryParams.sort_by" placeholder="排序字段" style="width: 100%;">
                  <el-option label="创建时间" value="created_at" />
                  <el-option label="评分" value="rating" />
                  <el-option label="文件大小" value="file_size" />
                  <el-option label="宽度" value="width" />
                  <el-option label="高度" value="height" />
                </el-select>
              </el-col>
              <el-col :span="12">
                <el-select v-model="queryParams.sort_order" placeholder="排序方向" style="width: 100%;">
                  <el-option label="升序" value="asc" />
                  <el-option label="降序" value="desc" />
                </el-select>
              </el-col>
            </el-form-item>

            <!-- 分页 -->
            <el-form-item label="每页数量">
              <el-input-number v-model="queryParams.page_size" :min="1" :max="100" />
            </el-form-item>
          </el-form>
        </el-card>
      </div>
    </el-collapse-transition>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { Search, ArrowDown, ArrowUp, Close } from '@element-plus/icons-vue'

const emit = defineEmits(['search'])

const showAdvanced = ref(false)

// 基础查询参数（一级）
const basicParams = reactive({
  tags: '',
  author: ''
})

// 完整查询参数（二级高级选项）
const queryParams = reactive({
  tags: '',
  author: '',
  min_width: null,
  max_width: null,
  min_height: null,
  max_height: null,
  rating: 'All',
  min_file_size: null,
  max_file_size: null,
  file_type: '',
  sort_by: 'created_at',
  sort_order: 'desc',
  page: 1,
  page_size: 20
})

const toggleAdvanced = () => {
  showAdvanced.value = !showAdvanced.value
}

const handleSearch = () => {
  // 合并基础参数和高级参数
  const mergedParams = {
    ...queryParams,
    tags: basicParams.tags,
    author: basicParams.author,
    page: 1
  }
  emit('search', mergedParams)
}

// 暴露方法供父组件调用
defineExpose({
  reset: () => {
    basicParams.tags = ''
    basicParams.author = ''
    Object.assign(queryParams, {
      tags: '',
      author: '',
      min_width: null,
      max_width: null,
      min_height: null,
      max_height: null,
      rating: 'All',
      min_file_size: null,
      max_file_size: null,
      file_type: '',
      sort_by: 'created_at',
      sort_order: 'desc',
      page: 1,
      page_size: 20
    })
  }
})
</script>

<style scoped>
.query-container {
  margin-bottom: 20px;
  position: relative;
}

.floating-query-bar {
  position: sticky;
  top: 0;
  z-index: 100;
  padding: 10px 0;
}

.query-bar-card {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border: none;
}

.query-bar-card :deep(.el-card__body) {
  padding: 15px 20px;
}

.query-bar-card :deep(.el-form-item) {
  margin-bottom: 0;
}

.query-bar-card :deep(.el-form-item__label) {
  color: white;
}

.query-bar-card :deep(.el-input__wrapper) {
  background: rgba(255, 255, 255, 0.9);
}

.query-bar-card :deep(.el-button) {
  background: rgba(255, 255, 255, 0.2);
  border: 1px solid rgba(255, 255, 255, 0.3);
  color: white;
}

.query-bar-card :deep(.el-button:hover) {
  background: rgba(255, 255, 255, 0.3);
}

.query-bar-card :deep(.el-button--primary) {
  background: white;
  border-color: white;
  color: #667eea;
}

.query-bar-card :deep(.el-button--primary:hover) {
  background: #f0f0f0;
  border-color: #f0f0f0;
}

.advanced-query-panel {
  margin-top: 10px;
}

.advanced-query-panel :deep(.el-card__header) {
  background: #f5f7fa;
  padding: 10px 20px;
}
</style>
