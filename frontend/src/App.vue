<template>
  <div id="app">
    <el-container style="height: 100vh">
      <!-- 顶部导航栏 -->
      <el-header style="background: #409EFF; color: white; display: flex; align-items: center; justify-content: space-between;">
        <div style="display: flex; align-items: center;">
          <h2 style="margin: 0; margin-right: 20px;">Yande.re Spider</h2>
        </div>
        <div>
          <el-button type="primary" @click="$router.push('/')">图库</el-button>
          <el-button type="primary" @click="$router.push('/download')">下载管理</el-button>
          <el-button type="primary" @click="$router.push('/config')">配置</el-button>
        </div>
      </el-header>

      <!-- 主内容区 -->
      <el-main>
        <router-view />
      </el-main>
    </el-container>
  </div>
</template>

<script setup>
</script>

<style>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

#app {
  font-family: 'Helvetica Neue', Helvetica, 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', Arial, sans-serif;
}
</style>
