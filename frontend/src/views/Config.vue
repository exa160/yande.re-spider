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
        :class="{ active: activeMenu === 'advanced' }"
        @click="activeMenu = 'advanced'"
      >
        高级功能
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
          <div class="about-title">Yande.re Local Picture Manager</div>
          <div class="about-version">Version {{ appVersion }}</div>
          <div class="about-desc">Yande.re 本地图片管理工具</div>
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
              检测到异常操作，如需帮助请提issue
            </el-alert>
          </div>
        </div>
      </div>

      <!-- 高级功能 -->
      <div v-show="activeMenu === 'advanced'" class="config-section">
        <div class="advanced-section">
          <div class="advanced-title">缓存更新</div>
          <div class="advanced-desc">从 yande.re API 刷新标签和艺术家信息到本地数据库（首次全量，之后增量）</div>
          
          <div class="cache-stats">
            <div class="stat-item">
              <span class="stat-label">标签缓存</span>
              <span class="stat-value">{{ tagStats.total || 0 }}</span>
              <span class="stat-tip">最大ID: {{ tagStats.max_id || 0 }}</span>
            </div>
            <div class="stat-item">
              <span class="stat-label">艺术家缓存</span>
              <span class="stat-value">{{ artistStats.total || 0 }}</span>
            </div>
          </div>

          <div class="refresh-controls">
            <div class="refresh-item">
              <div class="refresh-info">
                <div class="refresh-name">更新标签</div>
                <div class="refresh-params">
                  <span class="param-tip">从 ID {{ tagStats.max_id || 0 }} 开始增量更新</span>
                  <span class="param-tip" style="color: #E6A23C; margin-left: 8px;">长按全量刷新</span>
                </div>
              </div>
              <el-button 
                type="primary" 
                @click="handleRefreshTags" 
                @mousedown.native="startLongPress"
                @mouseup.native="endLongPress"
                @mouseleave.native="endLongPress"
                @touchstart.native="startLongPress"
                @touchend.native="endLongPress"
                :loading="refreshingTags"
                size="small"
              >
                刷新
              </el-button>
            </div>

            <div class="refresh-item">
              <div class="refresh-info">
                <div class="refresh-name">更新艺术家</div>
                <div class="refresh-params">
                  <el-input-number v-model="refreshArtistsParams.max_pages" :min="1" :max="100" size="small" /> 页
                  <span class="param-tip">(每页100条)</span>
                </div>
              </div>
              <el-button 
                type="primary" 
                @click="handleRefreshArtists" 
                :loading="refreshingArtists"
                size="small"
              >
                刷新
              </el-button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '@/api'
import { tagCacheApi } from '@/api/tagCache'

// 编译时注入的版本号 - 单一来源 (vite.config.js define 替换)
const appVersion = __APP_VERSION__

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
  schema_name: 'Pictures'
})

const saving = ref(false)
const activeMenu = ref('api')
const testing = ref(false)
const tamperDetected = ref(false)

// 高级功能 - 缓存更新
const tagStats = ref({ total: 0, max_id: 0 })
const artistStats = ref({ total: 0 })
const refreshingTags = ref(false)
const refreshingArtists = ref(false)
const refreshTagsParams = ref({ after_id: 0 })
const refreshArtistsParams = ref({ page: 1, limit: 100, max_pages: 10 })

// 长按定时器
const LONG_PRESS_DURATION = 500
let longPressTimer = null

