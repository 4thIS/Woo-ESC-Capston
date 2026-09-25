import '@/styles/index.css'
import { createApp } from 'vue'
import StudentApp from './StudentApp.vue'
import { makeRouter } from './router'

createApp(StudentApp).use(makeRouter()).mount('#app')
