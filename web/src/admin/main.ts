import '@/styles/index.css'
import { createApp } from 'vue'
import { restoreSession } from '@/lib/session'
import AdminApp from './AdminApp.vue'
import { makeRouter } from './router'

restoreSession('admin')
createApp(AdminApp).use(makeRouter()).mount('#app')
