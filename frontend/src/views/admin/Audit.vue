<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">Audit Logs</h2>
      <p class="page-desc">System operation audit trail</p>
    </div>

    <el-card>
      <el-form :model="filterForm" inline>
        <el-form-item label="Action">
          <el-select v-model="filterForm.action" clearable>
            <el-option label="Login" value="login" />
            <el-option label="Logout" value="logout" />
            <el-option label="Create Task" value="create_task" />
            <el-option label="Download Report" value="download_report" />
            <el-option label="View Logs" value="view_logs" />
          </el-select>
        </el-form-item>
        <el-form-item label="User">
          <el-input v-model="filterForm.user" placeholder="Username" />
        </el-form-item>
        <el-form-item label="Time Range">
          <el-date-picker v-model="filterForm.timeRange" type="datetimerange" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary">Filter</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card class="mt-20">
      <el-table :data="auditLogs" stripe>
        <el-table-column prop="created_at" label="Time" width="180" />
        <el-table-column prop="user_name" label="User" width="150" />
        <el-table-column prop="action" label="Action" width="150">
          <template #default="{ row }">
            <el-tag :type="getActionType(row.action)">{{ row.action }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="resource_type" label="Resource" width="120" />
        <el-table-column prop="ip_address" label="IP" width="150" />
        <el-table-column prop="details" label="Details" show-overflow-tooltip />
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'

const filterForm = reactive({
  action: '',
  user: '',
  timeRange: []
})

const auditLogs = ref([
  { created_at: '2024-04-17 14:30:45', user_name: 'admin', action: 'login', resource_type: 'system', ip_address: '192.168.1.100', details: 'Successful login' },
  { created_at: '2024-04-17 14:30:00', user_name: 'net_user1', action: 'view_logs', resource_type: 'logs', ip_address: '192.168.1.101', details: 'Viewed network logs' },
  { created_at: '2024-04-17 14:25:00', user_name: 'admin', action: 'create_task', resource_type: 'task', ip_address: '192.168.1.100', details: 'Created analysis task-003' },
  { created_at: '2024-04-17 14:20:00', user_name: 'srv_user1', action: 'download_report', resource_type: 'report', ip_address: '192.168.1.102', details: 'Downloaded daily report' },
])

function getActionType(action) {
  const types = {
    login: 'success',
    logout: 'info',
    create_task: 'primary',
    download_report: 'warning',
    view_logs: ''
  }
  return types[action] || ''
}
</script>