import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/Login.vue'),
    meta: { requiresAuth: false }
  },
  {
    path: '/',
    component: () => import('@/views/Layout.vue'),
    redirect: '/dashboard',
    meta: { requiresAuth: true },
    children: [
      {
        path: 'dashboard',
        name: 'Dashboard',
        component: () => import('@/views/Dashboard.vue'),
        meta: { title: 'Dashboard', icon: 'HomeFilled' }
      },
      {
        path: 'logs',
        name: 'Logs',
        component: () => import('@/views/Logs.vue'),
        meta: { title: 'Log Query', icon: 'Document' }
      },
      {
        path: 'analysis',
        name: 'Analysis',
        component: () => import('@/views/Analysis.vue'),
        meta: { title: 'AI Analysis', icon: 'Cpu' }
      },
      {
        path: 'reports',
        name: 'Reports',
        component: () => import('@/views/Reports.vue'),
        meta: { title: 'Reports', icon: 'DocumentCopy' }
      },
      {
        path: 'charts',
        name: 'Charts',
        component: () => import('@/views/Charts.vue'),
        meta: { title: 'Charts', icon: 'DataLine' }
      },
      {
        path: 'profile',
        name: 'Profile',
        component: () => import('@/views/Profile.vue'),
        meta: { title: 'Profile', icon: 'User', hidden: true }
      },
      // Admin routes
      {
        path: 'admin',
        name: 'Admin',
        redirect: '/admin/users',
        meta: { title: 'Admin', icon: 'Setting', roles: ['super_admin', 'audit_admin', 'dept_admin'] },
        children: [
          {
            path: 'users',
            name: 'AdminUsers',
            component: () => import('@/views/admin/Users.vue'),
            meta: { title: 'User Management', roles: ['super_admin', 'dept_admin'] }
          },
          {
            path: 'roles',
            name: 'AdminRoles',
            component: () => import('@/views/admin/Roles.vue'),
            meta: { title: 'Role Management', roles: ['super_admin'] }
          },
          {
            path: 'ai-config',
            name: 'AdminAIConfig',
            component: () => import('@/views/admin/AIConfig.vue'),
            meta: { title: 'AI Configuration', roles: ['super_admin'] }
          },
          {
            path: 'storage',
            name: 'AdminStorage',
            component: () => import('@/views/admin/Storage.vue'),
            meta: { title: 'Storage Management', roles: ['super_admin'] }
          },
          {
            path: 'email',
            name: 'AdminEmail',
            component: () => import('@/views/admin/Email.vue'),
            meta: { title: 'Email Configuration', roles: ['super_admin'] }
          },
          {
            path: 'tasks',
            name: 'AdminTasks',
            component: () => import('@/views/admin/Tasks.vue'),
            meta: { title: 'Task Scheduling', roles: ['super_admin'] }
          },
          {
            path: 'frontend',
            name: 'AdminFrontend',
            component: () => import('@/views/admin/Frontend.vue'),
            meta: { title: 'Frontend Modules', roles: ['super_admin'] }
          },
          {
            path: 'audit',
            name: 'AdminAudit',
            component: () => import('@/views/admin/Audit.vue'),
            meta: { title: 'Audit Logs', roles: ['super_admin', 'audit_admin'] }
          },
          {
            path: 'ai-usage',
            name: 'AdminAIUsage',
            component: () => import('@/views/admin/AIUsage.vue'),
            meta: { title: 'AI Usage Statistics', roles: ['super_admin', 'audit_admin'] }
          }
        ]
      }
    ]
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'NotFound',
    component: () => import('@/views/NotFound.vue')
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

// Navigation guard for authentication
router.beforeEach((to, from, next) => {
  const authStore = useAuthStore()

  if (to.meta.requiresAuth && !authStore.isLoggedIn) {
    next({ name: 'Login', query: { redirect: to.fullPath } })
  } else if (to.name === 'Login' && authStore.isLoggedIn) {
    next({ name: 'Dashboard' })
  } else if (to.meta.roles && !to.meta.roles.includes(authStore.userRole)) {
    next({ name: 'Dashboard' })
  } else {
    next()
  }
})

export default router