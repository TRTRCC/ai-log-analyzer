<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">User Management</h2>
      <p class="page-desc">Manage users and roles</p>
    </div>

    <!-- Actions -->
    <el-card>
      <div class="flex-between">
        <el-form inline>
          <el-form-item>
            <el-input placeholder="Search users" prefix-icon="Search" />
          </el-form-item>
          <el-form-item>
            <el-select placeholder="Role" clearable>
              <el-option label="Super Admin" value="super_admin" />
              <el-option label="Audit Admin" value="audit_admin" />
              <el-option label="Dept Admin" value="dept_admin" />
              <el-option label="Network User" value="network_user" />
              <el-option label="Server User" value="server_user" />
              <el-option label="K8S User" value="k8s_user" />
            </el-select>
          </el-form-item>
        </el-form>
        <el-button type="primary" @click="showCreateUser">
          <el-icon><Plus /></el-icon>
          Add User
        </el-button>
      </div>
    </el-card>

    <!-- Users Table -->
    <el-card class="mt-20">
      <el-table :data="users" stripe>
        <el-table-column prop="username" label="Username" width="150" />
        <el-table-column prop="email" label="Email" width="200" />
        <el-table-column prop="role" label="Role" width="150">
          <template #default="{ row }">
            <el-tag :type="getRoleType(row.role)">{{ row.role }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="department" label="Department" width="150" />
        <el-table-column prop="is_active" label="Status" width="100">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'danger'">
              {{ row.is_active ? 'Active' : 'Disabled' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="last_login" label="Last Login" width="180" />
        <el-table-column prop="created_at" label="Created" width="180" />
        <el-table-column label="Actions" fixed="right" width="200">
          <template #default="{ row }">
            <el-button size="small" link @click="editUser(row)">Edit</el-button>
            <el-button size="small" link @click="resetPassword(row)">Reset Password</el-button>
            <el-button size="small" link type="danger" @click="deleteUser(row)">Delete</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- Create/Edit User Dialog -->
    <el-dialog v-model="userDialogVisible" :title="editingUser ? 'Edit User' : 'Create User'" width="500px">
      <el-form :model="userForm" label-width="100px">
        <el-form-item label="Username" required>
          <el-input v-model="userForm.username" :disabled="editingUser" />
        </el-form-item>
        <el-form-item label="Email" required>
          <el-input v-model="userForm.email" />
        </el-form-item>
        <el-form-item label="Password" :required="!editingUser" v-if="!editingUser">
          <el-input v-model="userForm.password" type="password" show-password />
        </el-form-item>
        <el-form-item label="Role" required>
          <el-select v-model="userForm.role">
            <el-option label="Super Admin" value="super_admin" />
            <el-option label="Audit Admin" value="audit_admin" />
            <el-option label="Dept Admin" value="dept_admin" />
            <el-option label="Network User" value="network_user" />
            <el-option label="Server User" value="server_user" />
            <el-option label="K8S User" value="k8s_user" />
          </el-select>
        </el-form-item>
        <el-form-item label="Department">
          <el-select v-model="userForm.department_id" clearable>
            <el-option label="Network Team" value="dept-1" />
            <el-option label="Server Team" value="dept-2" />
            <el-option label="K8S Team" value="dept-3" />
            <el-option label="Audit Team" value="dept-4" />
          </el-select>
        </el-form-item>
        <el-form-item label="Active">
          <el-switch v-model="userForm.is_active" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="userDialogVisible = false">Cancel</el-button>
        <el-button type="primary" @click="saveUser">Save</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

const userDialogVisible = ref(false)
const editingUser = ref(null)

const userForm = reactive({
  username: '',
  email: '',
  password: '',
  role: 'server_user',
  department_id: '',
  is_active: true
})

const users = ref([
  { id: '1', username: 'admin', email: 'admin@example.com', role: 'super_admin', department: 'IT Admin', is_active: true, last_login: '2024-04-17 08:00', created_at: '2024-01-01' },
  { id: '2', username: 'net_user1', email: 'net@example.com', role: 'network_user', department: 'Network Team', is_active: true, last_login: '2024-04-16 14:00', created_at: '2024-02-01' },
  { id: '3', username: 'srv_user1', email: 'srv@example.com', role: 'server_user', department: 'Server Team', is_active: true, last_login: '2024-04-15 10:00', created_at: '2024-02-01' },
])

function getRoleType(role) {
  const types = {
    super_admin: 'danger',
    audit_admin: 'warning',
    dept_admin: 'success',
    network_user: 'primary',
    server_user: 'info',
    k8s_user: ''
  }
  return types[role] || ''
}

function showCreateUser() {
  editingUser.value = null
  Object.assign(userForm, {
    username: '',
    email: '',
    password: '',
    role: 'server_user',
    department_id: '',
    is_active: true
  })
  userDialogVisible.value = true
}

function editUser(user) {
  editingUser.value = user
  Object.assign(userForm, {
    username: user.username,
    email: user.email,
    role: user.role,
    department_id: user.department,
    is_active: user.is_active
  })
  userDialogVisible.value = true
}

async function saveUser() {
  ElMessage.success(editingUser.value ? 'User updated' : 'User created')
  userDialogVisible.value = false
}

async function resetPassword(user) {
  await ElMessageBox.confirm(`Reset password for ${user.username}?`, 'Confirm', {
    type: 'warning'
  })
  ElMessage.success('Password reset, new password sent to user email')
}

async function deleteUser(user) {
  await ElMessageBox.confirm(`Delete user ${user.username}?`, 'Confirm', {
    type: 'danger'
  })
  users.value = users.value.filter(u => u.id !== user.id)
  ElMessage.success('User deleted')
}
</script>