<template>
  <div class="config-page">
    <!-- 左侧菜单 -->
    <div class="config-menu">
      <div 
        class="menu-item" 
        :class="{ active: activeMenu === 'api' }"
        @click="activeMenu = 'api'"
      >
        API配置
      </div>
      <div 
        class="menu-item" 
        :class="{ active: activeMenu === 'downloader' }"
        @click="activeMenu = 'downloader'"
      >
        下载器配置
      </div>
      <div 
        class="menu-item" 
        :class="{ active: activeMenu === 'database' }"
        @click="activeMenu = 'database'"
      >
        数据库配置
      </div>
      <div 
        class="menu-item" 
        :class="{ active: activeMenu === 'about' }"
        @click="activeMenu = 'about'"
      >
        关于
      </div>
    </div>

    <!-- 右侧内容 -->
    <div class="config-content">
      <!-- API配置 -->
      <div v-show="activeMenu === 'api'" class="config-section">
        <el-form :model="apiConfig" label-width="100px" class="config-form">
          <el-form-item label="重试次数">
            <el-input-number v-model="apiConfig.retry_times" :min="0" :max="500" />
          </el-form-item>
          <el-form-item label="超时时间">
            <el-input-number v-model="apiConfig.timeout" :min="1" :max="300" /> 秒
          </el-form-item>
          <el-form-item label="启用代理">
            <el-switch v-model="apiConfig.proxy_enable" />
          </el-form-item>
          <el-form-item label="代理地址" v-if="apiConfig.proxy_enable">
            <el-input v-model="apiConfig.proxy" placeholder="http://host:port 或 socks5://host:port" size="small" />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" @click="saveApiConfig" :loading="saving" size="small">
              保存
            </el-button>
          </el-form-item>
        </el-form>
      </div>

      <!-- 下载器配置 -->
      <div v-show="activeMenu === 'downloader'" class="config-section">
        <el-form :model="downloaderConfig" label-width="100px" class="config-form">
          <el-form-item label="并发下载数">
            <el-input-number v-model="downloaderConfig.max_concurrent_tasks" :min="1" :max="10" />
          </el-form-item>
          <el-form-item label="分块大小">
            <el-input-number v-model="downloaderConfig.chunk_size" :min="1" :max="102400" /> KB
          </el-form-item>
          <el-form-item label="分段大小">
            <el-input-number v-model="downloaderConfig.split_size" :min="1" :max="1000000" /> MB
          </el-form-item>
          <el-form-item label="重试次数">
            <el-input-number v-model="downloaderConfig.retry_times" :min="0" :max="500" />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" @click="saveDownloaderConfig" :loading="saving" size="small">
              保存
            </el-button>
          </el-form-item>
        </el-form>
      </div>

      <!-- 数据库配置 -->
      <div v-show="activeMenu === 'database'" class="config-section">
        <el-form :model="databaseConfig" label-width="100px" class="config-form">
          <el-form-item label="启用数据库">
            <el-switch v-model="databaseConfig.enable" />
          </el-form-item>
          <template v-if="databaseConfig.enable">
            <el-form-item label="主机">
              <el-input v-model="databaseConfig.host" size="small" />
            </el-form-item>
            <el-form-item label="端口">
              <el-input-number v-model="databaseConfig.port" :min="1" :max="65535" size="small" />
            </el-form-item>
            <el-form-item label="用户名">
              <el-input v-model="databaseConfig.user" size="small" />
            </el-form-item>
            <el-form-item label="密码">
              <el-input v-model="databaseConfig.password" type="password" show-password size="small" />
            </el-form-item>
            <el-form-item label="数据库名">
              <el-input v-model="databaseConfig.schema_name" size="small" />
            </el-form-item>
            <el-form-item label="数据表名">
              <el-input v-model="databaseConfig.datatable" size="small" />
            </el-form-item>
          </template>
          <el-form-item v-else>
            <el-alert type="info" :closable="false" show-icon>
              禁用后将使用 SQLite 本地数据库
            </el-alert>
          </el-form-item>
          <el-form-item>
            <el-button type="primary" @click="saveDatabaseConfig" :loading="saving" size="small">
              保存
            </el-button>
            <el-button @click="testConnection" :loading="testing" size="small">
              测试连接
            </el-button>
            <el-button @click="resetConfig" size="small">
              重置
            </el-button>
          </el-form-item>
        </el-form>
      </div>

      <!-- 关于 -->
      <div v-show="activeMenu === 'about'" class="config-section about-section">
        <div class="about-content">
          <div class="about-title">Yande.re Spider Next</div>
          <div class="about-version">Version 1.0.0</div>
          <div class="about-desc">基于 Python + FastAPI + Vue.js 3 的图片下载管理系统</div>
          <div class="about-links">
            <a href="https://github.com/exa160/yande.re-spider" target="_blank" class="github-link">
              <svg height="20" width="20" viewBox="0 0 24 24" fill="currentColor">
                <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.807 5.625-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"/>
              </svg>
              GitHub
            </a>
          </div>
          <div class="about-protection" v-if="tamperDetected">
            <el-alert type="warning" :closable="false" show-icon>
              检测到异常操作，如需帮助请联系作者
            </el-alert>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import api from '@/api'

