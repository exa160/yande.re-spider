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
          <el-form-item label="线程数">
            <el-input-number v-model="downloaderConfig.thread_num" :min="1" :max="32" />
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
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
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
</style>
