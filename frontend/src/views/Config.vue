<template>
  <div class="config-page">
    <el-row :gutter="20">
      <!-- API配置 -->
      <el-col :span="12">
        <el-card>
          <template #header>
            <span>API配置</span>
          </template>
          <el-form :model="apiConfig" label-width="120px">
            <el-form-item label="重试次数">
              <el-input-number v-model="apiConfig.retry_times" :min="0" :max="500" />
            </el-form-item>
            <el-form-item label="超时时间(秒)">
              <el-input-number v-model="apiConfig.timeout" :min="1" :max="300" />
            </el-form-item>
            <el-form-item label="启用代理">
              <el-switch v-model="apiConfig.proxy_enable" />
            </el-form-item>
            <el-form-item label="代理地址" v-if="apiConfig.proxy_enable">
              <el-input v-model="apiConfig.proxy" placeholder="http://host:port 或 socks5://host:port" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="saveApiConfig" :loading="saving">
                保存
              </el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>

      <!-- 下载器配置 -->
      <el-col :span="12">
        <el-card>
          <template #header>
            <span>下载器配置</span>
          </template>
          <el-form :model="downloaderConfig" label-width="120px">
            <el-form-item label="线程数">
              <el-input-number v-model="downloaderConfig.thread_num" :min="1" :max="32" />
            </el-form-item>
            <el-form-item label="分块大小(KB)">
              <el-input-number v-model="downloaderConfig.chunk_size" :min="1" :max="102400" />
            </el-form-item>
            <el-form-item label="分段大小(MB)">
              <el-input-number v-model="downloaderConfig.split_size" :min="1" :max="1000000" />
            </el-form-item>
            <el-form-item label="重试次数">
              <el-input-number v-model="downloaderConfig.retry_times" :min="0" :max="500" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="saveDownloaderConfig" :loading="saving">
                保存
              </el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>
    </el-row>

    <!-- 数据库配置 -->
    <el-row :gutter="20" style="margin-top: 20px;">
      <el-col :span="24">
        <el-card>
          <template #header>
            <div style="display: flex; justify-content: space-between; align-items: center;">
              <span>数据库配置</span>
              <el-button type="primary" size="small" @click="testConnection" :loading="testing">
                测试连接
              </el-button>
            </div>
          </template>
          <el-form :model="databaseConfig" label-width="120px">
            <el-form-item label="启用数据库">
              <el-switch v-model="databaseConfig.enable" />
            </el-form-item>
            <template v-if="databaseConfig.enable">
              <el-row :gutter="20">
                <el-col :span="12">
                  <el-form-item label="主机">
                    <el-input v-model="databaseConfig.host" />
                  </el-form-item>
                </el-col>
                <el-col :span="12">
                  <el-form-item label="端口">
                    <el-input-number v-model="databaseConfig.port" :min="1" :max="65535" />
                  </el-form-item>
                </el-col>
              </el-row>
              <el-row :gutter="20">
                <el-col :span="12">
                  <el-form-item label="用户名">
                    <el-input v-model="databaseConfig.user" />
                  </el-form-item>
                </el-col>
                <el-col :span="12">
                  <el-form-item label="密码">
                    <el-input v-model="databaseConfig.password" type="password" show-password />
                  </el-form-item>
                </el-col>
              </el-row>
              <el-row :gutter="20">
                <el-col :span="12">
                  <el-form-item label="数据库名">
                    <el-input v-model="databaseConfig.schema_name" />
                  </el-form-item>
                </el-col>
                <el-col :span="12">
                  <el-form-item label="数据表名">
                    <el-input v-model="databaseConfig.datatable" />
                  </el-form-item>
                </el-col>
              </el-row>
            </template>
            <el-form-item v-else>
              <el-alert type="info" :closable="false">
                禁用后将使用 SQLite 本地数据库 (data/yande_data.db)
              </el-alert>
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="saveDatabaseConfig" :loading="saving">
                保存
              </el-button>
              <el-button @click="resetConfig">
                重置为默认值
              </el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>
    </el-row>
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
  padding: 20px;
}
</style>
