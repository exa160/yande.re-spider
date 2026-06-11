/// <reference types="vite/client" />

// vite.config.js 通过 define 编译时注入的全局变量
// 见 frontend/vite.config.js: readFileSync(package.json) + JSON.stringify(version)
declare const __APP_VERSION__: string