const apiConfig = ref({
  retry_times: 3,
  timeout: 30,
  proxy_enable: false,
  proxy: ''
})

const downloaderConfig = ref({
  thread_num: 4,
  max_concurrent_tasks: 3,
  chunk_size: 10,
  split_size: 200,
  retry_times: 3
})

const databaseConfig = ref({
  enable: false,
  host: 'localhost',
  port: 3306,
  user: 'root',
  password: '',
  schema_name: 'Pictures',
  datatable: 'YandeRE'
})

const saving = ref(false)
const activeMenu = ref('api')
const testing = ref(false)
const tamperDetected = ref(false)

// 防修改检测状态
const originalElements = new Map()
let protectionInterval = null
let devToolsOpen = false

// 保存关键元素的原始内容
const saveOriginalContent = () => {
  const elements = document.querySelectorAll('.about-title, .about-version, .about-desc, .github-link')
  elements.forEach((el, index) => {
    originalElements.set(index, {
      content: el.innerHTML,
      attributes: el.getAttribute('class'),
      style: el.getAttribute('style')
    })
  })
}

// 检测开发者工具
const detectDevTools = () => {
  const threshold = 160
  const widthThreshold = window.outerWidth - window.innerWidth > threshold
  const heightThreshold = window.outerHeight - window.innerHeight > threshold
  
  if (widthThreshold || heightThreshold) {
    return true
  }
  
  // 检测 console.log 劫持
  const originalLog = console.log
  let logCalled = false
  console.log = function(...args) {
    logCalled = true
    return originalLog.apply(console, args)
  }
  setTimeout(() => {
    if (logCalled) {
      console.log = originalLog
    }
  }, 1000)
  
  return false
}

// 启动防护
const startProtection = () => {
  // 保存初始状态
  saveOriginalContent()
  
  // 定期检测元素变化
  protectionInterval = setInterval(() => {
    // 检测开发者工具
    if (detectDevTools() && !devToolsOpen) {
      devToolsOpen = true
      tamperDetected.value = true
    }
    
    // 检测元素内容变化
    const elements = document.querySelectorAll('.about-title, .about-version, .about-desc, .github-link')
    elements.forEach((el, index) => {
      const original = originalElements.get(index)
      if (original) {
        const currentContent = el.innerHTML
        const currentClass = el.getAttribute('class')
        const currentStyle = el.getAttribute('style')
        
        if (currentContent !== original.content || 
            currentClass !== original.attributes || 
            currentStyle !== original.style) {
          // 恢复原始内容
          el.innerHTML = original.content
          el.setAttribute('class', original.attributes)
          if (original.style) {
            el.setAttribute('style', original.style)
          } else {
            el.removeAttribute('style')
          }
          tamperDetected.value = true
        }
      }
    })
  }, 500)
}

// 停止防护
const stopProtection = () => {
  if (protectionInterval) {
    clearInterval(protectionInterval)
    protectionInterval = null
  }
}

// 禁用右键
const disableContextMenu = (e) => {
  if (activeMenu.value === 'about') {
    e.preventDefault()
    return false
  }
}

// 监听键盘事件
const handleKeyDown = (e) => {
  if (activeMenu.value !== 'about') return
  
  // 禁用 F12
  if (e.key === 'F12') {
    e.preventDefault()
    return false
  }
  
  // 禁用 Ctrl+Shift+I / Ctrl+Shift+J / Ctrl+Shift+C
  if (e.ctrlKey && e.shiftKey && ['I', 'J', 'C'].includes(e.key)) {
    e.preventDefault()
    return false
  }
  
  // 禁用 Ctrl+U (查看源码)
  if (e.ctrlKey && e.key === 'u') {
    e.preventDefault()
    return false
  }
}

