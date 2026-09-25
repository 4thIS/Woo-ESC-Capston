import { createApp } from 'vue'
import AdminApp from './AdminApp.vue'
import { makeRouter } from './router'

createApp(AdminApp).use(makeRouter()).mount('#app')
