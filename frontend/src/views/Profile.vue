<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">My Profile</h2>
    </div>

    <el-card>
      <el-descriptions :column="2" border>
        <el-descriptions-item label="Username">{{ user.username }}</el-descriptions-item>
        <el-descriptions-item label="Email">{{ user.email }}</el-descriptions-item>
        <el-descriptions-item label="Role">
          <el-tag>{{ user.role }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="Department">{{ user.department }}</el-descriptions-item>
        <el-descriptions-item label="Status">
          <el-tag type="success">Active</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="Last Login">{{ user.lastLogin }}</el-descriptions-item>
      </el-descriptions>
    </el-card>

    <el-card class="mt-20">
      <template #header>Change Password</template>
      <el-form :model="passwordForm" label-width="120px">
        <el-form-item label="Current Password">
          <el-input type="password" show-password />
        </el-form-item>
        <el-form-item label="New Password">
          <el-input type="password" show-password />
        </el-form-item>
        <el-form-item label="Confirm Password">
          <el-input type="password" show-password />
        </el-form-item>
        <el-form-item>
          <el-button type="primary">Update Password</el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
import { reactive } from 'vue'
import { useAuthStore } from '@/stores/auth'

const authStore = useAuthStore()

const user = reactive({
  username: authStore.userName,
  email: authStore.userEmail,
  role: authStore.userRole,
  department: 'IT Department',
  lastLogin: '2024-04-17 08:00'
})

const passwordForm = reactive({
  current: '',
  new: '',
  confirm: ''
})
</script>