const loadConfig = async () => {
  try {
    const response = await api.get('/config/')
    apiConfig.value = {
      retry_times: response.api.retry_times,
      timeout: response.api.timeout,
      proxy_enable: response.api.proxy_enable,
      proxy: response.api.proxy || ''
    }
    downloaderConfig.value = response.downloader
    databaseConfig.value = response.database
  } catch (error) {
    ElMessage.error('加载配置失败')
  }
}

const saveApiConfig = async () => {
  saving.value = true
  try {
    await api.put('/config/api', apiConfig.value)
    ElMessage.success('API配置保存成功')
  } catch (error) {
    ElMessage.error('保存失败')
  } finally {
    saving.value = false
  }
}

const saveDownloaderConfig = async () => {
  saving.value = true
  try {
    await api.put('/config/downloader', downloaderConfig.value)
    ElMessage.success('下载器配置保存成功')
  } catch (error) {
    ElMessage.error('保存失败')
  } finally {
    saving.value = false
  }
}

const saveDatabaseConfig = async () => {
  saving.value = true
  try {
    await api.put('/config/database', databaseConfig.value)
    ElMessage.success('数据库配置保存成功')
  } catch (error) {
    ElMessage.error('保存失败')
  } finally {
    saving.value = false
  }
}

const testConnection = async () => {
  testing.value = true
  try {
    const response = await api.post('/config/test-connection', databaseConfig.value)
    if (response.success) {
      ElMessage.success('数据库连接成功')
    } else {
      ElMessage.error(response.message)
    }
  } catch (error) {
    ElMessage.error('连接测试失败')
  } finally {
    testing.value = false
  }
}

const resetConfig = async () => {
  try {
    await api.post('/config/reset?section=api')
    await api.post('/config/reset?section=downloader')
    await api.post('/config/reset?section=database')
    ElMessage.success('配置已重置')
    await loadConfig()
  } catch (error) {
    ElMessage.error('重置失败')
  }
}

onMounted(() => {
  loadConfig()
  // 关于页面防修改保护
  if (activeMenu.value === 'about') {
    startProtection()
    document.addEventListener('contextmenu', disableContextMenu)
    document.addEventListener('keydown', handleKeyDown)
  }
})

onUnmounted(() => {
  stopProtection()
  document.removeEventListener('contextmenu', disableContextMenu)
  document.removeEventListener('keydown', handleKeyDown)
})

// 监听 activeMenu 变化，动态启停保护
import { watch } from 'vue'
watch(activeMenu, (newVal) => {
  if (newVal === 'about') {
    startProtection()
    document.addEventListener('contextmenu', disableContextMenu)
    document.addEventListener('keydown', handleKeyDown)
  } else {
    stopProtection()
    document.removeEventListener('contextmenu', disableContextMenu)
    document.removeEventListener('keydown', handleKeyDown)
  }
})
</script>

<style scoped>
.config-page {
  display: flex;
  height: 100%;
  width: 100%;
}

.config-menu {
  width: 140px;
  flex-shrink: 0;
  border-right: 1px solid var(--border-color);
  padding: 10px 0;
  background: var(--bg-secondary);
}

.menu-item {
  padding: 10px 15px;
  font-size: 13px;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.3s;
}

.menu-item:hover {
  color: #409EFF;
  background: var(--bg-primary);
}

.menu-item.active {
  color: #409EFF;
  background: #ecf5ff;
  border-right: 3px solid #409EFF;
}

.config-content {
  flex: 1;
  padding: 15px 20px;
  overflow-y: auto;
}

.config-section {
  max-width: 400px;
}

.config-form :deep(.el-form-item) {
  margin-bottom: 12px;
}

.config-form :deep(.el-input-number) {
  width: 120px;
}

/* 关于页面样式 */
.about-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 40px 20px;
  text-align: center;
}

.about-title {
  font-size: 24px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 10px;
}

.about-version {
  font-size: 14px;
  color: var(--text-secondary);
  margin-bottom: 20px;
}

.about-desc {
  font-size: 14px;
  color: var(--text-secondary);
  line-height: 1.6;
  margin-bottom: 30px;
  max-width: 400px;
}

.about-links {
  display: flex;
  gap: 20px;
  margin-bottom: 30px;
}

.github-link {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #409EFF;
  text-decoration: none;
  font-size: 14px;
  transition: opacity 0.3s;
}

.github-link:hover {
  opacity: 0.8;
}

.about-protection {
  margin-top: 20px;
  width: 100%;
  max-width: 300px;
}

/* 暗色模式适配 */
:deep(.dark) .menu-item.active {
  background: #1a1a2e;
  border-right: 3px solid #409EFF;
}
</style>
