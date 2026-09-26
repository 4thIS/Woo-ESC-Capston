import '@/styles/index.css'
import { createApp } from 'vue'
import { restoreSession } from '@/lib/session'
import { expireIfIdle } from './idle'
import AdminApp from './AdminApp.vue'
import { makeRouter } from './router'

restoreSession('admin')
expireIfIdle()
createApp(AdminApp).use(makeRouter()).mount('#app')
