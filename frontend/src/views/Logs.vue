<template>
  <div class="page-container">
    <div class="page-header flex-between">
      <div>
        <h2 class="page-title">Log Query</h2>
        <p class="page-desc">Search and browse log entries</p>
      </div>
    </div>

    <!-- Search Form -->
    <el-card class="search-card">
      <el-form :model="searchForm" inline>
        <el-form-item label="Time Range">
          <el-date-picker
            v-model="searchForm.timeRange"
            type="datetimerange"
            range-separator="to"
            start-placeholder="Start"
            end-placeholder="End"
            :shortcuts="timeShortcuts"
          />
        </el-form-item>

        <el-form-item label="Log Type">
          <el-select v-model="searchForm.logType" placeholder="Select" clearable>
            <el-option label="Network" value="network" :disabled="!canAccessLogType('network')" />
            <el-option label="Server" value="server" :disabled="!canAccessLogType('server')" />
            <el-option label="K8S" value="k8s" :disabled="!canAccessLogType('k8s')" />
            <el-option label="All" value="all" :disabled="!isAdmin" />
          </el-select>
        </el-form-item>

        <el-form-item label="Severity">
          <el-select v-model="searchForm.severity" placeholder="Select" clearable>
            <el-option label="INFO" value="INFO" />
            <el-option label="WARNING" value="WARNING" />
            <el-option label="ERROR" value="ERROR" />
            <el-option label="CRITICAL" value="CRITICAL" />
          </el-select>
        </el-form-item>

        <el-form-item label="Source Host">
          <el-input v-model="searchForm.sourceHost" placeholder="Hostname or IP" />
        </el-form-item>

        <el-form-item label="Search">
          <el-input v-model="searchForm.keyword" placeholder="Keyword search" clearable>
            <template #prefix>
              <el-icon><Search /></el-icon>
            </template>
          </el-input>
        </el-form-item>

        <el-form-item>
          <el-button type="primary" @click="handleSearch">Search</el-button>
          <el-button @click="resetSearch">Reset</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- Results Table -->
    <el-card class="mt-20">
      <el-table
        :data="logData"
        stripe
        v-loading="loading"
        :row-class-name="getRowClass"
      >
        <el-table-column prop="timestamp" label="Timestamp" width="180" sortable />
        <el-table-column prop="log_type" label="Type" width="100" />
        <el-table-column prop="source_host" label="Source" width="150" />
        <el-table-column prop="severity" label="Severity" width="100">
          <template #default="{ row }">
            <el-tag :type="getSeverityType(row.severity)" size="small">
              {{ row.severity }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="program" label="Program" width="120" />
        <el-table-column prop="message" label="Message" show-overflow-tooltip />
        <el-table-column label="Actions" width="100" fixed="right">
          <template #default="{ row }">
            <el-button size="small" link @click="viewDetail(row)">Detail</el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- Pagination -->
      <div class="pagination-wrapper">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :page-sizes="[20, 50, 100, 200]"
          :total="total"
          layout="total, sizes, prev, pager, next, jumper"
          @size-change="handleSizeChange"
          @current-change="handleCurrentChange"
        />
      </div>
    </el-card>

    <!-- Detail Dialog -->
    <el-dialog v-model="detailVisible" title="Log Detail" width="60%">
      <el-descriptions :column="2" border v-if="currentLog">
        <el-descriptions-item label="Timestamp">{{ currentLog.timestamp }}</el-descriptions-item>
        <el-descriptions-item label="Log Type">{{ currentLog.log_type }}</el-descriptions-item>
        <el-descriptions-item label="Source Host">{{ currentLog.source_host }}</el-descriptions-item>
        <el-descriptions-item label="Source IP">{{ currentLog.source_ip }}</el-descriptions-item>
        <el-descriptions-item label="Severity">
          <el-tag :type="getSeverityType(currentLog.severity)">{{ currentLog.severity }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="Program">{{ currentLog.program }}</el-descriptions-item>
        <el-descriptions-item label="Message" :span="2">
          <pre class="log-message">{{ currentLog.message }}</pre>
        </el-descriptions-item>
        <el-descriptions-item label="Raw Message" :span="2">
          <pre class="raw-message">{{ currentLog.raw_message }}</pre>
        </el-descriptions-item>
      </el-descriptions>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed } from 'vue'
import { useAuthStore } from '@/stores/auth'

const authStore = useAuthStore()

const loading = ref(false)
const detailVisible = ref(false)
const currentLog = ref(null)

const currentPage = ref(1)
const pageSize = ref(50)
const total = ref(1000)

const canAccessLogType = computed(() => authStore.canAccessLogType)
const isAdmin = computed(() => ['super_admin', 'audit_admin'].includes(authStore.userRole))

const searchForm = reactive({
  timeRange: [],
  logType: '',
  severity: '',
  sourceHost: '',
  keyword: ''
})

const timeShortcuts = [
  {
    text: 'Last Hour',
    value: () => {
      const end = new Date()
      const start = new Date()
      start.setTime(start.getTime() - 3600 * 1000)
      return [start, end]
    }
  },
  {
    text: 'Today',
    value: () => {
      const end = new Date()
      const start = new Date()
      start.setHours(0, 0, 0, 0)
      return [start, end]
    }
  },
  {
    text: 'Last 7 Days',
    value: () => {
      const end = new Date()
      const start = new Date()
      start.setTime(start.getTime() - 3600 * 1000 * 24 * 7)
      return [start, end]
    }
  }
]

const logData = ref([
  { timestamp: '2024-04-17 14:30:45', log_type: 'server', source_host: 'web-01', severity: 'INFO', program: 'nginx', message: 'Request processed successfully' },
  { timestamp: '2024-04-17 14:30:40', log_type: 'network', source_host: 'switch-01', severity: 'WARNING', program: 'cisco', message: 'Interface flapping detected' },
  { timestamp: '2024-04-17 14:30:35', log_type: 'k8s', source_host: 'pod-api-01', severity: 'ERROR', program: 'kubelet', message: 'Container failed to start' },
])

function getSeverityType(severity) {
  const types = {
    INFO: 'info',
    WARNING: 'warning',
    ERROR: 'danger',
    CRITICAL: 'danger'
  }
  return types[severity] || 'info'
}

function getRowClass({ row }) {
  if (row.severity === 'ERROR' || row.severity === 'CRITICAL') {
    return 'error-row'
  }
  if (row.severity === 'WARNING') {
    return 'warning-row'
  }
  return ''
}

function handleSearch() {
  loading.value = true
  setTimeout(() => {
    loading.value = false
  }, 500)
}

function resetSearch() {
  searchForm.timeRange = []
  searchForm.logType = ''
  searchForm.severity = ''
  searchForm.sourceHost = ''
  searchForm.keyword = ''
}

function handleSizeChange(val) {
  pageSize.value = val
}

function handleCurrentChange(val) {
  currentPage.value = val
}

function viewDetail(row) {
  currentLog.value = row
  detailVisible.value = true
}
</script>

<style scoped lang="scss">
.search-card {
  margin-bottom: 20px;
}

.pagination-wrapper {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
}

.log-message, .raw-message {
  background-color: #f5f7fa;
  padding: 10px;
  border-radius: 4px;
  font-family: monospace;
  white-space: pre-wrap;
  max-height: 200px;
  overflow-y: auto;
}

.error-row {
  background-color: #fef0f0;
}

.warning-row {
  background-color: #fdf6ec;
}
</style>