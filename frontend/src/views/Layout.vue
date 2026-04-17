<template>
  <div class="layout-container">
    <!-- Sidebar -->
    <el-scrollbar class="layout-sidebar" :class="{ collapsed: isCollapsed }">
      <div class="sidebar-header">
        <span v-if="!isCollapsed" class="logo">AI Log Analyzer</span>
        <span v-else class="logo-mini">AI</span>
      </div>

      <el-menu
        :default-active="activeMenu"
        :collapse="isCollapsed"
        class="sidebar-menu"
        router
      >
        <template v-for="item in visibleMenuItems" :key="item.path">
          <!-- Single menu item -->
          <el-menu-item v-if="!item.children" :index="item.path">
            <el-icon><component :is="item.meta?.icon" /></el-icon>
            <span>{{ item.meta?.title }}</span>
          </el-menu-item>

          <!-- Sub menu -->
          <el-sub-menu v-else :index="item.path">
            <template #title>
              <el-icon><component :is="item.meta?.icon" /></el-icon>
              <span>{{ item.meta?.title }}</span>
            </template>
            <el-menu-item
              v-for="child in item.children"
              :key="child.path"
              :index="child.path"
            >
              {{ child.meta?.title }}
            </el-menu-item>
          </el-sub-menu>
        </template>
      </el-menu>
    </el-scrollbar>

    <!-- Main content -->
    <div class="layout-main">
      <!-- Header -->
      <header class="layout-header">
        <div class="header-left">
          <el-icon
            class="collapse-btn"
            :size="20"
            @click="toggleCollapse"
          >
            <component :is="isCollapsed ? 'Expand' : 'Fold'" />
          </el-icon>
          <el-breadcrumb separator="/">
            <el-breadcrumb-item :to="{ path: '/' }">Home</el-breadcrumb-item>
            <el-breadcrumb-item v-if="currentRoute.meta?.title !== 'Dashboard'">
              {{ currentRoute.meta?.title }}
            </el-breadcrumb-item>
          </el-breadcrumb>
        </div>

        <div class="header-right">
          <el-badge :value="notificationCount" :hidden="notificationCount === 0">
            <el-icon :size="20"><Bell /></el-icon>
          </el-badge>

          <el-dropdown @command="handleUserCommand">
            <div class="user-info">
              <div class="user-avatar">{{ userName?.charAt(0)?.toUpperCase() }}</div>
              <span class="user-name">{{ userName }}</span>
              <el-icon><ArrowDown /></el-icon>
            </div>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="profile">Profile</el-dropdown-item>
                <el-dropdown-item command="settings">Settings</el-dropdown-item>
                <el-dropdown-item divided command="logout">Logout</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </header>

      <!-- Content -->
      <main class="layout-content">
        <router-view v-slot="{ Component }">
          <transition name="fade" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </main>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const isCollapsed = ref(false)
const notificationCount = ref(0)

const currentRoute = computed(() => route)
const activeMenu = computed(() => route.path)
const userName = computed(() => authStore.userName)

const menuItems = [
  { path: '/dashboard', meta: { title: 'Dashboard', icon: 'HomeFilled' } },
  { path: '/logs', meta: { title: 'Log Query', icon: 'Document' } },
  { path: '/analysis', meta: { title: 'AI Analysis', icon: 'Cpu' } },
  { path: '/reports', meta: { title: 'Reports', icon: 'DocumentCopy' } },
  { path: '/charts', meta: { title: 'Charts', icon: 'DataLine' } },
  {
    path: '/admin',
    meta: { title: 'Admin', icon: 'Setting', roles: ['super_admin', 'audit_admin', 'dept_admin'] },
    children: [
      { path: '/admin/users', meta: { title: 'Users' } },
      { path: '/admin/ai-config', meta: { title: 'AI Config' } },
      { path: '/admin/audit', meta: { title: 'Audit' } },
    ]
  }
]

const visibleMenuItems = computed(() => {
  return menuItems.filter(item => {
    if (!item.meta?.roles) return true
    return item.meta.roles.includes(authStore.userRole)
  })
})

function toggleCollapse() {
  isCollapsed.value = !isCollapsed.value
}

function handleUserCommand(command) {
  if (command === 'profile') {
    router.push('/profile')
  } else if (command === 'settings') {
    router.push('/profile')
  } else if (command === 'logout') {
    authStore.logout()
    router.push('/login')
  }
}

onMounted(() => {
  authStore.fetchUserInfo()
})
</script>

<style scoped lang="scss">
.collapse-btn {
  cursor: pointer;
  padding: 5px;
}

.user-info {
  cursor: pointer;
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>