import { createApp } from 'vue'
import App from './App.vue'
import { pinia } from './stores'
import router from './router'
import { realtime } from './services/realtime'
import './assets/main.css'
import './assets/operations.css'
import './assets/sidebar-layout.css'

createApp(App).use(pinia).use(router).mount('#app')

realtime.syncAuthentication()
router.afterEach(() => realtime.syncAuthentication())