const startLongPress = () => {
  longPressTimer = setTimeout(async () => {
    longPressTimer = null
    try {
      await ElMessageBox.confirm(
        '全量更新将清空现有标签缓存并重新获取所有标签，此操作不可恢复。是否继续？',
        '全量更新确认',
        { confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning' }
      )
    } catch {
      return
    }
    
    refreshingTags.value = true
    try {
      const result = await tagCacheApi.refreshTags({ full_refresh: true, limit: 0 })
      ElMessage.success(`全量刷新已启动，预计获取 ${result.data.total_updated || '大量'} 标签`)
      await loadCacheStats()
    } catch (error) {
      ElMessage.error('全量更新失败')
    } finally {
      refreshingTags.value = false
    }
  }, LONG_PRESS_DURATION)
}

const endLongPress = () => {
  if (longPressTimer) {
    clearTimeout(longPressTimer)
    longPressTimer = null
  }
}

const loadCacheStats = async () => {
  try {
    const [tagsRes, artistsRes] = await Promise.all([
      tagCacheApi.getTagsStats(),
      tagCacheApi.getArtistsStats()
    ])
    tagStats.value = tagsRes.data || {}
    artistStats.value = artistsRes.data || {}
  } catch (error) {
    console.error('Load cache stats error:', error)
  }
}

const handleRefreshTags = async () => {
  if (longPressTimer) {
    clearTimeout(longPressTimer)
    longPressTimer = null
    return
  }
  
  refreshingTags.value = true
  try {
    const result = await tagCacheApi.refreshTags({ after_id: tagStats.value.max_id || 0 })
    ElMessage.success(`标签增量更新完成: 更新了 ${result.data.total_updated} 条 (最新ID: ${result.data.last_id})`)
    await loadCacheStats()
  } catch (error) {
    ElMessage.error('标签更新失败')
  } finally {
    refreshingTags.value = false
  }
}

const handleRefreshArtists = async () => {
  refreshingArtists.value = true
  try {
    const result = await tagCacheApi.refreshArtists(refreshArtistsParams.value)
    // 后端异步处理时 data 为 null，显示 message 即可
    if (result.data) {
      ElMessage.success(`艺术家更新完成: 更新了 ${result.data.total_updated} 条 (共 ${result.data.pages_done} 页)`)
    } else {
      ElMessage.success(result.message || '艺术家刷新任务已启动')
    }
    await loadCacheStats()
  } catch (error) {
    ElMessage.error('艺术家更新失败')
  } finally {
    refreshingArtists.value = false
  }
}

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
    const response = await api.get('/config')
    const config = response.data
    apiConfig.value = {
      retry_times: config.yande_api.retry,
      timeout: config.yande_api.timeout,
      proxy_enable: config.yande_api.proxy_enable,
      proxy: config.yande_api.proxies?.http || ''
    }
    downloaderConfig.value = {
      thread_num: config.downloader.thread_num,
      max_concurrent_tasks: config.downloader.max_concurrent_tasks,
      chunk_size: Math.round(config.downloader.chunk_size / 1024),  // 字节 -> KB
      split_size: Math.round(config.downloader.split_size / (1024 * 1024)),  // 字节 -> MB
      retry_times: config.downloader.retry_times
    }
    databaseConfig.value = config.database
  } catch (error) {
    ElMessage.error('加载配置失败')
  }
}

const saveApiConfig = async () => {
  saving.value = true
  try {
    const payload = {
      retry: apiConfig.value.retry_times,
      timeout: apiConfig.value.timeout,
      proxy_enable: apiConfig.value.proxy_enable,
      proxies: {
        http: apiConfig.value.proxy,
        https: apiConfig.value.proxy
      }
    }
    await api.put('/config/api', payload)
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
    const payload = {
      thread_num: downloaderConfig.value.thread_num,
      max_concurrent_tasks: downloaderConfig.value.max_concurrent_tasks,
      chunk_size: downloaderConfig.value.chunk_size * 1024,  // KB -> 字节
      split_size: downloaderConfig.value.split_size * 1024 * 1024,  // MB -> 字节
      retry_times: downloaderConfig.value.retry_times
    }
    await api.put('/config/downloader', payload)
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
    if (response.data.success) {
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

// 监听切换到高级功能时加载缓存统计
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
  if (newVal === 'advanced') {
    loadCacheStats()
  }
}, { immediate: false })

onUnmounted(() => {
  stopProtection()
  document.removeEventListener('contextmenu', disableContextMenu)
  document.removeEventListener('keydown', handleKeyDown)
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

/* 高级功能样式 */
.advanced-section {
  max-width: 500px;
}

.advanced-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 8px;
}

.advanced-desc {
  font-size: 13px;
  color: var(--text-muted);
  margin-bottom: 20px;
}

.cache-stats {
  display: flex;
  gap: 20px;
  margin-bottom: 24px;
  padding: 12px 16px;
  background: var(--bg-primary);
  border-radius: 8px;
}

.stat-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.stat-label {
  font-size: 12px;
  color: var(--text-muted);
}

.stat-value {
  font-size: 20px;
  font-weight: 600;
  color: var(--text-primary);
}

.stat-tip {
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 2px;
}

.refresh-controls {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.refresh-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  background: var(--bg-primary);
  border-radius: 8px;
}

.refresh-info {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.refresh-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
}

.refresh-params {
  display: flex;
  align-items: center;
  gap: 8px;
}

.param-tip {
  font-size: 12px;
  color: var(--text-muted);
}

/* 暗色模式适配 */
:deep(.dark) .menu-item.active {
  background: #1a1a2e;
  border-right: 3px solid #409EFF;
}

/* 移动端适配 */
@media screen and (max-width: 768px) {
  .config-page {
    flex-direction: column;
  }

  .config-menu {
    width: 100%;
    display: flex;
    flex-direction: row;
    overflow-x: auto;
    border-right: none;
    border-bottom: 1px solid var(--border-color);
    padding: 0;
    gap: 0;
  }

  .menu-item {
    flex-shrink: 0;
    padding: 12px 16px;
    border-right: none;
    border-bottom: 3px solid transparent;
  }

  .menu-item.active {
    border-right: none;
    border-bottom: 3px solid #409EFF;
    background: var(--bg-primary);
  }

  .config-content {
    padding: 12px;
    overflow-y: auto;
  }

  .advanced-section {
    max-width: 100%;
  }

  .cache-stats {
    flex-direction: column;
    gap: 12px;
  }

  .refresh-controls {
    gap: 12px;
  }

  .refresh-item {
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
  }

  .refresh-item .el-button {
    width: 100%;
  }
}
</style>
