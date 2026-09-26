import '@/styles/index.css'
import { createApp } from 'vue'
import { restoreSession } from '@/lib/session'
import StudentApp from './StudentApp.vue'
import { makeRouter } from './router'

restoreSession('student')
createApp(StudentApp).use(makeRouter()).mount('#app')
