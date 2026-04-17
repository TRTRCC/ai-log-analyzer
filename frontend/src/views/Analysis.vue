<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">AI Analysis</h2>
      <p class="page-desc">AI-powered log analysis and insights</p>
    </div>

    <!-- New Analysis -->
    <el-card>
      <template #header>
        <span>Start New Analysis</span>
      </template>

      <el-form :model="analysisForm" label-width="120px">
        <el-row :gutter="20">
          <el-col :span="8">
            <el-form-item label="Analysis Type">
              <el-select v-model="analysisForm.analysisType">
                <el-option label="Full Analysis" value="full" />
                <el-option label="Time Range" value="time_range" />
                <el-option label="Specific Devices" value="devices" />
                <el-option label="Error Focus" value="error_focus" />
              </el-select>
            </el-form-item>
          </el-col>

          <el-col :span="8">
            <el-form-item label="Log Type">
              <el-select v-model="analysisForm.logType">
                <el-option label="Network" value="network" :disabled="!canAccessLogType('network')" />
                <el-option label="Server" value="server" :disabled="!canAccessLogType('server')" />
                <el-option label="K8S" value="k8s" :disabled="!canAccessLogType('k8s')" />
                <el-option label="All" value="all" :disabled="!isAdmin" />
              </el-select>
            </el-form-item>
          </el-col>

          <el-col :span="8">
            <el-form-item label="AI Model">
              <el-select v-model="analysisForm.modelId" placeholder="Select model">
                <el-option
                  v-for="model in aiModels"
                  :key="model.id"
                  :label="model.display_name"
                  :value="model.id"
                />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>

        <el-row :gutter="20" v-if="analysisForm.analysisType === 'time_range'">
          <el-col :span="24">
            <el-form-item label="Time Range">
              <el-date-picker
                v-model="analysisForm.timeRange"
                type="datetimerange"
                range-separator="to"
                start-placeholder="Start"
                end-placeholder="End"
              />
            </el-form-item>
          </el-col>
        </el-row>

        <el-row :gutter="20" v-if="analysisForm.analysisType === 'devices'">
          <el-col :span="24">
            <el-form-item label="Devices">
              <el-select
                v-model="analysisForm.devices"
                multiple
                filterable
                placeholder="Select devices"
              >
                <el-option label="web-01" value="web-01" />
                <el-option label="db-01" value="db-01" />
                <el-option label="switch-01" value="switch-01" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>

        <el-form-item>
          <el-button type="primary" :loading="starting" @click="startAnalysis">
            Start Analysis
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- Analysis Tasks -->
    <el-card class="mt-20">
      <template #header>
        <div class="flex-between">
          <span>Analysis Tasks</span>
          <el-button size="small" @click="refreshTasks">Refresh</el-button>
        </div>
      </template>

      <el-table :data="tasks" stripe v-loading="loading">
        <el-table-column prop="id" label="Task ID" width="250" />
        <el-table-column prop="task_type" label="Type" width="120" />
        <el-table-column prop="status" label="Status" width="100">
          <template #default="{ row }">
            <el-tag :type="getStatusType(row.status)">
              {{ row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="log_type" label="Log Type" width="100" />
        <el-table-column prop="progress_percent" label="Progress" width="150">
          <template #default="{ row }">
            <el-progress
              :percentage="row.progress_percent"
              :status="row.status === 'completed' ? 'success' : ''"
            />
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="Created" width="180" />
        <el-table-column prop="input_tokens" label="Tokens" width="120">
          <template #default="{ row }">
            {{ row.input_tokens || '-' }} / {{ row.output_tokens || '-' }}
          </template>
        </el-table-column>
        <el-table-column label="Actions" fixed="right" width="200">
          <template #default="{ row }">
            <el-button size="small" link @click="viewResult(row)" :disabled="row.status !== 'completed'">
              View Result
            </el-button>
            <el-button size="small" link @click="cancelTask(row)" :disabled="row.status !== 'pending'">
              Cancel
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- Result Dialog -->
    <el-dialog v-model="resultVisible" title="Analysis Result" width="70%">
      <div v-if="currentResult">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="Task ID">{{ currentResult.id }}</el-descriptions-item>
          <el-descriptions-item label="Status">
            <el-tag :type="getStatusType(currentResult.status)">{{ currentResult.status }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="Input Tokens">{{ currentResult.input_tokens }}</el-descriptions-item>
          <el-descriptions-item label="Output Tokens">{{ currentResult.output_tokens }}</el-descriptions-item>
        </el-descriptions>

        <el-divider>Analysis Summary</el-divider>
        <div class="analysis-content">
          <pre>{{ currentResult.result?.summary || 'No summary available' }}</pre>
        </div>

        <el-divider>Key Findings</el-divider>
        <el-collapse>
          <el-collapse-item
            v-for="(finding, index) in currentResult.result?.findings"
            :key="index"
            :title="finding.title"
          >
            {{ finding.description }}
          </el-collapse-item>
        </el-collapse>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'

const authStore = useAuthStore()

const loading = ref(false)
const starting = ref(false)
const resultVisible = ref(false)
const currentResult = ref(null)

const canAccessLogType = computed(() => authStore.canAccessLogType)
const isAdmin = computed(() => ['super_admin', 'audit_admin'].includes(authStore.userRole))

const analysisForm = reactive({
  analysisType: 'full',
  logType: 'server',
  modelId: '',
  timeRange: [],
  devices: []
})

const aiModels = ref([
  { id: 'model-1', display_name: 'Claude 3.5 Sonnet' },
  { id: 'model-2', display_name: 'GPT-4' },
  { id: 'model-3', display_name: 'Azure GPT-4' },
])

const tasks = ref([
  { id: 'task-001', task_type: 'auto', status: 'completed', log_type: 'all', progress_percent: 100, created_at: '2024-04-17 08:00', input_tokens: 50000, output_tokens: 5000 },
  { id: 'task-002', task_type: 'manual', status: 'running', log_type: 'network', progress_percent: 65, created_at: '2024-04-17 10:30' },
  { id: 'task-003', task_type: 'manual', status: 'pending', log_type: 'server', progress_percent: 0, created_at: '2024-04-17 12:00' },
])

function getStatusType(status) {
  const types = {
    completed: 'success',
    running: 'primary',
    pending: 'info',
    failed: 'danger',
    cancelled: 'info'
  }
  return types[status] || 'info'
}

async function startAnalysis() {
  starting.value = true
  setTimeout(() => {
    ElMessage.success('Analysis task created')
    starting.value = false
    tasks.value.unshift({
      id: `task-${Date.now()}`,
      task_type: 'manual',
      status: 'pending',
      log_type: analysisForm.logType,
      progress_percent: 0,
      created_at: new Date().toISOString()
    })
  }, 1000)
}

function refreshTasks() {
  loading.value = true
  setTimeout(() => {
    loading.value = false
  }, 500)
}

function viewResult(task) {
  currentResult.value = {
    ...task,
    result: {
      summary: 'Analysis shows 3 network anomalies detected in the past 24 hours...',
      findings: [
        { title: 'Network Issue', description: 'Interface flapping on switch-01' },
        { title: 'Security Alert', description: 'Multiple failed login attempts' },
        { title: 'Performance', description: 'High CPU usage on web-01' }
      ]
    }
  }
  resultVisible.value = true
}

function cancelTask(task) {
  task.status = 'cancelled'
  ElMessage.info('Task cancelled')
}
</script>

<style scoped lang="scss">
.analysis-content {
  background-color: #f5f7fa;
  padding: 15px;
  border-radius: 4px;
  font-family: monospace;
  white-space: pre-wrap;
  max-height: 300px;
  overflow-y: auto;
}
</style>