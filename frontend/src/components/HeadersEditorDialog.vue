<template>
  <el-dialog
    :model-value="modelValue"
    title="编辑请求头"
    width="720px"
    :close-on-click-modal="false"
    @update:model-value="handleClose"
  >
    <div class="fixed-headers">
      <div class="section-title">常用</div>
      <el-form label-width="140px">
        <el-form-item label="User-Agent">
          <el-input
            v-model="localHeaders.user_agent"
            size="small"
            clearable
            placeholder="如: Mozilla/5.0 ..."
          />
        </el-form-item>
        <el-form-item label="Accept">
          <el-input
            v-model="localHeaders.accept"
            size="small"
            clearable
            placeholder="如: text/html,..."
          />
        </el-form-item>
        <el-form-item label="Accept-Language">
          <el-input
            v-model="localHeaders.accept_language"
            size="small"
            clearable
            placeholder="如: zh-CN,zh;q=0.9,..."
          />
        </el-form-item>
      </el-form>
    </div>

    <div class="custom-headers">
      <div class="section-title">自定义</div>
      <div
        v-for="(item, index) in customHeaders"
        :key="index"
        class="custom-row"
      >
        <el-input
          v-model="item.key"
          placeholder="Header 名 (如 Authorization)"
          size="small"
          class="key-input"
        />
        <el-input
          v-model="item.value"
          placeholder="Header 值"
          size="small"
          class="value-input"
        />
        <el-button
          :icon="Delete"
          circle
          size="small"
          @click="removeCustom(index)"
        />
      </div>
      <el-button
        v-if="canShowAddButton"
        type="primary"
        plain
        size="small"
        style="margin-top: 8px"
        @click="addCustomRow"
      >
        + 添加自定义 header
      </el-button>
      <div v-else class="hint">
        提示: 在已有行最后一行输入内容后会自动追加新行
      </div>
    </div>

    <template #footer>
      <el-button @click="handleClose" size="small">取消</el-button>
      <el-button type="primary" @click="handleSave" size="small">
        保存
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, watch, computed } from 'vue'
import { Delete } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

const props = defineProps({
  modelValue: {
    type: Boolean,
    default: false,
  },
  headers: {
    type: Object,
    default: () => ({}),
  },
})

const emit = defineEmits(['update:modelValue', 'save'])

const FIXED_KEYS = new Set([
  'User-agent', 'user-agent', 'user_agent',
  'Accept', 'accept',
  'Accept-Language', 'accept-language', 'accept_language',
])

const localHeaders = ref({
  user_agent: '',
  accept: '',
  accept_language: '',
})

const customHeaders = ref([])

function initFromProps(headers) {
  const h = headers || {}
  localHeaders.value = {
    user_agent: h['User-agent'] ?? h['user-agent'] ?? h.user_agent ?? '',
    accept: h['Accept'] ?? h.accept ?? '',
    accept_language:
      h['Accept-Language'] ?? h['accept-language'] ?? h.accept_language ?? '',
  }
  customHeaders.value = Object.entries(h)
    .filter(([k]) => !FIXED_KEYS.has(k))
    .map(([k, v]) => ({ key: k, value: String(v) }))
}

watch(
  () => props.modelValue,
  (v) => {
    if (v) initFromProps(props.headers)
  }
)

const hasEmptyRow = computed(() =>
  customHeaders.value.some(
    (r) => r.key.trim() === '' && r.value.trim() === ''
  )
)

const canShowAddButton = computed(
  () => customHeaders.value.length === 0 || hasEmptyRow.value
)

watch(
  customHeaders,
  (rows) => {
    if (rows.length === 0) return
    const last = rows[rows.length - 1]
    if (last.key.trim() === '' && last.value.trim() === '') return
    rows.push({ key: '', value: '' })
  },
  { deep: true }
)

function addCustomRow() {
  customHeaders.value.push({ key: '', value: '' })
}

function removeCustom(index) {
  customHeaders.value.splice(index, 1)
}

function handleClose() {
  emit('update:modelValue', false)
}

function handleSave() {
  const normalizeKey = (k) => k.toLowerCase().replace(/[-_]/g, '-')

  const allKeys = []
  if (localHeaders.value.user_agent.trim())
    allKeys.push(normalizeKey('User-agent'))
  if (localHeaders.value.accept.trim())
    allKeys.push(normalizeKey('Accept'))
  if (localHeaders.value.accept_language.trim())
    allKeys.push(normalizeKey('Accept-Language'))
  customHeaders.value.forEach((r) => {
    if (r.key.trim()) allKeys.push(normalizeKey(r.key))
  })

  const seen = new Set()
  const dup = []
  allKeys.forEach((k) => {
    if (seen.has(k)) dup.push(k)
    else seen.add(k)
  })
  if (dup.length > 0) {
    ElMessage.error(
      `存在重复的 Header 名: ${[...new Set(dup)].join(', ')}`
    )
    return
  }

  const result = {}
  if (localHeaders.value.user_agent.trim()) {
    result['User-agent'] = localHeaders.value.user_agent
  }
  if (localHeaders.value.accept.trim()) {
    result['Accept'] = localHeaders.value.accept
  }
  if (localHeaders.value.accept_language.trim()) {
    result['Accept-Language'] = localHeaders.value.accept_language
  }
  customHeaders.value.forEach((r) => {
    if (r.key.trim() !== '') result[r.key] = r.value
  })

  emit('save', result)
  emit('update:modelValue', false)
}
</script>

<style scoped>
.section-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
  margin: 12px 0 8px;
}

.fixed-headers {
  border-bottom: 1px dashed var(--border-color);
  padding-bottom: 12px;
  margin-bottom: 12px;
}

.custom-row {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
  align-items: center;
}

.custom-row .key-input {
  flex: 0 0 200px;
}

.custom-row .value-input {
  flex: 1;
}

.hint {
  font-size: 12px;
  color: var(--text-muted);
  margin-top: 8px;
}
</style>